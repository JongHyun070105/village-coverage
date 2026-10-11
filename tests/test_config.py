from __future__ import annotations

from scripts import api_smoke_test


def test_empty_environment_value_overrides_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("CONFIG_VALUE=from-file\n", encoding="utf-8")
    monkeypatch.setattr(api_smoke_test, "ROOT", tmp_path)
    monkeypatch.delenv("VILLAGE_COVERAGE_TEST_MODE", raising=False)
    monkeypatch.setenv("CONFIG_VALUE", "")

    assert api_smoke_test._load_config("CONFIG_VALUE") == ""


def test_test_mode_does_not_load_unset_values_from_dotenv(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("CONFIG_VALUE=from-file\n", encoding="utf-8")
    monkeypatch.setattr(api_smoke_test, "ROOT", tmp_path)
    monkeypatch.delenv("CONFIG_VALUE", raising=False)
    monkeypatch.setenv("VILLAGE_COVERAGE_TEST_MODE", "true")

    assert api_smoke_test._load_config("CONFIG_VALUE") == ""
