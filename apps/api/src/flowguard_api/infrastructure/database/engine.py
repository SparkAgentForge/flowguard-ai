"""SQLAlchemy engine construction."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def create_database_engine(database_url: str) -> Engine:
    """Create a PostgreSQL engine for the configured application database."""

    if make_url(database_url).get_backend_name() != "postgresql":
        raise ValueError("FLOWGUARD_DATABASE_URL must use a PostgreSQL SQLAlchemy URL")
    return create_engine(database_url, pool_pre_ping=True)


def _configured_engine() -> Engine:
    # Import settings lazily so utility code can import the engine factory
    # without constructing the application configuration first.
    from flowguard_api.config import get_settings

    return create_database_engine(get_settings().database_url)


engine = _configured_engine()
