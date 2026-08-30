#!/bin/bash

set -x

COLUMNS=180
export COLUMNS
# --reload is intentionally omitted: oslo.config is a singleton that cannot
# be re-initialised in the worker subprocess spawned by uvicorn --reload.
uvicorn --factory "main:create_app" --port 80 --host '0.0.0.0'
