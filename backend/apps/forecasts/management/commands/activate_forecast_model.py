from django.core.management.base import BaseCommand, CommandError

from apps.forecasts.services import ModelActivationService


class Command(BaseCommand):
    help = "Explicitly activate a validated model that satisfies all thresholds."

    def add_arguments(self, parser):
        parser.add_argument("model_version")

    def handle(self, *args, **options):
        try:
            model = ModelActivationService().activate(options["model_version"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"activated {model.model_version}")
