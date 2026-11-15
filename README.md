# LaunchScope

A Django app for generic-pharma launch intelligence: search products by market, exclusivity and patent
dates, revenue and API supply, chart the results, and track portfolios. All bundled data is synthetic:
every product, company and figure comes from the `seed_demo` command.

## Quick start

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo          # 400 synthetic products, demo org + user
.venv/bin/python manage.py runserver 8010
```

Local demo login (development only): **demo / demo-pass-123** (change with `seed_demo --password …`).
The demo user is staff, so `/admin/` works for editing reference data and products.

Run tests: `.venv/bin/python manage.py test`

## Apps

| App | Responsibility |
|---|---|
| `orgs` | Organisation, user profile, free/full access tier with a time-boxed full-access window, profile & password change |
| `reference` | Colour-coded lookups: Indication, Region, DosageForm, Year, Excipient, Keyword (`/ref/<table>/`) |
| `products` | Product, ProductCountry (per-market revenue, exclusivity, patents, FTF/ANDA, API supply), Portfolio & Play Area lists with notes |
| `analysis` | Parameter search (`analysis/search.py`), JSON data endpoint, chart aggregates, saved searches, single-product detail |
| `reports` | Start → poll → download CSV reports (runs inline; swap `_run` onto Celery/RQ when needed) |
| `dashboard` | Tiles, upcoming launch / exclusivity panels, launch ticker |

## Endpoints

```
POST /analysis/getanalysisdata/             search → {data:{IsRepSearchSet, numproducts, repdata, charts}}
GET  /analysis/getproductnames/?term=        autocomplete
GET  /analysis/getsinglepdt/<market_id>/     product detail across markets
GET  /analysis/savedsearch/<id>/             + create/, <id>/update/, <id>/delete/
POST /newproducts/add/                       add market_ids[] to a portfolio/play area
POST /newproducts/item/<id>/note/            set notes      POST …/delete/  remove
POST /myreports/generatereports/             → task_id; GET reports/status/<id>/, reports/download/<id>/
```

## Frontend

Server-rendered templates on AdminLTE 4 / Bootstrap 5 (dark), jQuery 3.7, DataTables 2.3 (select, Excel/CSV
export), Select2, Chart.js 4 and SweetAlert2, all from pinned CDN URLs in `templates/base.html`.
Page logic lives in `static/js/analysis.js` and `static/js/lists.js`.

## Importing data

One row per product × region, from CSV or Excel (first sheet). Required columns: `active_substance`,
`dosage_form`, `region`, plus `indication` for new products. All other columns are optional; headers are
matched loosely, and the CSV from **My Reports** is accepted as-is, so you can export, edit and re-import.

- Products are matched on substance + dosage form, markets on product + region (case-insensitive).
- Empty cells never clear stored values; only columns present in the file are written.
- `keywords` / `excipients` are `;`-separated and replace the product's set when filled.
- Dates: `YYYY-MM-DD`, `DD-Mon-YYYY`, or native Excel dates. Numbers may include `$`, `,` and a trailing `M`.
- Any error blocks the whole file unless you choose to skip invalid rows.

```bash
.venv/bin/python manage.py import_products --template template.csv      # blank template with an example row
.venv/bin/python manage.py import_products data.xlsx --dry-run          # validate + exact counts, no writes
.venv/bin/python manage.py import_products data.xlsx --create-lookups   # also add unknown regions/indications/…
.venv/bin/python manage.py import_products data.csv --skip-invalid      # import good rows, list the rest
```

Staff users get the same flow in the browser under **Import data** (`/newproducts/import/`): upload →
preview with per-row errors → confirm. Logic lives in `products/importer.py`.

## Not yet built

- Remaining chart panels from the reference (post-generic tracker, global API consumption, first-wave launchers).
- Excipient/keyword editing per product from the Analysis page (admin covers it for now).
- Production settings: `SECRET_KEY`/`DEBUG` from environment, Postgres, static file serving.
