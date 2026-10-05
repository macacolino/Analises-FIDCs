"""Testes de fumaça da API contra a base real (pulados se a base não foi construída)."""
import os

import pytest

os.environ.setdefault("FIDC_AGENDADOR", "0")
from fidc import config  # noqa: E402

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="rode python -m fidc.etl antes")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from fidc.api.main import app
    return TestClient(app)


def test_meta(client):
    r = client.get("/api/meta").json()
    assert r["mes_referencia"] <= r["ultimo_mes"]


def test_busca_e_lamina(client):
    rows = client.get("/api/fundos?limit=5").json()
    assert rows and rows[0]["pl"] >= rows[-1]["pl"]
    lam = client.get(f"/api/fundos/{rows[0]['cnpj']}").json()
    assert lam["cabecalho"]["cnpj"] == rows[0]["cnpj"]
    assert {"kpis", "comparativo", "series", "alertas"} <= set(lam)


def test_setor_e_export(client):
    assert client.get("/api/categorias").status_code == 200
    r = client.get("/api/setores/precatorios/ranking?formato=xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_fundo_inexistente(client):
    assert client.get("/api/fundos/00000000000000").status_code == 404
