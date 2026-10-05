#!/usr/bin/env bash
# Prepara (se faltar algo) e sobe o Analisador de FIDCs. Pode rodar quantas vezes quiser.
set -e
cd "$(dirname "$0")/.."

echo "==> 1/4 Dependências Python"
python -c "import duckdb, fastapi, uvicorn, openpyxl, yaml" 2>/dev/null || pip install -q -r backend/requirements.txt

echo "==> 2/4 Telas (frontend)"
if [ ! -f frontend/dist/index.html ]; then (cd frontend && npm ci --no-audit --no-fund && npm run build); fi

echo "==> 3/4 Dados da CVM"
if [ ! -f data/fidc.duckdb ]; then
  echo "    Primeira vez: baixando e processando o histórico da CVM (3 a 5 min)..."
  (cd backend && python -m fidc.etl)
fi

echo "==> 4/4 Subindo o app na porta 8000"
pkill -f "[u]vicorn fidc.api.main" 2>/dev/null || true
nohup python -m uvicorn fidc.api.main:app --app-dir backend --host 0.0.0.0 --port 8000 < /dev/null > /tmp/fidc-api.log 2>&1 &
disown
for i in $(seq 1 20); do
  if curl -s localhost:8000/api/meta >/dev/null; then
    echo ""
    echo "PRONTO! Abra a aba 'PORTAS' (ou 'Ports') aqui embaixo e clique no globo da porta 8000."
    exit 0
  fi
  sleep 1
done
echo "O app não respondeu. Log:"; tail -30 /tmp/fidc-api.log; exit 1
