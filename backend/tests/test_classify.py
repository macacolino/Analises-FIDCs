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
    # nenhum cedente listado no informe = nenhum cedente relevante: multicedente (marcado para revisar), caso do MR FIDC
    assert cat(C1=0.9, top1=None) == "multicedente_multissacado"


def test_consignado_por_prazo_e_taxa():
    # sem pista no nome: carteira longa = público; curta ou taxa alta = privado (heurística, revisar)
    assert classify.classify_frame(pd.DataFrame([{**feat(nome="FIDC XPTO", F2=1.0), "pmr": 760, "taxa_ix": None,
                                                  "segmento_principal": "F2", "segmento_principal_pct": 1.0}]), CATS
                                   ).loc[0, "categoria"] == "consignado_publico"
    assert cat(nome="FIDC XPTO", F2=1.0) == "consignado_indefinido"
    f = feat(nome="FIDC XPTO", F2=1.0)
    f.update(pmr=300, taxa_ix=None)
    c = classify.classify_one(f, CATS)[0]
    assert (c.alias_de or c.id) == "consignado_privado"


def _reg(nome="FIDC XPTO", **sinais):
    f = feat(nome=nome, F2=1.0)
    f.update(pmr=760, taxa_ix=None, tem_reg=True, **{f"reg_{k}": v for k, v in sinais.items()})
    c = classify.classify_one(f, CATS)[0]
    return c.alias_de or c.id


def test_regulamento_define_publico_ou_privado():
    # prazo longo sugeriria público, mas o regulamento é de consignado privado: regulamento ganha da heurística
    assert _reg(consignado=40, consig_privado=30, consig_inss=2) == "consignado_privado"
    assert _reg(consignado=40, consig_inss=50, consig_privado=3) == "consignado_publico"
    assert _reg(consignado=40, consig_servidor=20, consig_inss=0, consig_privado=3) == "consignado_publico"
    # o nome explícito continua ganhando do regulamento
    assert _reg(nome="CAJU CONSIGNADO PRIVADO FIDC", consignado=40, consig_inss=90, consig_privado=5) == "consignado_privado"


def test_regulamento_sem_consignado_tira_da_categoria():
    assert _reg(consignado=0, ccb=20) == "credito_pessoal"
    assert _reg(consignado=1) == "outros"


def test_consignado_escondido_em_outro_segmento():
    f = feat(nome="FIDC XPTO", F8=1.0)
    f.update(tem_reg=True, reg_consignado=30, reg_consig_privado=25)
    c = classify.classify_one(f, CATS)[0]
    assert (c.alias_de or c.id) == "consignado_privado"
    f.update(reg_consignado=5, reg_consig_privado=5)   # menção lateral não basta
    assert classify.classify_one(f, CATS)[0].id == "financeiro_outros"


def test_fic_e_sem_carteira():
    assert cat(cotas=0.9) == "fic_fidc"
    assert cat(sem_carteira=True) == "sem_carteira"


def test_override_manual_ganha():
    df = pd.DataFrame([{**feat(nome="FIDC ALION CONSIGNADOS", F2=1.0), "segmento_principal": "F2",
                        "segmento_principal_pct": 1.0}])
    out = classify.classify_frame(df, CATS, overrides={"1".zfill(14): "consignado_publico"})
    assert out.loc[0, "categoria"] == "consignado_publico"
    assert out.loc[0, "origem"] == "manual"


def _ia(nome="FIDC XPTO", seg=None, **ia):
    f = feat(nome=nome, **(seg or {"F8": 1.0}))
    f.update({f"ia_{k}": v for k, v in ia.items()})
    c = classify.classify_one(f, CATS)[0]
    return c.alias_de or c.id


def test_ia_classifica_consignado_e_tese():
    # F3 Falcon: "financeiro - outros" no informe, regulamento de consignado privado (Lei 15.179)
    assert _ia(tese="consignado", consignado="privado_clt", confianca="alta") == "consignado_privado"
    assert _ia(tese="consignado", consignado="inss", confianca="media") == "consignado_publico"
    # segmento consignado no informe, mas o regulamento é de crédito pessoal
    assert _ia(seg={"F2": 1.0}, tese="credito_pessoal", consignado="nao_e_consignado", confianca="alta") == "credito_pessoal"
    # financeiro-outros: vale a tese da IA; com confiança baixa, não
    assert _ia(tese="cartao", consignado="nao_e_consignado", confianca="alta") == "cartao"
    assert _ia(tese="cartao", consignado="nao_e_consignado", confianca="baixa") == "financeiro_outros"
    # nome explícito continua ganhando
    assert _ia(nome="CAJU CONSIGNADO PRIVADO FIDC", tese="consignado", consignado="inss", confianca="alta") == "consignado_privado"
