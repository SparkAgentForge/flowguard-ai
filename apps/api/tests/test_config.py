import pytest
from pydantic import ValidationError

from flowguard_api.config import Settings


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLOWGUARD_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert any(
        item["loc"] == ("database_url",) and item["type"] == "missing"
        for item in error.value.errors()
    )


@pytest.mark.parametrize("database_url", ["", "   "])
def test_database_url_cannot_be_blank(database_url: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(database_url=database_url, _env_file=None)

    assert any(item["loc"] == ("database_url",) for item in error.value.errors())


def test_database_url_uses_explicit_configuration() -> None:
    database_url = "postgresql+pg8000://test:test@localhost:5432/test"

    assert Settings(database_url=database_url, _env_file=None).database_url == database_url
