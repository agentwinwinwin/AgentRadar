from django.db import migrations, models


def create_postgresql_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX repo_cat_stars_idx ON repositories "
            "(category, is_disabled, is_fork, stars DESC NULLS LAST)"
        )


def drop_postgresql_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS repo_cat_stars_idx")


class Migration(migrations.Migration):
    dependencies = [("repositories", "0006_production_query_indexes")]
    operations = [
        migrations.RemoveIndex(model_name="repository", name="repo_cat_stars_idx"),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(create_postgresql_index, drop_postgresql_index)],
            state_operations=[
                migrations.AddIndex(
                    model_name="repository",
                    index=models.Index(
                        models.F("category"),
                        models.F("is_disabled"),
                        models.F("is_fork"),
                        models.OrderBy(models.F("stars"), descending=True, nulls_last=True),
                        name="repo_cat_stars_idx",
                    ),
                )
            ],
        ),
    ]
