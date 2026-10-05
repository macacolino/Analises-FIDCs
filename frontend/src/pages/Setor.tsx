import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useApi, useTaxonomia, type Row } from '../api'
import { Bars, TimeLines } from '../components/Charts'
import { DataGrid } from '../components/DataGrid'
import { Kpi, Loading, Tabs } from '../components/ui'
import { mesAno } from '../fmt'

const SAFRA_METRICAS: [string, string][] = [
  ['inad_90', 'Inad. >90d'], ['pdd_carteira', 'PDD / carteira'], ['inad_90_lag12', 'Inad. defasada 12m'],
  ['rentab_senior', 'Rentab. sênior'], ['subordinacao', 'Subordinação'],
]
const SAFRA_FMT: Record<string, string> = { rentab_senior: 'pct100' }

export default function Setor() {
  const { categoria = 'consignado_publico' } = useParams()
  const nav = useNavigate()
  const tax = useTaxonomia()
  const setor = useApi<{ historico: Row[]; aging: Row[] }>(`/api/setores/${categoria}`)
  const [tab, setTab] = useState<'fundos' | 'series' | 'safra'>('fundos')
  const [tipoSerie, setTipoSerie] = useState('senior')
  const [safraMetrica, setSafraMetrica] = useState('inad_90')
  const rankUrl = `/api/setores/${categoria}/ranking`
  const seriesUrl = `/api/ranking/series?categoria=${categoria}${tipoSerie ? `&tipo=${tipoSerie}` : ''}`
  const safraUrl = `/api/setores/${categoria}/safra?metrica=${safraMetrica}`
  const ranking = useApi<Row[]>(rankUrl)
  const series = useApi<Row[]>(tab === 'series' ? seriesUrl : null)
  const safra = useApi<Row[]>(tab === 'safra' ? safraUrl : null)

  // começa no 1º mês com pelo menos 5 fundos: antes disso a "categoria" é um ou dois fundos e o gráfico vira ruído
  const hist = useMemo(() => {
    const h = setor.data?.historico ?? []
    const i = h.findIndex((r) => r.n_fundos >= 5 && r.dt >= '2016-01-01')
    return i < 0 ? h : h.slice(i)
  }, [setor.data])
  const ult = hist[hist.length - 1]
  const cat = tax.data?.find((c) => c.id === categoria)

  // safra de fundos: uma linha por ano de início (as 6 safras mais recentes com dados)
  const safraChart = useMemo(() => {
    const rows = safra.data ?? []
    const anos = [...new Set(rows.map((r) => r.safra_fundo))].sort().slice(-6)
    const byM = new Map<number, Row>()
    for (const r of rows) {
      if (!anos.includes(r.safra_fundo) || r.meses_desde_inicio > 60) continue
      const row = byM.get(r.meses_desde_inicio) ?? { m: r.meses_desde_inicio }
      row[`s${r.safra_fundo}`] = r.valor
      byM.set(r.meses_desde_inicio, row)
    }
    return { data: [...byM.values()].sort((a, b) => a.m - b.m), series: anos.map((a) => ({ key: `s${a}`, label: `Safra ${a}` })) }
  }, [safra.data])

  return (
    <div className="stack">
      <div className="row">
        <div>
          <h1>{cat?.nome ?? categoria}</h1>
          <div className="sub">{cat?.grupo} · análise setorial · referência {mesAno(ult?.dt)}</div>
        </div>
        <div className="spacer" />
        <select value={categoria} onChange={(e) => nav(`/setores/${e.target.value}`)}>
          {tax.data?.map((c) => <option key={c.id} value={c.id}>{c.grupo} · {c.nome}</option>)}
        </select>
      </div>
      <Loading q={setor} />
      {ult && (
        <div className="kpis">
          <Kpi k="n_fundos" v={ult.n_fundos} />
          <Kpi k="pl_total" v={ult.pl_total} />
          <Kpi k="inad_90" v={ult.inad_90} compare={<>mediana {fmtP(ult.inad_90_mediana)}</>} />
          <Kpi k="pdd_carteira" v={ult.pdd_carteira} compare={<>mediana {fmtP(ult.pdd_carteira_mediana)}</>} />
          <Kpi k="subordinacao" v={ult.subordinacao} compare={<>mediana {fmtP(ult.subordinacao_mediana)}</>} />
          <Kpi k="rentab_senior" label="Rentab. sênior (mediana)" v={ult.rentab_senior_mediana} />
          <Kpi k="rentab_subordinada" label="Rentab. subordinada (mediana)" v={ult.rentab_subordinada_mediana} />
          <Kpi k="roll_60_90" label="Roll 31-60→61-90 (mediana)" v={ult.roll_60_90_mediana} />
        </div>
      )}
      {hist.length > 0 && (
        <div className="grid2">
          <div className="card"><TimeLines title="PL da categoria" data={hist} fmt="brl"
            series={[{ key: 'pl_total', label: 'PL' }]} /></div>
          <div className="card"><TimeLines title="Inadimplência >90d" data={hist} fmt="pct"
            series={[{ key: 'inad_90', label: 'Agregada (ponderada)' }, { key: 'inad_90_mediana', label: 'Mediana dos fundos' }]} /></div>
          <div className="card"><TimeLines title="PDD / carteira" data={hist} fmt="pct"
            series={[{ key: 'pdd_carteira', label: 'Agregada' }, { key: 'pdd_carteira_mediana', label: 'Mediana' }]} /></div>
          <div className="card"><TimeLines title="Subordinação" data={hist} fmt="pct"
            series={[{ key: 'subordinacao', label: 'Agregada' }, { key: 'subordinacao_mediana', label: 'Mediana' }]} /></div>
          <div className="card"><TimeLines title="Rentabilidade mensal (mediana)" data={hist} fmt="pct100"
            series={[{ key: 'rentab_senior_mediana', label: 'Sênior' }, { key: 'rentab_subordinada_mediana', label: 'Subordinada' }]} /></div>
          <div className="card"><TimeLines title="Roll rates (mediana) - proxy de safra" data={hist} fmt="pct"
            series={[{ key: 'roll_30_60_mediana', label: '1-30→31-60' }, { key: 'roll_60_90_mediana', label: '31-60→61-90' },
                     { key: 'roll_90_120_mediana', label: '61-90→91-120' }]} /></div>
        </div>
      )}
      {setor.data?.aging && (
        <div className="card">
          <Bars title="Parcelas vencidas por faixa de atraso (% da carteira bruta da categoria)" data={setor.data.aging}
            x="faixa" fmt="pct" series={[{ key: 'pct_carteira', label: '% carteira' }]} />
        </div>
      )}
      <div className="card">
        <Tabs value={tab} onChange={setTab} options={[['fundos', 'Ranking de fundos'], ['series', 'Ranking de séries (rentabilidade)'], ['safra', 'Safra de fundos']]} />
        {tab === 'fundos' && (
          <DataGrid rows={ranking.data} exportUrl={rankUrl} height={560}
            cols={['nome', 'gestor', { field: 'pl', sort: 'desc' }, 'inad_90', 'inad_contratos', 'pdd_carteira',
                   'cobertura_pdd_90', 'subordinacao', 'rentab_senior', 'rentab_subordinada', 'roll_60_90',
                   'inad_90_lag12', 'recompra_subst_3m_carteira', 'top1_cedente_pct', 'prazo_medio_dias', 'admin']} />
        )}
        {tab === 'series' && (
          <DataGrid rows={series.data} exportUrl={seriesUrl} height={560}
            extra={(
              <select value={tipoSerie} onChange={(e) => setTipoSerie(e.target.value)}>
                <option value="senior">Sênior</option><option value="mezanino">Mezanino</option>
                <option value="subordinada">Subordinada</option><option value="">Todas</option>
              </select>
            )}
            cols={['nome', 'serie', 'tipo', 'pl_serie', 'rentab_mes', { field: 'rentab_12m', sort: 'desc' },
                   'subordinacao', 'inad_90', 'pdd_carteira']} />
        )}
        {tab === 'safra' && (
          <div className="stack">
            <div className="row">
              <span className="sub">Mediana entre os fundos de cada safra (ano do 1º informe) por meses de vida. Safras com ≥3 fundos.</span>
              <div className="spacer" />
              <select value={safraMetrica} onChange={(e) => setSafraMetrica(e.target.value)}>
                {SAFRA_METRICAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <a className="btn" href={`${safraUrl}&formato=xlsx`}>⬇ Excel</a>
            </div>
            <Loading q={safra} />
            {safra.data && (
              <TimeLines data={safraChart.data} x="m" xFmt={(v) => `mês ${v}`} series={safraChart.series}
                fmt={SAFRA_FMT[safraMetrica] ?? 'pct'} height={320} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const fmtP = (v: number | null) => (v == null ? '–' : (v * 100).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '%')
