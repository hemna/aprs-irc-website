#!/bin/bash

docker compose down && docker build -t hemna6969/wxnow-website:latest . && docker compose up -d
