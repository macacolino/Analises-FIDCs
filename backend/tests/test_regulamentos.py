"""Leitura do regulamento por regras: trechos reais (MR FIDC, cl. 7 e Anexo) em formato reduzido."""
from fidc import regulamentos as rg

PAG = [
    "Capítulo 4. A Razão de Subordinação Mínima será de, no mínimo, 33,33% (trinta e três inteiros e trinta e três "
    "centésimos por cento) do Patrimônio Líquido. As Cotas Subordinadas Juniores deverão representar, no mínimo, 50% "
    "(cinquenta por cento) do patrimônio líquido das Cotas Subordinadas.",
    "7.5 O total de Direitos Creditórios devidos por cada Devedor não poderá ser superior a 5% (cinco por cento) do "
    "Patrimônio Líquido. O fundo poderá adquirir Direitos Creditórios devidos por um mesmo Devedor acima do limite de "
    "20% (vinte por cento) do Patrimônio Líquido quando: (a) houver garantia.",
    "Critérios de Elegibilidade: (i) os Direitos Creditórios de um mesmo Cedente poderão representar no máximo 10% "
    "(dez por cento) do Patrimônio Líquido; (ii) os Direitos Creditórios adquiridos dos 10 (dez) maiores Cedentes "
    "poderão representar no máximo 55% (cinquenta e cinco por cento) do Patrimônio Líquido; (iii) os Direitos "
    "Creditórios que tenham um mesmo Devedor poderão representar no máximo 3,5% (três e meio por cento) do "
    "Patrimônio Líquido; (iv) a soma dos 10 (dez) maiores Devedores poderão representar no máximo 25% do Patrimônio "
    "Líquido.",
]


def test_campos_mr():
    c = {x["campo"]: x for x in rg.campos(PAG)}
    assert abs(c["sub_min_senior"]["valor_num"] - 0.3333) < 1e-9
    assert c["jr_min_sobre_subordinadas"]["valor_num"] == 0.5
    assert abs(c["jr_min_pl"]["valor_num"] - 0.16665) < 1e-9
    assert c["limite_maior_cedente"]["valor_num"] == 0.10
    assert c["limite_10_cedentes"]["valor_num"] == 0.55
    # a cláusula mais restritiva (3,5%) ganha; a exceção "acima do limite de 20%" é ignorada
    assert c["limite_maior_sacado"]["valor_num"] == 0.035
    assert c["limite_10_sacados"]["valor_num"] == 0.25
    assert all(x["trecho"] and x["pagina"] for x in c.values())


def test_sinais_consignado():
    s = rg.sinais("Direitos creditórios de crédito consignado a trabalhadores do setor privado, via eSocial "
                  "(Lei 15.179). Não inclui benefícios do INSS.")
    assert s["consignado"] == 1 and s["consig_privado"] >= 2 and s["consig_inss"] == 1


def test_legibilidade():
    assert not rg.texto_legivel("\x03\x04\x05" * 2000)
    assert rg.texto_legivel(("O fundo de investimento das cotas que de da do " * 100))
