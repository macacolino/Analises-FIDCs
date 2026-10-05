#!/usr/bin/env bash
# Sobe a API (que também serve as telas) em segundo plano. Log em /tmp/fidc-api.log
cd "$(dirname "$0")/../backend"
if [ ! -f ../data/fidc.duckdb ]; then python -m fidc.etl; fi
nohup python -m uvicorn fidc.api.main:app --host 0.0.0.0 --port 8000 > /tmp/fidc-api.log 2>&1 &
