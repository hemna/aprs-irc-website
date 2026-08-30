import asyncio
import click
import datetime
import json
import logging as python_logging
import os
import secrets
import uvicorn

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from oslo_config import cfg
from aprsd_irc_extension.db import models
from aprsd.threads import stats as stats_threads

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import log
import utils

CONF = cfg.CONF
grp = cfg.OptGroup('web')
cfg.CONF.register_group(grp)
web_opts = [
    cfg.StrOpt('host_ip',
               default='0.0.0.0',
               help='The hostname/ip address to listen on'
               ),
    cfg.IntOpt('host_port',
               default=80,
               help='The port to listen on for requests'
               ),
    cfg.StrOpt('haminfo_ip',
               default='0.0.0.0',
               help='The hostname/ip address to haminfo api'
               ),
    cfg.StrOpt('haminfo_port',
               default='8043',
               help='The haminfo api IP port'
               ),
    cfg.StrOpt('aprsd_ip',
               default='0.0.0.0',
               help='The hostname/ip address to aprsd instance',
               ),
    cfg.StrOpt('aprsd_port',
               default='8043',
               help='The APRSD api IP port'
               ),
    cfg.StrOpt('admin_password',
               default=None,
               help='Password for the /admin interface. If unset, admin routes return 503.',
               secret=True,
               ),
]

LOG = None
CONF.register_opts(web_opts, group="web")
API_KEY_HEADER = "X-Api-Key"


def fetch_stats():
    now = datetime.datetime.now()
    time_format = "%m-%d-%Y %H:%M:%S"
    _log = LOG or python_logging.getLogger(__name__)

    # Prefer the JSON stats file (written by aprsd; more reliable than pickle).
    # Check both the shared /config mount and the local config/ directory.
    for stats_json_path in ("/config/statsstore.json", "config/statsstore.json"):
        if os.path.exists(stats_json_path):
            try:
                with open(stats_json_path) as f:
                    data = json.load(f)
                return {
                    "time": now.strftime(time_format),
                    "stats": data,
                }
            except Exception as exc:
                # Log and continue — try the next candidate path (closes #7).
                _log.warning("Failed to read stats from %s: %s", stats_json_path, exc)

    # Fall back to the StatsStore pickle
    try:
        stats_obj = stats_threads.StatsStore()
        stats_obj.load()
        return {
            "time": now.strftime(time_format),
            "stats": stats_obj.data,
        }
    except Exception as exc:
        _log.error("fetch_stats: all sources failed — returning empty stats. Cause: %s", exc)
        return {
            "time": now.strftime(time_format),
            "stats": {},
        }


