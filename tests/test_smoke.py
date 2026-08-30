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
_ext_db_session = _stub_module("aprsd_irc_extension.db.session")
_ext_db_session.get_session = mock.MagicMock(return_value=mock.MagicMock())
_ext_models = _stub_module("aprsd_irc_extension.db.models")
_ext_models.Channel = mock.MagicMock()
_ext_models.ChannelUsers = mock.MagicMock()

# uvicorn stub — only needed if not installed; setdefault means real uvicorn
# takes priority when present (CI installs it)
_stub_module("uvicorn")

# click: DO NOT stub — CI installs the real package, and httpx imports
# click.argument which a stub would be missing. The real click is always
# available in this project's deps.

# log stub
_log_mod = _stub_module("log")
_log_mod.setup_logging = lambda app, gunicorn=False: mock.MagicMock()

# ---------------------------------------------------------------------------
# Now we can safely import the app
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import main  # noqa: E402  (must come after stubs)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_client(tmp_path, minimal_config):
    """Return a TestClient for a freshly created app instance."""
    from fastapi.testclient import TestClient

    static_dir = tmp_path / "web" / "static"
    static_dir.mkdir(parents=True)
    tmpl_dir = tmp_path / "web" / "templates"
    tmpl_dir.mkdir(parents=True)
    # Minimal templates so Jinja2 doesn't blow up on the / and /about routes
    (tmpl_dir / "index.html").write_text(
        "<!doctype html><html><body>{{ channels|tojson }}</body></html>"
    )
    (tmpl_dir / "about.html").write_text(
        "<!doctype html><html><body>{{ aprsd_version }}</body></html>"
    )

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        app = main.create_app(config_file=minimal_config)
    finally:
        os.chdir(orig_cwd)

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# fetch_stats
# ---------------------------------------------------------------------------

