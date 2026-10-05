#!/usr/bin/env sh
# Sobe o Analisador de FIDCs localmente (Linux/Mac). Requer Python 3.11+ e Node 20+.
set -e
cd "$(dirname "$0")"
python3 -m pip install -q -r backend/requirements.txt
if [ ! -f frontend/dist/index.html ]; then (cd frontend && npm install && npm run build); fi
cd backend
if [ ! -f ../data/fidc.duckdb ]; then echo "Primeira execução: baixando dados da CVM (~3 min)..."; python3 -m fidc.etl; fi
echo "Abra http://localhost:8000"
python3 -m uvicorn fidc.api.main:app --port 8000