def create_app(config_file: str = None) -> FastAPI:
    global LOG

    # Config resolution order (closes #3):
    #   1. explicit argument
    #   2. APRS_IRC_TEST_CONFIG env var (used by tests)
    #   3. <app-dir>/config/aprsd_irc.conf  (path relative to *this file*, not CWD)
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    _default_conf = os.path.join(_app_dir, "config", "aprsd_irc.conf")
    conf_file = (
        config_file
        or os.environ.get("APRS_IRC_CONFIG")       # production override
        or os.environ.get("APRS_IRC_TEST_CONFIG")  # CI/test override
        or _default_conf
    )
    _config_args = ["--config-file", conf_file]

    CONF(_config_args, project='aprsd_irc', version="1.0.0")
    python_logging.captureWarnings(True)
    app = FastAPI()
    LOG = log.setup_logging(app, gunicorn=True)
    CONF.log_opt_values(LOG, python_logging.DEBUG)

    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(_app_dir, "web", "static")),
        name="static",
    )
    templates = Jinja2Templates(directory=os.path.join(_app_dir, "web", "templates"))

    security = HTTPBasic()

    def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
        password = CONF.web.admin_password
        if not password:
            raise HTTPException(status_code=503, detail="Admin interface not configured")
        ok = secrets.compare_digest(
            credentials.password.encode("utf-8"),
            password.encode("utf-8"),
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
                headers={"WWW-Authenticate": "Basic"},
            )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        aprsd_stats = fetch_stats()
        stats_data = aprsd_stats.get("stats", {})
        aprs_client = stats_data.get("APRSClientStats", {})
        server_string = aprs_client.get("server_string", "unknown")
        aprs_connection = (
            "APRS-IS Server: <a href='http://status.aprs2.net' >"
            "{}</a>".format(server_string)
        )

        aprsd_stats_data = stats_data.get("APRSDStats", {})
        version = aprsd_stats_data.get("version", "unknown")
        aprsd_version = version
        uptime = aprsd_stats_data.get("uptime")

        channels = models.Channel.get_all_channels()
        channels_json = []
        for ch in channels:
            ch_json = ch.to_json()
            ch_json["messages"] = []
            for m in ch.messages.limit(50):
                pkt_json = json.loads(m.packet.to_json())
                ch_json["messages"].append(pkt_json)
            channels_json.append(ch_json)

        return templates.TemplateResponse(
            request=request, name="index.html",
            context={
                "initial_stats": aprsd_stats,
                "aprs_connection": aprs_connection,
                "callsign": "IRC",
                "version": version,
                "uptime": uptime,
                "aprsd_version": aprsd_version,
                "channels": channels_json,
            }
        )

    @app.get("/stats")
    async def stats():
        return fetch_stats()

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @app.get("/about", response_class=HTMLResponse)
    async def about(request: Request):
        aprsd_stats = fetch_stats()
        stats_data = aprsd_stats.get("stats", {})
        aprsd_stats_data = stats_data.get("APRSDStats", {})
        version = aprsd_stats_data.get("version", "unknown")
        return templates.TemplateResponse(
            request=request, name="about.html",
            context={"aprsd_version": version},
        )

    @app.get("/messages/{channel}")
    async def messages(channel: str):
        # Channel names may be stored with a leading # — match both forms
        ch = models.Channel.get_channel_by_name(channel) or \
             models.Channel.get_channel_by_name('#' + channel)
        result = []
        if ch and ch.messages:
            for m in ch.messages.limit(50):
                result.append(m.to_json())
        return result

    @app.get("/events")
    async def events():
        """Server-Sent Events stream — pushes new messages to the client.

        The client opens one persistent EventSource('/events').  Every 2 s the
        server checks each channel for messages newer than the last-seen
        timestamp and emits a named SSE event per channel:

            event: lounge
            data: [{"from_call": "WB4BOR", "message_text": "hello", ...}]

        Closes gracefully when the client disconnects.
        """
        async def generator():
            # Track the newest timestamp we have sent per channel name (no #).
            last_ts: dict[str, float] = {}

            # Seed with current newest so we only push *new* messages.
            try:
                for ch in models.Channel.get_all_channels():
                    name = ch.name.lstrip('#')
                    newest = max(
                        (m.timestamp for m in ch.messages if hasattr(m, 'timestamp')),
                        default=0,
                    )
                    last_ts[name] = newest
            except Exception:
                pass

            while True:
                await asyncio.sleep(2)
                try:
                    for ch in models.Channel.get_all_channels():
                        name = ch.name.lstrip('#')
                        cutoff = last_ts.get(name, 0)
                        new_msgs = [
                            m for m in ch.messages
                            if hasattr(m, 'timestamp') and m.timestamp > cutoff
                        ]
                        if not new_msgs:
                            continue
                        last_ts[name] = max(m.timestamp for m in new_msgs)
                        payload = json.dumps([json.loads(m.to_json()) for m in new_msgs])
                        yield f"event: {name}\ndata: {payload}\n\n"
                except Exception:
                    # DB may be briefly unavailable — skip this tick
                    pass

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering
            },
        )

    @app.get("/admin", response_class=HTMLResponse)
    async def admin(request: Request, _=Depends(require_admin)):
        channels = models.Channel.get_all_channels()
        return templates.TemplateResponse(
            request=request, name="admin.html",
            context={"channels": channels},
        )

    @app.post("/admin/channel/{channel_name}/delete", response_class=HTMLResponse)
    async def admin_delete_channel(
        request: Request,
        channel_name: str,
        _=Depends(require_admin),
    ):
        from aprsd_irc_extension.db import session as db_session
        session = db_session.get_session()
        ch = (models.Channel.find_by_name(session, channel_name) or
              models.Channel.find_by_name(session, '#' + channel_name))
        message = f"Channel {channel_name} not found."
        if ch:
            session.delete(ch)
            session.commit()
            message = f"Channel {ch.name} deleted."
        channels = models.Channel.get_all_channels()
        return templates.TemplateResponse(
            request=request, name="admin.html",
            context={"channels": channels, "message": message},
        )

    @app.post("/admin/channel/{channel_name}/user/{callsign}/delete", response_class=HTMLResponse)
    async def admin_delete_user(
        request: Request,
        channel_name: str,
        callsign: str,
        _=Depends(require_admin),
    ):
        from aprsd_irc_extension.db import session as db_session
        from aprsd_irc_extension.db.models import ChannelUsers
        session = db_session.get_session()
        ch = (models.Channel.find_by_name(session, channel_name) or
              models.Channel.find_by_name(session, '#' + channel_name))
        message = f"User {callsign} or channel {channel_name} not found."
        if ch:
            user_obj = session.query(ChannelUsers).filter(
                ChannelUsers.channel_id == ch.id,
                ChannelUsers.user == callsign,
            ).first()
            if user_obj:
                session.delete(user_obj)
                session.commit()
                message = f"Removed {callsign} from {ch.name}."
        channels = models.Channel.get_all_channels()
        return templates.TemplateResponse(
            request=request, name="admin.html",
            context={"channels": channels, "message": message},
        )

    return app


@click.command()
@click.option(
    "-c",
    "--config-file",
    "config_file",
    show_default=True,
    default=utils.DEFAULT_CONFIG_FILE,
    help="The aprsd config file to use for options.",
)
@click.option(
    "--log-level",
    "log_level",
    default="DEBUG",
    show_default=True,
    type=click.Choice(
        ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        case_sensitive=False,
    ),
    show_choices=True,
    help="The log level to use for aprsd.log",
)
@click.version_option()
def main(config_file, log_level):
    # Closes #4: FastAPI apps don't have .run(); use uvicorn directly.
    create_app(config_file=config_file)
    uvicorn.run(
        "main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8080,
        log_level=log_level.lower(),
        reload=False,
    )
