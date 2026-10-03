from django.db import migrations


DISCOVERY_QUERIES = (
    "topic:ai-agent",
    "topic:ai-agents",
    '"agent framework"',
    '"AI agent framework"',
    '"coding agent"',
    '"browser agent"',
    '"research agent"',
    '"multi agent"',
    '"multi-agent"',
    '"agent memory"',
    '"agent workflow"',
    '"computer use"',
    '"MCP agent"',
    '"model context protocol"',
    '"agent observability"',
    '"agent security"',
)


def seed_discovery_queries(apps, schema_editor) -> None:
    query_model = apps.get_model("repositories", "GitHubDiscoveryQuery")
    query_model.objects.bulk_create(
        [query_model(query=query) for query in DISCOVERY_QUERIES],
        ignore_conflicts=True,
    )


def remove_seeded_discovery_queries(apps, schema_editor) -> None:
    query_model = apps.get_model("repositories", "GitHubDiscoveryQuery")
    query_model.objects.filter(query__in=DISCOVERY_QUERIES).delete()


class Migration(migrations.Migration):
    dependencies = [("repositories", "0002_alter_repository_stars")]

    operations = [
        migrations.RunPython(seed_discovery_queries, remove_seeded_discovery_queries),
    ]
