from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from products.importer import ImportFileError, import_file, template_csv


class Command(BaseCommand):
    help = "Import products and per-market data from a CSV or Excel file (one row per product × region)."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", help="CSV or .xlsx file")
        parser.add_argument("--dry-run", action="store_true", help="Validate and report counts without saving.")
        parser.add_argument("--create-lookups", action="store_true",
                            help="Create unknown indications, dosage forms, regions, keywords and excipients.")
        parser.add_argument("--skip-invalid", action="store_true",
                            help="Import valid rows even if other rows have errors.")
        parser.add_argument("--template", metavar="OUT", help="Write a CSV template to OUT and exit.")

    def handle(self, *args, **opts):
        if opts["template"]:
            Path(opts["template"]).write_text(template_csv(), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Template written to {opts['template']}"))
            return
        if not opts["path"]:
            raise CommandError("Give a file path, or --template OUT.")
        path = Path(opts["path"])
        if not path.is_file():
            raise CommandError(f"No such file: {path}")
        try:
            with path.open("rb") as fh:
                result = import_file(fh, path.name, dry_run=opts["dry_run"],
                                     create_lookups=opts["create_lookups"], skip_invalid=opts["skip_invalid"])
        except ImportFileError as exc:
            raise CommandError(str(exc)) from exc

        if result.ignored_columns:
            self.stdout.write(self.style.WARNING("Ignored columns: " + ", ".join(result.ignored_columns)))
        for error in result.errors[:200]:
            self.stdout.write(self.style.ERROR(str(error)))
        if len(result.errors) > 200:
            self.stdout.write(self.style.ERROR(f"… and {len(result.errors) - 200} more"))
        style = self.style.SUCCESS if result.applied or (result.dry_run and not result.errors) else self.style.WARNING
        self.stdout.write(style(result.summary()))
        if result.errors and not opts["skip_invalid"]:
            raise CommandError("Nothing was imported because of the errors above "
                               "(fix them, or rerun with --skip-invalid / --create-lookups).")
