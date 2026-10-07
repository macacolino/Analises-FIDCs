import { useMemo, useState } from 'react'
import { useApi, useTaxonomia, type Row } from '../api'
import { fmtValue } from '../fmt'
import { DataGrid } from './DataGrid'
import { Loading } from './ui'

const mediana = (v: number[]) => {
  const s = v.filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b)
  return s.length ? s[Math.floor((s.length - 1) / 2)] : null
}

/** subordinação não se aplica a fundo de cota única (não há sênior a proteger) */
const naCotaUnica = (field: string) => ({
  field,
  valueFormatter: (p: any) => (p.data?.estrutura === 'cota única' && p.value == null ? 'n/a (cota única)' : fmtValue(p.value, 'pct')),
})

/** Comparativo por estratégia: rentabilidade 12m por tipo de cota, remuneração vs CDI, estrutura, taxas */
export function Comparativo({ categoria: fixa }: { categoria?: string }) {
  const tax = useTaxonomia()
  const [cat, setCat] = useState(fixa ?? 'precatorios_federais')
  const [alim, setAlim] = useState(false)
  const [estr, setEstr] = useState<'' | 'cota única' | 'sênior + subordinada'>('')
  const cats = cat === 'precatorios_todos' ? 'precatorios_federais,precatorios' : cat
  const url = `/api/comparativo?categorias=${cats}`
  const d = useApi<Row[]>(url)
  const rows = useMemo(() => (d.data ?? []).filter((r) =>
    (!alim || (r.alimentar ?? '').startsWith('sim') || (r.alimentar ?? '').startsWith('provável'))
    && (!estr || r.estrutura === estr)), [d.data, alim, estr])
  const res = useMemo(() => ({
    n: rows.length,
    unica: mediana(rows.map((r) => r.rentab_12m_cota_unica)),
    senior: mediana(rows.map((r) => r.rentab_12m_senior)),
    spread: mediana(rows.map((r) => r.spread_cdi_12m)),
    sub: mediana(rows.map((r) => r.rentab_12m_subordinada)),
    subord: mediana(rows.map((r) => r.subordinacao)),
    gestao: mediana(rows.map((r) => r.taxa_gestao)),
  }), [rows])
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        {!fixa && (
          <select value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="precatorios_federais">Precatórios federais</option>
            <option value="precatorios_todos">Precatórios (todos)</option>
            {tax.data?.filter((c) => !c.id.startsWith('precatorios')).map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select>
        )}
        <label className="muted"><input type="checkbox" checked={alim} onChange={(e) => setAlim(e.target.checked)} /> só foco alimentar</label>
        <select value={estr} onChange={(e) => setEstr(e.target.value as any)}>
          <option value="">Todas as estruturas</option><option value="cota única">Só cota única</option>
          <option value="sênior + subordinada">Só sênior + subordinada</option>
        </select>
      </div>
      <div className="sub">
        {res.n} fundos · medianas: rentab. 12m cota única {fmtValue(res.unica, 'pct')} · sênior {fmtValue(res.senior, 'pct')}
        {' '}· remuneração vs CDI {res.spread != null ? `CDI ${res.spread >= 0 ? '+' : '−'} ${fmtValue(Math.abs(res.spread), 'pct')}` : '–'}
        {' '}· subordinada {fmtValue(res.sub, 'pct')} · subordinação {fmtValue(res.subord, 'pct')} · taxa de gestão {fmtValue(res.gestao, 'pct')}
      </div>
      <Loading q={d} />
      <DataGrid rows={rows} exportUrl={url} height={560}
        cols={['nome', 'gestor', { field: 'pl', sort: 'desc' }, 'dt_informe', 'foco', 'alimentar', 'estrutura', 'rentab_12m_cota_unica',
               'rentab_12m_senior', 'spread_cdi_12m', 'pct_cdi_12m', 'rentab_12m_mezanino', 'rentab_12m_subordinada',
               'meses_rentab', naCotaUnica('subordinacao'), naCotaUnica('jr_pl'), 'benchmark_senior', 'taxa_gestao', 'taxa_administracao',
               'taxa_performance', 'taxa_minima_cessao', 'pct_precatorios', 'over90_carteira', 'q_status', 'admin']} />
      <p className="muted">Rentabilidade 12m pelo informe CVM (séries com PL; com 6–11 meses de histórico, anualizada – ver
        "Meses na conta"). Remuneração vs CDI = (1 + rentab. 12m da cota única ou sênior) / (1 + CDI 12m) − 1. Taxas, benchmark e
        taxa mínima de cessão vêm do regulamento (manual &gt; IA &gt; regras de texto); o benchmark costuma ficar no suplemento da
        série e pode faltar. Foco "(regras)" = leitura por texto, ainda sem a leitura por IA.</p>
    </div>
  )
}
