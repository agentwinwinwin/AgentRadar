import json

from django.core.management.base import BaseCommand

from apps.knowledge.services import RAGService
from apps.repositories.models import Repository


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("repository")
        parser.add_argument("question")

    def handle(self, *args, **options):
        repository = Repository.objects.get(full_name=options["repository"])
        self.stdout.write(
            json.dumps(
                RAGService().answer(repository.id, options["question"]),
                default=str,
                ensure_ascii=False,
            )
        )
