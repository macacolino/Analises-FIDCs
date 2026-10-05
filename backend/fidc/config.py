"""Caminhos e parâmetros globais. Tudo pode ser sobrescrito por variável de ambiente."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("FIDC_DATA_DIR", ROOT / "data"))

RAW_DIR = DATA_DIR / "raw"            # zips baixados da CVM
PARQUET_DIR = DATA_DIR / "parquet"    # uma pasta por tabela do informe, um parquet por zip
DB_PATH = DATA_DIR / "fidc.duckdb"    # base analítica (reconstruída pelo ETL)
APP_DB_PATH = DATA_DIR / "app.sqlite" # estado do app: carteira, watchlist, notas, overrides
FNET_CACHE_DIR = DATA_DIR / "fnet"

CVM_BASE = "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS"
CVM_CAD_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
FNET_BASE = "https://fnet.bmfbovespa.com.br/fnet/publico"

TAXONOMY_FILE = Path(os.environ.get(
    "FIDC_TAXONOMY_FILE", Path(__file__).parent / "taxonomy" / "categorias.yaml"))

HTTP_TIMEOUT = float(os.environ.get("FIDC_HTTP_TIMEOUT", "300"))

for d in (RAW_DIR, PARQUET_DIR, FNET_CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
