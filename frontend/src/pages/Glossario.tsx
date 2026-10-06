import { useMemo, useState } from 'react'
import { useApi, useDic, type Row } from '../api'
import { Loading } from '../components/ui'

const SENTIDO: Record<number, string> = { 1: 'maior é melhor', [-1]: 'menor é melhor', 0: 'contexto (sem juízo)' }

/** Conceitos que não são uma coluna específica, mas aparecem em todo o app. */
const CONCEITOS: [string, string][] = [
  ['Informe mensal (CVM)', 'Documento estruturado que todo FIDC entrega à CVM todo mês (tabelas I a X). Fonte principal do app: dados.cvm.gov.br. Os números são declarados pelo administrador, sem auditoria.'],
  ['Mês de referência', 'Último mês em que pelo menos 90% dos fundos do mês anterior já entregaram o informe. O mês corrente costuma aparecer parcial e não entra nas comparações.'],
  ['Carteira bruta', 'Direitos creditórios líquidos de PDD (Tab. I) + PDD. Base de quase todos os percentuais "/ carteira". Conferido: a Tab. II (carteira por segmento) soma a mesma carteira bruta em ~95% dos fundos.'],
  ['Vencidos por faixa (aging)', 'Valor das parcelas vencidas e não pagas por faixa de atraso (1-30, 31-60, …, >1080 dias), Tab. V (com aquisição substancial de riscos) + Tab. VI (sem).'],
  ['Over 30 / Over 90 / Over 180', 'Soma das faixas de atraso acima de 30, 90 ou 180 dias, dividida pela carteira bruta (Over 180 é dividido pelo PL).'],
  ['PDD', 'Provisão para redução no valor de recuperação (itens I.2.a.11 e I.2.b.11 do informe).'],
  ['Sênior, mezanino e subordinada júnior (Sr, Mz, Jr)', 'Tipos de cota pela ordem de prioridade. A Jr absorve perdas primeiro, depois a Mz, por último a Sr. Tipo lido do nome da série/subclasse na Tab. X.2.'],
  ['Subordinação', '(PL mezanino + PL subordinada) ÷ PL das séries, com PL de cada série = quantidade de cotas × valor da cota (Tab. X.2). Fica em branco quando o fundo tem uma única série.'],
  ['Roll rate', 'Quanto do atraso de uma faixa migra para a faixa seguinte no mês: ex. vencidos 31-60 d no mês ÷ vencidos 1-30 d no mês anterior.'],
  ['Safra (por mês de vencimento)', 'Proxy sem fita: a safra do mês m é o saldo a vencer em até 30 dias no fim de m−1. F30 = vencidos 31-60 d no fim de m+1 ÷ base; F60 = 61-90 d em m+2; F180 = 151-180 d em m+5 (≈ perda da safra); F360 = 361-720 d em m+12.'],
  ['Pares', 'Fundos usados como comparação: mesma categoria, mercado inteiro ou um grupo salvo (ex.: Pares MCMS). O próprio fundo nunca entra nas estatísticas.'],
  ['P25, mediana, P75', 'Quartis da métrica entre os pares: 25% dos pares estão abaixo do P25, metade abaixo da mediana, 75% abaixo do P75.'],
  ['Percentil', 'Posição do fundo entre os pares (0 a 100), mostrada quando há pelo menos 5 pares com dado.'],
  ['Posição (quartil favorável / desfavorável)', 'Favorável = fundo no melhor quartil dos pares no sentido da métrica (acima do P75 se "maior é melhor"; abaixo do P25 se "menor é melhor"). Desfavorável = pior quartil. Entre os dois = neutro.'],
  ['Zero vencido declarado', 'Fundo que informa zero em todas as faixas de atraso e na Tab. I. Não é possível verificar; por padrão esses fundos ficam fora das estatísticas de inadimplência dos pares (opção na tela).'],
  ['1 fundo por gestora', 'Opção da comparação: fica só o maior fundo de cada gestora, para uma casa grande não dominar as estatísticas.'],
  ['Qualidade do dado (ok / alerta / erro)', 'Resultado das checagens de consistência do informe no mês. Pares com erro ficam fora das estatísticas por padrão.'],
  ['Red flag (amarelo / vermelho)', 'Sinal de risco da biblioteca MCMS calculado pelo informe. Os limiares foram calibrados para FIDCs multicedente multissacado e devem ser lidos com cuidado em outras teses.'],
  ['Categoria', 'Classificação interna do fundo (arquivo categorias.yaml): Tab. II do informe, palavras do nome, concentração de cedentes e, para consignado, prazo e taxa da carteira. "Revisar" = classificação de baixa confiança. Ajuste manual na lâmina sempre ganha.'],
  ['Stress test', 'Perda anual = custo de crédito 12m × 1, 2 e 4; nos cenários 2x e 4x a receita cai e entra a quebra do maior cedente. Perdas absorvidas Jr → Mz → Sr. Mostra a perda anual que zera a Jr e a que atinge a sênior.'],
]

