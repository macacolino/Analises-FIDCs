#!/usr/bin/env bash
# Prepara e sobe o Analisador de FIDCs. Pode rodar quantas vezes quiser:
# refaz só o que mudou desde a última vez (dependências, telas, base de dados).
set -e
cd "$(dirname "$0")/.."
mkdir -p data

hash_of() { find "$@" -type f \( -name '*.py' -o -name '*.yaml' -o -name '*.ts' -o -name '*.tsx' -o -name '*.css' -o -name '*.json' -o -name '*.gz' -o -name '*.txt' -o -name '*.html' \) \
  -not -path '*/node_modules/*' -not -path '*/__pycache__/*' -print0 | sort -z | xargs -0 cat | md5sum | cut -d' ' -f1; }

echo "==> 1/4 Dependências Python"
H=$(md5sum backend/requirements.txt | cut -d' ' -f1)
if [ "$(cat data/.req-hash 2>/dev/null)" != "$H" ]; then
  pip install -q -r backend/requirements.txt && echo "$H" > data/.req-hash
fi

echo "==> 2/4 Telas (frontend)"
H=$(hash_of frontend/src frontend/package.json frontend/index.html)
if [ ! -f frontend/dist/index.html ] || [ "$(cat data/.web-hash 2>/dev/null)" != "$H" ]; then
  echo "    código das telas mudou: recompilando..."
  (cd frontend && npm ci --no-audit --no-fund && npm run build) && echo "$H" > data/.web-hash
fi

echo "==> 3/4 Dados"
H=$(hash_of backend/fidc)
if [ ! -f data/fidc.duckdb ] || [ ! -d data/parquet/I ]; then
  echo "    Primeira vez: baixando e processando o histórico da CVM e do Banco Central (3 a 5 min)..."
  (cd backend && python -m fidc.etl) && echo "$H" > data/.etl-hash
elif [ "$(cat data/.etl-hash 2>/dev/null)" != "$H" ]; then
  echo "    código de cálculo mudou: atualizando dados e reconstruindo a base (1 a 3 min)..."
  (cd backend && python -m fidc.etl) && echo "$H" > data/.etl-hash
fi

echo "==> 4/4 Subindo o app na porta 8000"
pkill -f "[u]vicorn fidc.api.main" 2>/dev/null || true
sleep 1
nohup python -m uvicorn fidc.api.main:app --app-dir backend --host 0.0.0.0 --port 8000 < /dev/null > /tmp/fidc-api.log 2>&1 &
disown
for i in $(seq 1 30); do
  if curl -s localhost:8000/api/meta >/dev/null; then
    echo ""
    echo "PRONTO! Abra a aba 'PORTAS' (ou 'Ports') aqui embaixo e clique no globo da porta 8000."
    echo "Se a página já estava aberta, recarregue com Ctrl+Shift+R."
    exit 0
  fi
  sleep 1
done
echo "O app não respondeu. Log:"; tail -30 /tmp/fidc-api.log; exit 1
