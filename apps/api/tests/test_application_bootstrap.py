from sqlalchemy import create_engine, inspect

from flowguard_api.config import get_settings
from flowguard_api.infrastructure.database.migrations import upgrade_database


def test_upgrade_database_uses_configured_url_from_any_working_directory(
    tmp_path, monkeypatch
):
    database = tmp_path / "flowguard.db"
    monkeypatch.setenv("FLOWGUARD_DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    try:
        upgrade_database()
        tables = inspect(create_engine(f"sqlite:///{database}")).get_table_names()
        assert "documents" in tables
        assert "alembic_version" in tables
    finally:
        get_settings.cache_clear()
