"""Smoke tests for the aprs-irc-website FastAPI application.

These tests mock out all heavy external dependencies (aprsd, oslo.config,
aprsd_irc_extension) so they run fast in CI with no special infrastructure.
"""
import json
import os
import sys
import types
import unittest.mock as mock

# ---------------------------------------------------------------------------
# Build lightweight stubs for every hard-to-install dependency before any
# app import happens.  This keeps CI simple — no aprsd wheel required.
# ---------------------------------------------------------------------------


def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# oslo.config stub
_oslo_cfg = _stub_module("oslo_config")
_oslo_cfg_cfg = _stub_module("oslo_config.cfg")


class _FakeCONF:
    """Minimal oslo.config CONF stand-in."""

    def __call__(self, *a, **kw):
        pass

    def register_group(self, *a, **kw):
        pass

    def register_opts(self, *a, **kw):
        pass

    def log_opt_values(self, *a, **kw):
        pass


_CONF_instance = _FakeCONF()
_oslo_cfg_cfg.CONF = _CONF_instance
_oslo_cfg_cfg.OptGroup = lambda *a, **kw: object()
_oslo_cfg_cfg.StrOpt = lambda *a, **kw: object()
_oslo_cfg_cfg.IntOpt = lambda *a, **kw: object()

# aprsd stubs
_aprsd = _stub_module("aprsd")
_aprsd_conf = _stub_module("aprsd.conf")
_aprsd_conf_common = _stub_module("aprsd.conf.common")
_aprsd_threads = _stub_module("aprsd.threads")
_aprsd_stats = _stub_module("aprsd.threads.stats")


class _FakeStatsStore:
    data = {}

    def load(self):
        pass


_aprsd_stats.StatsStore = _FakeStatsStore

# aprsd_irc_extension stubs
_ext = _stub_module("aprsd_irc_extension")
_ext_conf = _stub_module("aprsd_irc_extension.conf")
_ext_db = _stub_module("aprsd_irc_extension.db")
_ext_models = _stub_module("aprsd_irc_extension.db.models")
_ext_models.Channel = mock.MagicMock()

# uvicorn stub
_stub_module("uvicorn")

# click stub — needs .command(), .option(), etc.
_click = types.ModuleType("click")
_click.command = lambda *a, **kw: (lambda f: f)
_click.option  = lambda *a, **kw: (lambda f: f)
_click.version_option = lambda *a, **kw: (lambda f: f)
_click.Choice  = lambda *a, **kw: None
sys.modules.setdefault("click", _click)

# log stub
_log_mod = _stub_module("log")
_log_mod.setup_logging = lambda app, gunicorn=False: mock.MagicMock()

# ---------------------------------------------------------------------------
# Now we can safely import the app
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import main  # noqa: E402  (must come after stubs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchStats:
    def test_returns_dict_with_time_and_stats(self, tmp_path):
        result = main.fetch_stats()
        assert "time" in result
        assert "stats" in result

    def test_reads_json_file_when_present(self, tmp_path):
        payload = {"APRSDStats": {"version": "3.0.0", "uptime": "1h"}}
        # Patch exists() so the *first* candidate path (/config/statsstore.json) matches,
        # and patch open() to return our payload.
        with mock.patch("main.os.path.exists", return_value=True):
            with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(payload))):
                result = main.fetch_stats()

        assert result["stats"] == payload

    def test_falls_back_when_no_json_file(self):
        with mock.patch("os.path.exists", return_value=False):
            result = main.fetch_stats()
        assert result["stats"] == {}  # StatsStore stub returns empty dict


class TestCreateApp:
    def test_returns_fastapi_instance(self, tmp_path, minimal_config):
        from fastapi import FastAPI

        # Stub static/template directories so StaticFiles doesn't fail.
        static_dir = tmp_path / "web" / "static"
        static_dir.mkdir(parents=True)
        tmpl_dir = tmp_path / "web" / "templates"
        tmpl_dir.mkdir(parents=True)

        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            app = main.create_app(config_file=minimal_config)
        finally:
            os.chdir(orig_cwd)

        assert isinstance(app, FastAPI)

    def test_health_route_exists(self, tmp_path, minimal_config):
        from fastapi.testclient import TestClient

        static_dir = tmp_path / "web" / "static"
        static_dir.mkdir(parents=True)
        tmpl_dir = tmp_path / "web" / "templates"
        tmpl_dir.mkdir(parents=True)

        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            app = main.create_app(config_file=minimal_config)
            client = TestClient(app)
            resp = client.get("/health")
        finally:
            os.chdir(orig_cwd)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
