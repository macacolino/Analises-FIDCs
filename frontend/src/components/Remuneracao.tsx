import { useApi, type Row } from '../api'
import { DataGrid } from './DataGrid'
import { Loading } from './ui'
import { fmtValue } from '../fmt'

/** Remuneração prometida por série (documentos do FNET lidos por IA) x entregue no informe CVM. */
export function RemuneracaoPrometida({ cnpj }: { cnpj: string }) {
  const q = useApi<{ series: Row[]; resumo: Row | null }>(`/api/fundos/${cnpj}/remuneracao`)
  if (!q.data) return <Loading q={q} />
  const { series, resumo: r } = q.data
  if (!r) return <div className="muted">Remuneração prometida ainda não lida para este fundo (fila de leitura automática).</div>
  const pp = (v: any) => v == null ? '–' : `${v >= 0 ? '+' : '−'}${fmtValue(Math.abs(v), 'pct')}`
  const linha = (rot: string, txt: any, alvo: any, ent: any, gap: any) => (txt || alvo != null) && (
    <div>
      <b>{rot}:</b> {txt ?? '–'}
      {alvo != null && <> · na régua CDI + x: <b>{pp(alvo)}</b> a.a.</>}
      {ent != null && <> · entregue (informe): <b>{pp(ent)}</b></>}
      {gap != null && <> · diferença: <b style={{ color: gap < -0.005 ? 'var(--critical)' : undefined }}>{pp(gap)}</b> a.a.</>}
    </div>
  )
  return (
    <div className="stack" style={{ gap: 6 }}>
      {linha('Sênior prometida', r.rem_senior_texto, r.rem_senior_alvo_aa, r.rem_senior_entregue_aa, r.rem_senior_gap_aa)}
      {linha('Mezanino prometida', r.rem_mez_texto, r.rem_mez_alvo_aa, r.rem_mez_entregue_aa, r.rem_mez_gap_aa)}
      {!r.rem_senior_texto && !r.rem_mez_texto && <div className="muted">
        Nenhuma meta numérica encontrada nos documentos públicos do FNET{r.rem_obs ? ` — ${r.rem_obs}` : '.'}</div>}
      {r.rem_sub && <div className="muted">Subordinada: {r.rem_sub}</div>}
      {r.rem_obs && (r.rem_senior_texto || r.rem_mez_texto) && <div className="muted">{r.rem_obs}</div>}
      <div className="muted" style={{ fontSize: 12 }}>
        Fonte: {r.rem_senior_doc ?? 'documentos do FNET'}{r.rem_senior_data ? ` de ${r.rem_senior_data}` : ''} · leitura por IA,
        confiança {r.rem_confianca ?? '–'}. "x% do CDI" convertido para CDI + x com o CDI de mercado dos últimos 12 meses.
        Entregue = mediana do excesso mensal da sênior/mezanino sobre o CDI no informe, anualizada.
      </div>
      {series.length > 0 && <DataGrid title="Séries com meta" rows={series} id="rem-series" pinned={0}
        cols={['tipo', 'nome', 'emissao_ou_serie', 'formula', 'indexador', 'spread_aa', 'pct_cdi', 'taxa_prefixada_aa',
               'vigente', 'natureza', 'data_emissao', 'valor_emitido', 'vencimento_ou_prazo', 'amortizacao', 'documento',
               'data_documento', 'pagina', 'trecho']} />}
    </div>
  )
}
