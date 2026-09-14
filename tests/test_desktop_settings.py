import json
import sys

from src.desktop.settings import load_theme_preference, save_theme_preference, settings_path


def test_theme_settings_default_validate_and_round_trip(tmp_path, monkeypatch):
    target = tmp_path / "portable" / "depviz-settings.json"
    monkeypatch.setenv("DEPVIZ_SETTINGS_PATH", str(target))
    assert settings_path() == target
    assert load_theme_preference() == "system"

    target.parent.mkdir(parents=True)
    target.write_text('{"theme": "unknown"}', encoding="utf-8")
    assert load_theme_preference() == "system"
    target.write_text("not json", encoding="utf-8")
    assert load_theme_preference() == "system"

    assert save_theme_preference("light") == target
    assert json.loads(target.read_text(encoding="utf-8")) == {"theme": "light"}
    assert load_theme_preference() == "light"


def test_unknown_theme_cannot_be_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPVIZ_SETTINGS_PATH", str(tmp_path / "settings.json"))
    try:
        save_theme_preference("sepia")
    except ValueError as error:
        assert "sepia" in str(error)
    else:
        raise AssertionError("An unknown theme should be rejected")


def test_frozen_application_keeps_settings_beside_executable(tmp_path, monkeypatch):
    monkeypatch.delenv("DEPVIZ_SETTINGS_PATH", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Depviz" / "Depviz.exe"))
    assert settings_path() == tmp_path / "Depviz" / "depviz-settings.json"
