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
from aprsd.rpc import client as aprsd_rpc_client
from aprsd_irc_extension import conf
from aprsd_irc_extension.db import session as db_session
from aprsd_irc_extension.db import models


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
CONF.register_opts(aprsd.conf.common.rpc_opts, group="rpc_settings")
API_KEY_HEADER = "X-Api-Key"
app = FastAPI(
    static_url_path="/static",
    static_folder="web/static",
    template_folder="web/templates"
)


def fetch_stats():
    stats = None
    try:
        stats = aprsd_rpc_client.RPCClient().get_stats_dict()
    except Exception as ex:
        LOG.error(ex)

    if not stats:
        stats = {
            "aprsd": {
                "seen_list": [],
                "version": "unknown",
            },
            "aprs-is": {"server": ""},
            "messages": {
                "sent": 0,
                "received": 0,
            },
            "email": {
                "sent": 0,
                "received": 0,
            },
            "seen_list": {
                "sent": 0,
                "received": 0,
            },
            "repeat": {
                "version": "unknown",
            }
        }
    #LOG.debug(f"stats {stats}")
    stats['repeat'] = {'version': 'unknown'}
    if "aprsd" in stats:
        if "watch_list" in stats["aprsd"]:
            del stats["aprsd"]["watch_list"]
    if "email" in stats:
        del stats["email"]
    if "messages" in stats:
        del stats["messages"]
    if 'repeat' not in stats:
        stats['repeat'] = {'version':'dev'}

    if "aprsd" in stats:
        if "seen_list" in stats["aprsd"] and "REPEAT" in stats["aprsd"]["seen_list"]:
            del stats["aprsd"]["seen_list"]["REPEAT"]

        seen_list = stats["aprsd"]["seen_list"]
        for call in seen_list:
            # add a ts 2021-11-01 16:18:11.631723
            date = datetime.datetime.strptime(seen_list[call]['last'], "%Y-%m-%d %H:%M:%S.%f")
            seen_list[call]["ts"] = int(datetime.datetime.timestamp(date))
    return stats


@cached(cache=TTLCache(maxsize=40960, ttl=6), info=True)
def _get_wx_stations():
    url = f"http://{CONF.web.haminfo_ip}:{CONF.web.haminfo_port}/wxstations"
    LOG.debug(f"Fetching {url}")
    stations = []
    try:
        headers = {API_KEY_HEADER: CONF.web.api_key}
        LOG.debug(f"headers {headers}")
        response = requests.get(url=url,
                                headers=headers,
                                timeout=60)
        if response.status_code == 200:
            json_record = response.json()

            for entry in json_record:
                #LOG.info(entry)
                point = Point((entry['longitude'], entry['latitude']))
                marker = Feature(geometry=point,
                                 id=entry['id'],
                                 properties=entry
                                 )
                stations.append(marker)
                # self.cs.print(entry)
        else:
            LOG.error(response)
            return None

    except Exception as ex:
        LOG.error(ex)
        return None

    LOG.warning(f"Size {len(stations)}")
    return stations


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
        LOG.debug(aprsd_stats)
        aprs_connection = (
            "APRS-IS Server: <a href='http://status.aprs2.net' >"
            "{}</a>".format(aprsd_stats["aprs-is"]["server"])
        )

        version = aprsd_stats["repeat"]["version"]
        aprsd_version = aprsd_stats["aprsd"]["version"]
        uptime = aprsd_stats["aprsd"].get("uptime")

        channels = models.Channel.get_all_channels()
        channels_json = []
        for ch in channels:
            ch_json = ch.to_json()
            ch_json["messages"] = []
            for m in ch.messages.limit(50):
                pkt_json = json.loads(m.packet.json)
                ch_json["messages"].append(pkt_json)
            ch_json["messages"].reverse()
            channels_json.append(ch_json)
        LOG.debug(channels_json)

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
                messages.reverse()

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
