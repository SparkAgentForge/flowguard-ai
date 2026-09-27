import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from flowguard_api.config import get_settings
from flowguard_api.models import Base


def _test_database_url() -> str:
    database_url = os.environ.get("FLOWGUARD_TEST_DATABASE_URL", "").strip()
    if not database_url:
        raise pytest.UsageError(
            "API tests require FLOWGUARD_TEST_DATABASE_URL pointing to a dedicated "
            "PostgreSQL database."
        )
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or url.database != "flowguard_test":
        raise pytest.UsageError(
            "FLOWGUARD_TEST_DATABASE_URL must point to the dedicated PostgreSQL "
            "database named flowguard_test."
        )
    return database_url


def _reset_database(engine) -> None:
    # The test database must be dedicated to the test run. Resetting its public
    # schema keeps each test isolated without relying on an embedded database.
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def pytest_configure(config: pytest.Config) -> None:
    # Application imports during collection must use the explicitly isolated
    # PostgreSQL test database rather than a developer's configured database.
    database_url = _test_database_url()
    test_settings = pytest.MonkeyPatch()
    test_settings.setenv("FLOWGUARD_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config.add_cleanup(test_settings.undo)


@pytest.fixture(autouse=True)
def isolate_test_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLOWGUARD_INFERENCE_PROVIDER", "mock")
    monkeypatch.setenv("FLOWGUARD_SOP_EXTRACTOR_PROVIDER", "rule_based")
    monkeypatch.setenv("FLOWGUARD_OBJECT_STORAGE_ENDPOINT", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_postgres_database():
    engine = create_engine(_test_database_url(), pool_pre_ping=True)
    _reset_database(engine)
    yield
    _reset_database(engine)
    engine.dispose()


@pytest.fixture
def session() -> Session:
    engine = create_engine(_test_database_url(), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield testing_session
    finally:
        testing_session.close()
        engine.dispose()


@pytest.fixture
def client(session: Session) -> TestClient:
    from flowguard_api.application import app
    from flowguard_api.infrastructure.database import get_session

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