class TestFetchStats:
    def test_returns_dict_with_time_and_stats(self, tmp_path):
        result = main.fetch_stats()
        assert "time" in result
        assert "stats" in result

    def test_reads_json_file_when_present(self, tmp_path):
        payload = {"APRSDStats": {"version": "3.0.0", "uptime": "1h"}}
        with mock.patch("main.os.path.exists", return_value=True):
            with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(payload))):
                result = main.fetch_stats()
        assert result["stats"] == payload

    def test_falls_back_when_no_json_file(self):
        with mock.patch("os.path.exists", return_value=False):
            result = main.fetch_stats()
        assert result["stats"] == {}  # StatsStore stub returns empty dict

    def test_time_key_is_formatted_string(self):
        result = main.fetch_stats()
        # Should look like "MM-DD-YYYY HH:MM:SS"
        import re
        assert re.match(r"\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}", result["time"])

    def test_bad_json_file_falls_through_to_next_candidate(self, tmp_path):
        """A corrupted statsstore.json should be skipped, not raise."""
        call_count = {"n": 0}

        def _exists(path):
            return True  # pretend all paths exist

        def _open(path, *a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First candidate returns bad JSON
                return mock.mock_open(read_data="not-json")()
            return mock.mock_open(read_data=json.dumps({"ok": True}))()

        with mock.patch("main.os.path.exists", side_effect=_exists):
            with mock.patch("builtins.open", side_effect=_open):
                result = main.fetch_stats()
        # Should not raise; returns the second file's data or the fallback
        assert "time" in result
        assert "stats" in result


# ---------------------------------------------------------------------------
# create_app / route tests
# ---------------------------------------------------------------------------

class TestCreateApp:
    def test_returns_fastapi_instance(self, tmp_path, minimal_config):
        from fastapi import FastAPI

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
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_stats_route_returns_time_and_stats(self, tmp_path, minimal_config):
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "time" in body
        assert "stats" in body

    def test_about_route_renders(self, tmp_path, minimal_config):
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/about")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_index_route_renders(self, tmp_path, minimal_config):
        # channels stub returns empty list by default
        _ext_models.Channel.get_all_channels.return_value = []
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_config_env_var_override(self, tmp_path, minimal_config):
        """APRS_IRC_CONFIG env var should be used as config path."""
        orig = os.environ.pop("APRS_IRC_CONFIG", None)
        os.environ["APRS_IRC_CONFIG"] = minimal_config
        try:
            static_dir = tmp_path / "web" / "static"
            static_dir.mkdir(parents=True)
            tmpl_dir = tmp_path / "web" / "templates"
            tmpl_dir.mkdir(parents=True)
            orig_cwd = os.getcwd()
            os.chdir(tmp_path)
            try:
                from fastapi import FastAPI
                app = main.create_app()  # no explicit config_file arg
                assert isinstance(app, FastAPI)
            finally:
                os.chdir(orig_cwd)
        finally:
            os.environ.pop("APRS_IRC_CONFIG", None)
            if orig is not None:
                os.environ["APRS_IRC_CONFIG"] = orig


# ---------------------------------------------------------------------------
# /messages route
# ---------------------------------------------------------------------------

class TestMessagesRoute:
    def _make_fake_message(self, text="hello", ts=1000.0):
        msg = mock.MagicMock()
        msg.to_json.return_value = json.dumps({
            "from_call": "WB4BOR",
            "message_text": text,
            "timestamp": ts,
        })
        return msg

    def test_returns_empty_list_for_unknown_channel(self, tmp_path, minimal_config):
        _ext_models.Channel.get_channel_by_name.return_value = None
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/messages/nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_messages_for_known_channel(self, tmp_path, minimal_config):
        msg = self._make_fake_message("test msg", ts=1700000000.0)
        ch = mock.MagicMock()
        ch.messages.limit.return_value = [msg]
        # Reset side_effect so return_value is used for bare name lookup
        _ext_models.Channel.get_channel_by_name.side_effect = None
        _ext_models.Channel.get_channel_by_name.return_value = ch
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/messages/lounge")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        # Route does result.append(m.to_json()) — FastAPI re-serialises the
        # string, so each element is a JSON string; parse it to get the dict.
        assert json.loads(data[0])["message_text"] == "test msg"

    def test_matches_channel_with_hash_prefix(self, tmp_path, minimal_config):
        """Request for 'wx' (no #) should fall back to looking up '#wx'."""
        msg = self._make_fake_message("via hash", ts=1700000001.0)
        ch = mock.MagicMock()
        ch.messages.limit.return_value = [msg]

        call_args = []

        def _get_by_name(name):
            call_args.append(name)
            # Only match the # form
            return ch if name == "#wx" else None

        _ext_models.Channel.get_channel_by_name.side_effect = _get_by_name
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/messages/wx")
        assert resp.status_code == 200
        # Confirm both lookup forms were attempted
        assert "wx" in call_args
        assert "#wx" in call_args
        assert json.loads(resp.json()[0])["message_text"] == "via hash"

    def test_empty_messages_returns_empty_list(self, tmp_path, minimal_config):
        ch = mock.MagicMock()
        ch.messages.limit.return_value = []
        _ext_models.Channel.get_channel_by_name.return_value = ch
        client = _make_client(tmp_path, minimal_config)
        resp = client.get("/messages/empty")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# /events SSE route
# The generator loops forever — we test the StreamingResponse object directly
# rather than going through TestClient (which would block consuming the body).
# ---------------------------------------------------------------------------

class TestEventsRoute:
    def _get_events_response(self, tmp_path, minimal_config):
        """Call the events endpoint function directly and return the response."""
        import asyncio as _asyncio

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

        # Find the events route handler registered on the app
        from fastapi.routing import APIRoute
        events_handler = None
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/events":
                events_handler = route.endpoint
                break
        assert events_handler is not None, "No /events route found"

        _ext_models.Channel.get_all_channels.return_value = []
        return _asyncio.run(events_handler())

    def test_events_returns_streaming_response(self, tmp_path, minimal_config):
        from fastapi.responses import StreamingResponse
        resp = self._get_events_response(tmp_path, minimal_config)
        assert isinstance(resp, StreamingResponse)

    def test_events_media_type_is_event_stream(self, tmp_path, minimal_config):
        resp = self._get_events_response(tmp_path, minimal_config)
        assert resp.media_type == "text/event-stream"

    def test_events_sets_no_cache_header(self, tmp_path, minimal_config):
        resp = self._get_events_response(tmp_path, minimal_config)
        assert resp.headers.get("cache-control") == "no-cache"

    def test_events_sets_accel_buffering_header(self, tmp_path, minimal_config):
        resp = self._get_events_response(tmp_path, minimal_config)
        assert resp.headers.get("x-accel-buffering") == "no"


# ---------------------------------------------------------------------------
# /admin auth
# ---------------------------------------------------------------------------

def _admin_conf(password):
    """Return a mock CONF.web object with admin_password set."""
    web = mock.MagicMock()
    web.admin_password = password
    conf = mock.MagicMock()
    conf.web = web
    return conf


class TestAdminAuth:
    def test_admin_no_password_configured_returns_503(self, tmp_path, minimal_config):
        # admin_password unset (None) → 503 when credentials ARE sent
        # (HTTPBasic returns 401 before require_admin runs if no credentials at all)
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf(None)):
            resp = client.get("/admin", auth=("any", "anything"))
        assert resp.status_code == 503

    def test_admin_wrong_password_returns_401(self, tmp_path, minimal_config):
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf("testpass")):
            resp = client.get("/admin", auth=("any", "wrongpassword"))
        assert resp.status_code == 401

    def test_admin_correct_password_returns_200(self, tmp_path, minimal_config):
        _ext_models.Channel.get_all_channels.return_value = []
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf("testpass")):
            resp = client.get("/admin", auth=("any", "testpass"))
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# /admin delete routes
# ---------------------------------------------------------------------------

