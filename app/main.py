import aprsd.conf.common
import click
import datetime
import json
import logging as python_logging
import requests
import sys

from aprslib import parse as aprs_parse
from cachetools import cached, TTLCache
from geojson import Feature, Point
from oslo_config import cfg
from aprsd_irc_extension import conf
from aprsd_irc_extension.db import session as db_session
from aprsd_irc_extension.db import models
from aprsd.threads import stats as stats_threads


from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
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
]

LOG = None
CONF.register_opts(web_opts, group="web")
API_KEY_HEADER = "X-Api-Key"
app = FastAPI(
    static_url_path="/static",
    static_folder="web/static",
    template_folder="web/templates"
)


def fetch_stats():
    stats_obj = stats_threads.StatsStore()
    stats_obj.load()
    now = datetime.datetime.now()
    time_format = "%m-%d-%Y %H:%M:%S"
    stats = {
        "time": now.strftime(time_format),
        "stats": stats_obj.data,
    }
    return stats


def create_app () -> FastAPI:
    global app, LOG

    #conf_file = utils.DEFAULT_CONFIG_FILE
    conf_file = "config/aprsd_irc.conf"
    config_file = ["--config-file", conf_file]

    log_level = "DEBUG"

    CONF(config_file, project='aprsd_irc', version="1.0.0")
    python_logging.captureWarnings(True)
    app = FastAPI()
    LOG = log.setup_logging(app, gunicorn=True)
    CONF.log_opt_values(LOG, python_logging.DEBUG)

    app.mount("/static", StaticFiles(directory="web/static"), name="static")
    templates = Jinja2Templates(directory="web/templates")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        aprsd_stats = fetch_stats()
        aprs_connection = (
            "APRS-IS Server: <a href='http://status.aprs2.net' >"
            "{}</a>".format(aprsd_stats["stats"]["APRSClientStats"]["server_string"])
        )

        version = aprsd_stats["stats"]["APRSDStats"]["version"]
        aprsd_version = aprsd_stats["stats"]["APRSDStats"]["version"]
        uptime = aprsd_stats["stats"]["APRSDStats"].get("uptime")

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
    return app

    @app.get("/messages/{channel}")
    async def messages(channel: str):
        ch = models.Channel.get_channel_by_name(channel)
        messages = []
        if ch:
            if ch.messages:
                for m in ch.messages.limit(50):
                    messages.append(m.to_json())

        return messages


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
    global app, LOG

    conf_file = config_file
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]

    app = create_app(config_file=config_file, log_level=log_level,
                     gunicorn=False)
    app.run(host="0.0.0.0", port=8080, debug=True)
