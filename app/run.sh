#!/bin/bash

set -x

COLUMNS=180
export COLUMNS
#cd /app
#pip install whitenoise
#pip freeze
#/usr/local/bin/gunicorn -w 6 --conf gunicorn_conf.py --bind '[::]:80' "main:create_app(config_file='config/aprsd_repeat.conf')"
#gunicorn -w 6 --conf gunicorn_conf.py --bind '[::]:80' "main:create_app(config_file='config/aprsd_listen.conf')"
uvicorn --reload --factory "main:create_app" --port 80 --host '0.0.0.0'
