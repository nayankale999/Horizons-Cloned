"""Bulk import of products and per-market data from CSV or Excel.

File shape: one row per product × region. The product is identified by
(active substance, dosage form); the market by (product, region). Rows for the
same product share product-level columns, so the last non-empty value wins.

Rules
- Columns may appear in any order; headers are matched case/punctuation-insensitively,
  and the column labels of this app's own report CSV are accepted, so a report can be
  edited and re-imported.
- Only columns present in the file are written. An empty cell leaves the stored value
  unchanged (it never clears it).
- Keywords and excipients are `;`-separated and replace the product's current set when
  the cell is non-empty.
- Unknown lookup values (indication, dosage form, region, keyword, excipient) are errors
  unless `create_lookups=True`.
- Validation runs over the whole file first. With any error, nothing is written unless
  `skip_invalid=True`, which imports the valid rows and reports the rest.
- `dry_run=True` performs the full import inside a transaction and rolls it back, so the
  counts are exact.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from reference.models import DosageForm, Excipient, Indication, Keyword, Region

from .models import Product, ProductCountry

# canonical column -> (target, type)
PRODUCT_COLUMNS = {
    "brand": "text", "innovator": "text", "therapeutic_category": "text", "strength": "text",
    "xlogp": "float", "logp": "float", "molecular_weight": "float", "solubility": "solubility",
}
MARKET_COLUMNS = {
    "revenue_musd": "decimal", "earliest_generic_launch": "date", "marketing_exclusivity": "date",
    "data_exclusivity": "date", "main_patent_expiry": "date", "patent_extension": "date",
    "other_blocking_patent": "text", "key_patents": "text", "ftf_anda_filers": "int",
    "post_generic_6m": "int", "api_manufacturers": "int", "api_consumption_kg": "decimal",
    "suggested_strategy": "text",
}
KEY_COLUMNS = ("active_substance", "dosage_form", "region")
LOOKUP_COLUMNS = {"indication": Indication, "dosage_form": DosageForm, "region": Region}
M2M_COLUMNS = {"keywords": Keyword, "excipients": Excipient}
ALL_COLUMNS = list(KEY_COLUMNS) + ["indication"] + list(PRODUCT_COLUMNS) + list(MARKET_COLUMNS) + list(M2M_COLUMNS)

ALIASES = {
    "substance": "active_substance", "activesubstance": "active_substance", "molecule": "active_substance",
    "dosage": "dosage_form", "dosagetype": "dosage_form", "dosageform": "dosage_form",
    "country": "region", "market": "region",
    "therapeuticcategory": "therapeutic_category",
    "revenue": "revenue_musd", "revenuem": "revenue_musd", "revenuemusd": "revenue_musd",
    "earliestgenericlaunch": "earliest_generic_launch", "genericlaunch": "earliest_generic_launch",
    "marketingexclusivity": "marketing_exclusivity", "me": "marketing_exclusivity", "mence": "marketing_exclusivity",
    "marketingexclusivitymencenda": "marketing_exclusivity",
    "dataexclusivity": "data_exclusivity", "de": "data_exclusivity", "dence1": "data_exclusivity",
    "dataexclusivitydence1": "data_exclusivity",
    "mainpatentexpiry": "main_patent_expiry", "patentexpiry": "main_patent_expiry",
    "patentextension": "patent_extension", "otherblockingpatent": "other_blocking_patent",
    "keypatents": "key_patents",
    "ftfandafilers": "ftf_anda_filers", "ftfanda": "ftf_anda_filers", "andafilers": "ftf_anda_filers",
    "postgenerictracker6m": "post_generic_6m", "postgeneric6m": "post_generic_6m",
    "apimanufacturers": "api_manufacturers", "apimfrs": "api_manufacturers",
    "apiconsumptionkg": "api_consumption_kg", "apiconsumptionkgs": "api_consumption_kg", "apiconskg": "api_consumption_kg",
    "suggestedstrategy": "suggested_strategy", "suggestedstrategycomments": "suggested_strategy", "strategy": "suggested_strategy",
    "molecularweight": "molecular_weight", "mw": "molecular_weight",
    "keyword": "keywords", "excipient": "excipients",
}
SOLUBILITY = {label.lower().replace(" ", "_"): code for code, label in Product.Solubility.choices}
SOLUBILITY.update({code: code for code, _ in Product.Solubility.choices})
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class ImportFileError(Exception):
    """The file itself can't be read (format, encoding, missing required columns)."""


@dataclass
class RowError:
    row: int
    column: str
    message: str

    def __str__(self):
        return f"Row {self.row}{f' [{self.column}]' if self.column else ''}: {self.message}"