class TestAdminDeleteRoutes:
    def test_delete_channel_unknown_returns_200_with_message(self, tmp_path, minimal_config):
        _ext_models.Channel.find_by_name = mock.MagicMock(return_value=None)
        _ext_models.Channel.get_all_channels.return_value = []
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf("testpass")):
            resp = client.post("/admin/channel/nosuchchan/delete", auth=("any", "testpass"))
        assert resp.status_code == 200
        assert "not found" in resp.text

    def test_delete_channel_known_commits_and_returns_200(self, tmp_path, minimal_config):
        fake_ch = mock.MagicMock()
        fake_ch.name = "#lounge"
        _ext_models.Channel.find_by_name = mock.MagicMock(return_value=fake_ch)
        _ext_models.Channel.get_all_channels.return_value = []
        fake_session = mock.MagicMock()
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf("testpass")), \
             mock.patch("aprsd_irc_extension.db.session.get_session", return_value=fake_session):
            resp = client.post("/admin/channel/%23lounge/delete", auth=("any", "testpass"))
        assert resp.status_code == 200
        fake_session.delete.assert_called_once_with(fake_ch)
        fake_session.commit.assert_called_once()

    def test_delete_user_no_auth_returns_401(self, tmp_path, minimal_config):
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf("testpass")):
            resp = client.post("/admin/channel/lounge/user/WB4BOR/delete")
        assert resp.status_code == 401

    def test_delete_user_known_removes_and_returns_200(self, tmp_path, minimal_config):
        fake_user = mock.MagicMock()
        fake_ch = mock.MagicMock()
        fake_ch.name = "#lounge"
        fake_ch.id = 1
        _ext_models.Channel.find_by_name = mock.MagicMock(return_value=fake_ch)
        _ext_models.Channel.get_all_channels.return_value = []
        fake_session = mock.MagicMock()
        fake_session.query.return_value.filter.return_value.first.return_value = fake_user
        client = _make_client(tmp_path, minimal_config)
        with mock.patch("main.CONF", _admin_conf("testpass")), \
             mock.patch("aprsd_irc_extension.db.session.get_session", return_value=fake_session):
            resp = client.post(
                "/admin/channel/%23lounge/user/WB4BOR/delete",
                auth=("any", "testpass"),
            )
        assert resp.status_code == 200
        fake_session.delete.assert_called_once_with(fake_user)
        fake_session.commit.assert_called_once()
