from django.db import migrations


def _enable_pg_extensions(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")


def _disable_pg_extensions(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    schema_editor.execute("DROP EXTENSION IF EXISTS pg_stat_statements;")
    schema_editor.execute("DROP EXTENSION IF EXISTS vector;")


class Migration(migrations.Migration):
    """Enable optional Postgres extensions.

    In CI/prod we use Postgres, but local/test runs may use SQLite.
    Keep this migration portable by no-op'ing on non-Postgres backends.
    """

    dependencies = []

    operations = [
        migrations.RunPython(_enable_pg_extensions, reverse_code=_disable_pg_extensions),
    ]
