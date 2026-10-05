import pandas as pd

from fidc.taxonomy import classify

CATS = classify.load_taxonomy()


def feat(nome="FIDC X", top1=None, sem_carteira=False, cotas=0.0, aquis_inad=0.0, **seg):
    f = {"cnpj": "1".zfill(14), "nome_norm": classify.normalize(nome), "top1_cedente_pct": top1,
         "sem_carteira": sem_carteira, "sh_cotas_fidc": cotas, "sh_aquis_inad": aquis_inad}
    for s in classify.SEGMENTOS:
        f[f"sh_{s}"] = seg.get(s, 0.0)
    return f


def cat(**kw):
    return classify.classify_one(feat(**kw), CATS)[0].id


def test_ids_unicos_e_fallback():
    assert CATS[-1].id == "outros"


def test_consignado_publico_privado_e_indefinido():
    assert cat(nome="FIDC FACTA CONSIGNADO INSS", F2=1.0) == "consignado_publico"
    assert cat(nome="CAJU CONSIGNADO PRIVADO FIDC", F2=1.0) == "consignado_privado"
    assert cat(nome="FIDC CLT NOW", F2=1.0) == "consignado_privado"
    assert cat(nome="FIDC ALION CONSIGNADOS", F2=1.0) == "consignado_indefinido"


def test_fgts_vem_antes_de_consignado():
    assert cat(nome="ICRED FGTS 2 FIDC", F2=1.0) == "fgts"


def test_precatorio_por_segmento_e_por_nome():
    assert cat(I1=0.8) == "precatorios"
    assert cat(nome="FIDC PRECATORIOS FEDERAIS", F8=1.0) == "precatorios"


def test_multicedente_por_concentracao():
    assert cat(C1=0.9, top1=8) == "multicedente_multissacado"
    assert cat(C1=0.9, top1=70) == "monocedente_comercial"
    assert cat(C1=0.9, top1=30) == "recebiveis_comerciais_outros"
    # sem informação de cedente não dá para afirmar multicedente
    assert cat(C1=0.9, top1=None) == "recebiveis_comerciais_outros"


def test_fic_e_sem_carteira():
    assert cat(cotas=0.9) == "fic_fidc"
    assert cat(sem_carteira=True) == "sem_carteira"


def test_override_manual_ganha():
    df = pd.DataFrame([{**feat(nome="FIDC ALION CONSIGNADOS", F2=1.0), "segmento_principal": "F2",
                        "segmento_principal_pct": 1.0}])
    out = classify.classify_frame(df, CATS, overrides={"1".zfill(14): "consignado_publico"})
    assert out.loc[0, "categoria"] == "consignado_publico"
    assert out.loc[0, "origem"] == "manual"
