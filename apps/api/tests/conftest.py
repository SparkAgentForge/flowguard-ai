import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from flowguard_api.config import get_settings
from flowguard_api.models import Base


def pytest_configure(config: pytest.Config) -> None:
    # Application imports during collection must not use a developer's database.
    test_settings = pytest.MonkeyPatch()
    test_settings.setenv("FLOWGUARD_DATABASE_URL", "sqlite://")
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


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield testing_session
    finally:
        testing_session.close()


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
