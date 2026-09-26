"""Run the application's Alembic migrations from the local entry point."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from flowguard_api.config import get_settings


def upgrade_database() -> None:
    """Bring the configured database schema to the latest revision."""

    api_root = next(
        (
            parent
            for parent in Path(__file__).resolve().parents
            if (parent / "alembic.ini").is_file() and (parent / "migrations").is_dir()
        ),
        None,
    )
    if api_root is None:
        raise RuntimeError("找不到数据库迁移目录")
    alembic_file = api_root / "alembic.ini"
    if not alembic_file.is_file():
        raise RuntimeError(f"找不到数据库迁移配置: {alembic_file}")

    alembic_config = Config(str(alembic_file))
    alembic_config.set_main_option("script_location", str(api_root / "migrations"))
    alembic_config.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(alembic_config, "head")