@dataclass
class ImportResult:
    rows: int = 0
    rows_imported: int = 0
    products_created: int = 0
    products_updated: int = 0
    markets_created: int = 0
    markets_updated: int = 0
    lookups_created: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    ignored_columns: list = field(default_factory=list)
    dry_run: bool = False
    applied: bool = False

    def summary(self):
        verb = "Would import" if self.dry_run else "Imported"
        parts = [
            f"{verb} {self.rows_imported}/{self.rows} rows",
            f"products +{self.products_created} new, {self.products_updated} updated",
            f"markets +{self.markets_created} new, {self.markets_updated} updated",
        ]
        if self.lookups_created:
            parts.append("new lookups " + ", ".join(f"{k}: {v}" for k, v in self.lookups_created.items()))
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return "; ".join(parts)


# ---------------------------------------------------------------- reading files

def _canonical(header):
    key = re.sub(r"[^a-z0-9]", "", str(header or "").lower())
    if not key:
        return None
    for col in ALL_COLUMNS:
        if key == col.replace("_", ""):
            return col
    return ALIASES.get(key)


def read_rows(fileobj, filename):
    """Return (headers, rows) where rows is a list of (line_number, [cell, ...])."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(fileobj, read_only=True, data_only=True)
        except Exception as exc:
            raise ImportFileError(f"Could not open the Excel file: {exc}") from exc
        sheet = wb.worksheets[0]
        it = sheet.iter_rows(values_only=True)
        headers = list(next(it, []) or [])
        rows = [(i, list(r)) for i, r in enumerate(it, start=2) if any(c not in (None, "") for c in r)]
        wb.close()
        return headers, rows
    if name.endswith((".csv", ".txt")):
        raw = fileobj.read()
        if isinstance(raw, bytes):
            for encoding in ("utf-8-sig", "cp1252"):
                try:
                    raw = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ImportFileError("Could not decode the CSV file; save it as UTF-8.")
        try:
            dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(raw), dialect)
        headers = next(reader, [])
        rows = [(i, r) for i, r in enumerate(reader, start=2) if any(c.strip() for c in r)]
        return headers, rows
    raise ImportFileError("Unsupported file type; upload .csv or .xlsx.")


# ---------------------------------------------------------------- parsing cells

def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _parse(kind, value):
    if isinstance(value, str):
        value = value.strip()
    if kind == "text":
        return str(value)
    if kind == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        m = re.fullmatch(r"(\d{1,2})[-/ ]([A-Za-z]{3})[A-Za-z]*[-/ ](\d{4})", text)
        if m and m.group(2).lower() in MONTHS:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        raise ValueError("use YYYY-MM-DD or DD-Mon-YYYY (e.g. 2027-03-05 or 05-Mar-2027)")
    if kind in ("int", "float", "decimal"):
        text = re.sub(r"[,$\s]|(?<=\d)[Mm]$", "", str(value))
        try:
            if kind == "int":
                number = Decimal(text)
                if number != number.to_integral_value() or number < 0:
                    raise ValueError
                return int(number)
            if kind == "float":
                return float(text)
            return Decimal(text).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            raise ValueError("expected a number" if kind != "int" else "expected a whole number ≥ 0") from None
    if kind == "solubility":
        code = SOLUBILITY.get(str(value).lower().replace(" ", "_").replace("-", "_"))
        if not code:
            raise ValueError("expected one of " + ", ".join(label for _, label in Product.Solubility.choices))
        return code
    raise AssertionError(kind)


# ---------------------------------------------------------------- import

class _Lookups:
    def __init__(self, create, result):
        self.create = create
        self.result = result
        self.cache = {}

    def get(self, model, name):
        key = (model, name.lower())
        if key not in self.cache:
            obj = model.objects.filter(name__iexact=name).first()
            if obj is None and self.create:
                obj = model.objects.create(name=name)
                label = model._meta.verbose_name_plural
                self.result.lookups_created[label] = self.result.lookups_created.get(label, 0) + 1
            self.cache[key] = obj
        return self.cache[key]


def _validate(headers, rows, lookups, result):
    mapping = {}
    for idx, header in enumerate(headers):
        col = _canonical(header)
        if col and col not in mapping.values():
            mapping[idx] = col
        elif not _blank(header):
            result.ignored_columns.append(str(header))
    result.columns = list(mapping.values())
    missing = [c for c in KEY_COLUMNS if c not in result.columns]
    if missing:
        raise ImportFileError("Missing required column(s): " + ", ".join(missing))

    parsed = []
    for line, cells in rows:
        values = {col: cells[idx] if idx < len(cells) else None for idx, col in mapping.items()}
        errors = []
        record = {"line": line, "product": {}, "market": {}, "m2m": {}}
        for col in KEY_COLUMNS:
            if _blank(values.get(col)):
                errors.append(RowError(line, col, "required"))
        name = str(values.get("active_substance") or "").strip()
        record["active_substance"] = name
        for col, model in LOOKUP_COLUMNS.items():
            if col in values and not _blank(values[col]):
                obj = lookups.get(model, str(values[col]).strip())
                if obj is None:
                    errors.append(RowError(line, col, f"unknown {model._meta.verbose_name} '{values[col]}'"))
                record[col] = obj
        for group, columns in (("product", PRODUCT_COLUMNS), ("market", MARKET_COLUMNS)):
            for col, kind in columns.items():
                if col in values and not _blank(values[col]):
                    try:
                        record[group][col] = _parse(kind, values[col])
                    except ValueError as exc:
                        errors.append(RowError(line, col, f"'{values[col]}': {exc}"))
        for col, model in M2M_COLUMNS.items():
            if col in values and not _blank(values[col]):
                objs = []
                for part in [p.strip() for p in str(values[col]).split(";") if p.strip()]:
                    obj = lookups.get(model, part)
                    if obj is None:
                        errors.append(RowError(line, col, f"unknown {model._meta.verbose_name} '{part}'"))
                    objs.append(obj)
                record["m2m"][col] = objs
        record["errors"] = errors
        parsed.append(record)

    # A new product needs an indication from at least one of its rows.
    groups = {}
    for rec in parsed:
        if rec["active_substance"] and rec.get("dosage_form") is not None:
            groups.setdefault((rec["active_substance"].lower(), rec["dosage_form"].pk), []).append(rec)
    for (name, dosage_pk), recs in groups.items():
        indication = next((r["indication"] for r in recs if r.get("indication") is not None), None)
        for rec in recs:
            rec["group_indication"] = indication
        exists = Product.objects.filter(active_substance__iexact=name, dosage_form_id=dosage_pk).exists()
        if indication is None and not exists:
            for rec in recs:
                if "indication" not in {e.column for e in rec["errors"]}:
                    rec["errors"].append(RowError(rec["line"], "indication", "required for a new product"))
    return parsed


def _apply(parsed, result):
    products = {}
    for rec in parsed:
        key = (rec["active_substance"].lower(), rec["dosage_form"].pk)
        product = products.get(key)
        if product is None:
            product = Product.objects.filter(
                active_substance__iexact=rec["active_substance"], dosage_form=rec["dosage_form"]
            ).first()
            if product is None:
                product = Product.objects.create(
                    active_substance=rec["active_substance"], dosage_form=rec["dosage_form"],
                    indication=rec["group_indication"], **rec["product"],
                )
                product._import_state = "created"
                result.products_created += 1
            else:
                product._import_state = "seen"
            products[key] = product
        changed = False
        if rec.get("indication") is not None and product.indication_id != rec["indication"].pk:
            product.indication = rec["indication"]
            changed = True
        for col, value in rec["product"].items():
            if getattr(product, col) != value:
                setattr(product, col, value)
                changed = True
        if changed:
            product.save()
            if product._import_state == "seen":
                product._import_state = "updated"
                result.products_updated += 1
        for col, objs in rec["m2m"].items():
            getattr(product, col).set(objs)

        market, created = ProductCountry.objects.get_or_create(
            product=product, region=rec["region"], defaults=rec["market"]
        )
        if created:
            result.markets_created += 1
        else:
            dirty = [c for c, v in rec["market"].items() if getattr(market, c) != v]
            for col in dirty:
                setattr(market, col, rec["market"][col])
            if dirty:
                market.save(update_fields=dirty)
                result.markets_updated += 1
        result.rows_imported += 1


class _Rollback(Exception):
    pass


def import_file(fileobj, filename, *, dry_run=False, create_lookups=False, skip_invalid=False):
    result = ImportResult(dry_run=dry_run)
    headers, rows = read_rows(fileobj, filename)
    result.rows = len(rows)
    try:
        with transaction.atomic():
            lookups = _Lookups(create_lookups, result)
            parsed = _validate(headers, rows, lookups, result)
            for rec in parsed:
                result.errors.extend(rec["errors"])
            valid = [r for r in parsed if not r["errors"]]
            if result.errors and not skip_invalid:
                raise _Rollback  # also discards any lookups created during validation
            _apply(valid, result)
            if dry_run:
                raise _Rollback
            result.applied = True
    except _Rollback:
        if not dry_run:
            result.rows_imported = 0
            result.lookups_created = {}
    result.errors.sort(key=lambda e: e.row)
    return result


def template_csv():
    """Header row plus one example row, for users to fill in."""
    example = {
        "active_substance": "Examplevir", "dosage_form": "Tablet", "region": "USA", "indication": "HIV",
        "brand": "Exampra", "innovator": "Example Pharma", "therapeutic_category": "Antiviral",
        "strength": "50 mg", "xlogp": "2.1", "logp": "2.4", "molecular_weight": "455.3", "solubility": "Low",
        "revenue_musd": "120.5", "earliest_generic_launch": "2029-06-30", "marketing_exclusivity": "2028-12-31",
        "data_exclusivity": "2027-06-30", "main_patent_expiry": "2029-01-15", "patent_extension": "",
        "other_blocking_patent": "", "key_patents": "US1234567", "ftf_anda_filers": "3", "post_generic_6m": "0",
        "api_manufacturers": "4", "api_consumption_kg": "850", "suggested_strategy": "Monitor FTF activity",
        "keywords": "Paragraph IV; Long-acting", "excipients": "Magnesium stearate; Povidone",
    }
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(ALL_COLUMNS)
    writer.writerow([example.get(c, "") for c in ALL_COLUMNS])
    return buf.getvalue()