export default function Glossario() {
  const cat = useApi<any>('/api/catalogo', { staleTime: Infinity })
  const checks = useApi<Row[]>('/api/qualidade/checks', { staleTime: Infinity })
  const { data: dic } = useDic()
  const [q, setQ] = useState('')
  const norm = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  const ok = (...t: (string | undefined)[]) => !q || t.some((x) => x && norm(x).includes(norm(q)))

  const outros = useMemo(() => {
    if (!dic || !cat.data) return []
    const ja = new Set([...cat.data.metricas.map((m: Row) => m.metrica), ...cat.data.red_flags.map((r: Row) => r.id)])
    return Object.entries(dic).filter(([k, v]) => !ja.has(k) && v.desc).sort((a, b) => a[1].label.localeCompare(b[1].label))
  }, [dic, cat.data])

  return (
    <div className="stack">
      <div>
        <h1>Glossário</h1>
        <div className="sub">Todos os termos, indicadores e como são calculados. A mesma definição aparece ao passar o mouse sobre o termo no app.</div>
      </div>
      <input type="search" className="big" placeholder="Buscar termo…" value={q} onChange={(e) => setQ(e.target.value)} />
      <Loading q={cat} />

      <div className="card"><h2>Conceitos</h2>
        <table className="simple"><tbody>{CONCEITOS.filter(([t, d]) => ok(t, d)).map(([t, d]) => (
          <tr key={t}><td style={{ width: '24%' }}><b>{t}</b></td><td>{d}</td></tr>))}</tbody></table>
      </div>

      {cat.data && cat.data.blocos.map((b: string) => {
        const ms = cat.data.metricas.filter((m: Row) => m.bloco === b && ok(m.label, m.definicao, m.codigo))
        if (!ms.length) return null
        return (
          <div key={b} className="card"><h2>Indicadores · {b}</h2>
            <table className="simple">
              <thead><tr><th>Indicador</th><th>Como calculamos</th><th>Leitura</th><th>Ref.</th></tr></thead>
              <tbody>{ms.map((m: Row) => (
                <tr key={m.metrica}><td style={{ width: '24%' }}><b>{m.label}</b></td><td>{m.definicao || dic?.[m.metrica]?.desc || '–'}</td>
                  <td className="muted" style={{ width: 150 }}>{SENTIDO[m.sentido]}</td><td className="muted">{m.codigo ?? ''}</td></tr>))}</tbody>
            </table>
          </div>
        )
      })}

      {cat.data && (
        <div className="card"><h2>Red flags</h2>
          <table className="simple">
            <thead><tr><th>Red flag</th><th>Regra (amarelo / vermelho)</th><th>Ref.</th></tr></thead>
            <tbody>{cat.data.red_flags.filter((r: Row) => ok(r.nome, r.regra)).map((r: Row) => (
              <tr key={r.id}><td style={{ width: '30%' }}><b>{r.nome}</b></td><td>{r.regra}</td><td className="muted">{r.codigo}</td></tr>))}</tbody>
          </table>
        </div>
      )}

      {checks.data && (
        <div className="card"><h2>Checagens de qualidade do dado</h2>
          <table className="simple">
            <thead><tr><th>#</th><th>Checagem</th><th>Severidade</th><th>O que fazer</th></tr></thead>
            <tbody>{checks.data.filter((c) => ok(c.descricao, c.recomendacao, c.id)).map((c) => (
              <tr key={c.id}><td>{c.id}</td><td>{c.descricao}</td><td>{c.severidade}</td><td className="muted">{c.recomendacao}</td></tr>))}</tbody>
          </table>
        </div>
      )}

      {cat.data && (
        <div className="card"><h2>Dados de regulamento e do gestor</h2>
          <p className="muted">Subordinação mínima, Jr mínima, limites de concentração e responsabilidade limitada são lidos
            automaticamente do regulamento vigente no FNET (regras de texto, sem IA), sempre com a página e o trecho. O dado
            manual prevalece sobre o extraído. Os demais dependem de preenchimento manual.</p>
          <table className="simple">
            <thead><tr><th>Dado</th><th>Fonte típica</th><th>Usado em</th></tr></thead>
            <tbody>{cat.data.parametros.filter((p: Row) => ok(p.label, p.uso)).map((p: Row) => (
              <tr key={p.chave}><td>{p.label}</td><td>{p.fonte}</td><td className="muted">{p.uso}</td></tr>))}</tbody>
          </table>
        </div>
      )}

      {outros.length > 0 && (
        <div className="card"><h2>Outros campos</h2>
          <table className="simple"><tbody>{outros.filter(([, v]) => ok(v.label, v.desc)).map(([k, v]) => (
            <tr key={k}><td style={{ width: '24%' }}><b>{v.label}</b></td><td>{v.desc}</td></tr>))}</tbody></table>
        </div>
      )}
    </div>
  )
}
