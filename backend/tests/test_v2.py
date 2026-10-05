"""Testes da v2 contra a base real (pulados se a base não existe).

O batimento usa valores calculados de forma independente na Base MCMS ago/26
(conector FIDCs.com.br + FNET) para fundos públicos - serve de regressão do método.
"""
import os

import pytest

os.environ.setdefault("FIDC_AGENDADOR", "0")
from fidc import config  # noqa: E402

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="rode python -m fidc.etl antes")

# cnpj: {métrica: valor de referência (Base MCMS ago/26)}
REF = {
    "24504464000101": {"pl": 1924.33162455e6, "over90_carteira": 0.0287951724907805, "pdd_carteira": 0.0606593050699894,
                       "subordinacao": 0.38514775598687, "jr_pl": 0.19612588204918, "m01_jr_pdd": 9.2358531058443,
                       "m16b_custo_credito_simples": 0.0629997340214705, "retorno_jr_pct_cdi": 3.03181701589688},
    "23216398000101": {"over90_carteira": 0.0353193208949948, "m01_jr_pdd": 29.8175740620642,
                       "m16b_custo_credito_simples": 0.00954041656178455},
}


def _row(cnpj):
    from fidc.db import df
    return df("SELECT * FROM comp_mes WHERE cnpj = ? AND dt = DATE '2026-08-31'", [cnpj]).iloc[0]


@pytest.mark.parametrize("cnpj", list(REF))
def test_batimento_base_mcms(cnpj):
    r = _row(cnpj)
    for k, ref in REF[cnpj].items():
        assert r[k] == pytest.approx(ref, rel=0.02, abs=0.002), k


def test_qualidade_tem_catalogo_e_resumo():
    from fidc.db import df
    ids = set(df("SELECT id FROM qualidade_check").id)
    assert {"Q01", "Q02", "Q09", "Q10"} <= ids
    st = df("SELECT DISTINCT status FROM qualidade_resumo").status
    assert set(st) <= {"ok", "alerta", "erro"}


def test_safras_sem_valores_impossiveis():
    from fidc.db import df
    d = df("SELECT quantile_cont(f30, 0.5) AS m FROM safra_venc WHERE f30 IS NOT NULL")
    assert 0 <= d.m[0] < 0.5


def test_comparacao_exclui_proprio_fundo_e_tem_posicao():
    from fidc import comparacao as cp
    r = cp.comparar("24504464000101")
    assert "24504464000101" not in {p["cnpj"] for p in r["pares"]["lista"]}
    assert {m["posicao"] for m in r["metricas"]} <= {"favoravel", "neutro", "desfavoravel", "contexto", "n/d"}
    assert len(r["red_flags"]) >= 10


def test_stress_limiar_maior_que_custo():
    from fidc import comparacao as cp
    s = cp.stress("24504464000101")
    assert s["disponivel"] and s["limiar_perda_senior"] > s["limiar_perda_jr"] > 0


def test_api_v2_rotas(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DB_PATH", tmp_path / "app.sqlite")
    from fastapi.testclient import TestClient
    from fidc.api.main import app
    with TestClient(app) as c:
        c_ = "24504464000101"
        for u in [f"/api/comparar/{c_}", f"/api/comparar/{c_}/serie?metrica=over90_carteira",
                  f"/api/fundos/{c_}/stress", f"/api/fundos/{c_}/roteiro", f"/api/fundos/{c_}/safras",
                  "/api/catalogo", "/api/qualidade/resumo", "/api/grupos"]:
            assert c.get(u).status_code == 200, u
        assert c.get("/api/grupos").json()[0]["nome"] == "Pares MCMS"   # carga inicial
        r = c.get(f"/api/fundos/{c_}/comite.xlsx")
        assert r.status_code == 200 and r.content[:2] == b"PK"
