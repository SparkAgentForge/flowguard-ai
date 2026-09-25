"""SQLAlchemy engine construction."""

from sqlalchemy import Engine, create_engine


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with settings suitable for SQLite and PostgreSQL."""

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def _configured_engine() -> Engine:
    # Import settings lazily so utility code can import the engine factory
    # without constructing the application configuration first.
    from flowguard_api.config import get_settings

    return create_database_engine(get_settings().database_url)


engine = _configured_engine()

