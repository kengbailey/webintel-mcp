"""Tests for the YOUTUBE_PROXY_URL override (see src/core/config.py).

Semantics: unset inherits PROXY_URL; set-but-empty forces a direct
connection; a value wins outright.
"""
import importlib

import src.core.config as config_module


def _reload_config(monkeypatch, proxy_url, youtube_proxy_url):
    monkeypatch.delenv('PROXY_URL', raising=False)
    monkeypatch.delenv('YOUTUBE_PROXY_URL', raising=False)
    if proxy_url is not None:
        monkeypatch.setenv('PROXY_URL', proxy_url)
    if youtube_proxy_url is not None:
        monkeypatch.setenv('YOUTUBE_PROXY_URL', youtube_proxy_url)
    return importlib.reload(config_module).SearchConfig


def test_unset_inherits_proxy_url(monkeypatch):
    cfg = _reload_config(monkeypatch, 'http://vpn:8888', None)
    assert cfg.YOUTUBE_PROXY_URL == 'http://vpn:8888'


def test_empty_forces_direct(monkeypatch):
    cfg = _reload_config(monkeypatch, 'http://vpn:8888', '')
    assert cfg.YOUTUBE_PROXY_URL is None


def test_value_overrides(monkeypatch):
    cfg = _reload_config(monkeypatch, 'http://vpn:8888', 'http://home:8899')
    assert cfg.YOUTUBE_PROXY_URL == 'http://home:8899'


def test_all_unset_is_direct(monkeypatch):
    cfg = _reload_config(monkeypatch, None, None)
    assert cfg.YOUTUBE_PROXY_URL is None
