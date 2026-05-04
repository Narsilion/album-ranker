from __future__ import annotations

import pytest

from album_ranker.settings import load_settings


def test_load_settings_validates_port(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALBUM_RANKER_PORT", "65536")

    with pytest.raises(SystemExit, match="ALBUM_RANKER_PORT must be between 1 and 65535"):
        load_settings()


def test_load_settings_validates_port_integer(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALBUM_RANKER_PORT", "not-a-port")

    with pytest.raises(SystemExit, match="ALBUM_RANKER_PORT must be an integer"):
        load_settings()


def test_load_settings_validates_model_name(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALBUM_RANKER_MODEL", "bad\nmodel")

    with pytest.raises(SystemExit, match="ALBUM_RANKER_MODEL must contain only printable characters"):
        load_settings()


def test_load_settings_strips_valid_model_name(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALBUM_RANKER_PORT", "8781")
    monkeypatch.setenv("ALBUM_RANKER_MODEL", " gpt-5-mini ")

    settings = load_settings()

    assert settings.port == 8781
    assert settings.model == "gpt-5-mini"
