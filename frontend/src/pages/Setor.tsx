import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { send, useApi, useTaxonomia, type Row } from '../api'
import { Bars, RankBars, TimeLines } from '../components/Charts'
import { Comparativo } from '../components/Comparativo'
import { DataGrid } from '../components/DataGrid'
import { Kpi, Loading, Tabs } from '../components/ui'
import { fmtValue, mesAno } from '../fmt'

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
  const [tab, setTab] = useState<'fundos' | 'series' | 'safra' | 'bcb' | 'orig' | 'gest' | 'rf' | 'dist' | 'estr' | 'comp'>('fundos')
  const [tipoSerie, setTipoSerie] = useState('')
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
        <Tabs value={tab} onChange={setTab} options={[['fundos', 'Ranking de fundos'], ['comp', 'Comparativo (rentab., taxas)'], ['estr', 'Estrutura x regulamento'], ['dist', 'Distribuição'], ['series', 'Ranking de séries'], ['rf', 'Red flags do setor'], ['bcb', 'Mercado (Banco Central)'], ['orig', 'Originadores / cedentes'], ['gest', 'Gestores'], ['safra', 'Safra de fundos']]} />
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
                <option value="">Todos os tipos de cota</option><option value="senior">Sênior</option>
                <option value="mezanino">Mezanino</option><option value="subordinada">Subordinada (júnior)</option>
              </select>
            )}
            cols={['nome', 'serie', 'tipo', 'pl_serie', 'rentab_mes', { field: 'rentab_12m', sort: 'desc' },
                   'subordinacao', 'inad_90', 'pdd_carteira']} />
        )}
        {tab === 'bcb' && <SetorBcb categoria={categoria} />}
        {tab === 'orig' && <SetorTabela url={`/api/setores/${categoria}/originadores`} cols={['nome_cedente', 'cedente', 'n_fundos', 'exposicao_estimada', 'maior_pct', { field: 'fundos', width: 500 }]}
          nota="Cedentes declarados na Tab. I do informe (até 9 por fundo). Nomes pela Receita (BrasilAPI). Exposição = % do cedente × carteira bruta do fundo - estimativa." />}
        {tab === 'gest' && <SetorTabela url={`/api/setores/${categoria}/gestores`} cols={['nome', 'n_fundos', 'pl_total', 'over90_mediana', 'subordinacao_mediana', 'retorno_jr_mediana']} />}
        {tab === 'rf' && <SetorTabela url={`/api/setores/${categoria}/redflags`} cols={[{ field: 'red_flag', headerName: 'Red flag', minWidth: 260, tooltipValueGetter: (p: any) => `${p.data?.definicao ?? ''}\n\nRegra: ${p.data?.regra ?? ''}` }, { field: 'regra', headerName: 'Regra (A = amarelo, V = vermelho)', width: 520, wrapText: true, autoHeight: true, tooltipValueGetter: (p: any) => p.data?.definicao }, 'n_fundos', 'amarelo', 'vermelho', 'pct_com_flag', 'pl_com_flag']}
          nota="Fundos da categoria no mês de referência; red flags calculadas pelo informe (biblioteca MCMS)." />}
        {tab === 'dist' && <Distribuicao categoria={categoria} />}
        {tab === 'estr' && <Estrutura categoria={categoria} />}
        {tab === 'comp' && <Comparativo categoria={categoria} />}
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

function SetorTabela({ url, cols, nota }: { url: string; cols: any[]; nota?: string }) {
  const d = useApi<Row[]>(url)
  return (
    <div className="stack" style={{ gap: 6 }}>
      <Loading q={d} />
      <DataGrid rows={d.data} exportUrl={url} height={520} cols={cols} pinned={1} />
      {nota && <p className="muted">{nota}</p>}
    </div>
  )
}

const METRICAS_BCB: [string, string, string][] = [
  ['inadimplencia', 'Inadimplência (% carteira, > 90 d)', 'pct100'], ['taxa', 'Taxa média de juros (% a.a.)', 'pct100'],
  ['saldo', 'Saldo da carteira (R$ milhões)', 'int'], ['concessoes', 'Concessões no mês (R$ milhões)', 'int'],
]

function SetorBcb({ categoria }: { categoria: string }) {
  const d = useApi<Row[]>(`/api/setores/${categoria}/bcb`)
  const porMetrica = useMemo(() => {
    const out: Record<string, { data: Row[]; series: { key: string; label: string }[] }> = {}
    for (const [m] of METRICAS_BCB) {
      const rows = (d.data ?? []).filter((r) => r.metrica === m)
      const nomes = [...new Set(rows.map((r) => r.nome))].slice(0, 8)
      const byDt = new Map<string, Row>()
      for (const r of rows) {
        const row = byDt.get(r.dt) ?? { dt: r.dt }
        row[`c${r.codigo}`] = r.valor
        byDt.set(r.dt, row)
      }
      const codes = [...new Set(rows.map((r) => r.codigo))].slice(0, 8)
      out[m] = { data: [...byDt.values()].sort((a, b) => (a.dt < b.dt ? -1 : 1)),
                 series: codes.map((c, i) => ({ key: `c${c}`, label: nomes[i] ?? String(c) })) }
    }
    return out
  }, [d.data])
  if (d.data && !d.data.length) return <div className="muted">Sem série do Banco Central mapeada para esta categoria (editar taxonomy/setor_bcb.yaml).</div>
  return (
    <div className="stack">
      <Loading q={d} />
      <div className="row"><span className="sub">Fonte: Banco Central, SGS (atualização automática no ETL diário).</span><div className="spacer" />
        <a className="btn" href={`/api/setores/${categoria}/bcb?formato=xlsx`}>⬇ Excel</a></div>
      <div className="grid2">
        {METRICAS_BCB.map(([m, t, f]) => porMetrica[m]?.data.length ? (
          <div key={m} className="card"><TimeLines title={t} data={porMetrica[m].data} series={porMetrica[m].series} fmt={f} /></div>) : null)}
      </div>
    </div>
  )
}

function Distribuicao({ categoria }: { categoria: string }) {
  const nav = useNavigate()
  const cat = useApi<any>('/api/catalogo', { staleTime: Infinity })
  const [m, setM] = useState('over90_carteira')
  const d = useApi<Row[]>(`/api/setores/${categoria}/distribuicao?metrica=${m}`)
  const meta = cat.data?.metricas?.find((x: Row) => x.metrica === m)
  const vals = (d.data ?? []).map((r) => r.valor).sort((a, b) => a - b)
  const q = (p: number) => (vals.length ? vals[Math.floor(p * (vals.length - 1))] : null)
  return (
    <div className="stack">
      <div className="row">
        <select value={m} onChange={(e) => setM(e.target.value)}>
          {cat.data?.metricas?.map((x: Row) => <option key={x.metrica} value={x.metrica}>{x.label}</option>)}
        </select>
        <span className="sub">n = {vals.length} · P25 {fmtValue(q(0.25), meta?.fmt)} · mediana {fmtValue(q(0.5), meta?.fmt)} · P75 {fmtValue(q(0.75), meta?.fmt)}</span>
      </div>
      <div className="legend"><span><i style={{ background: 'var(--s2)' }} />na carteira / watchlist</span><span><i style={{ background: 'var(--axis)' }} />demais fundos</span></div>
      {d.data && <RankBars fmt={meta?.fmt ?? 'pct'} destaque="" height={320}
        data={d.data.map((r) => ({ cnpj: r.cnpj, nome: r.nome, valor: r.valor, marca: r.listas || undefined }))}
        onClick={(c) => nav(`/fundo/${c}`)} />}
      <p className="muted">Fundos da categoria no mês de referência, sem os com erro de consistência. Clique numa barra para abrir a lâmina.</p>
    </div>
  )
}

/* ---------- estrutura atual x mínimos do regulamento, com referência editável da categoria ---------- */
function Estrutura({ categoria }: { categoria: string }) {
  const qc = useQueryClient()
  const url = `/api/setores/${categoria}/estrutura`
  const refUrl = `/api/categorias/${categoria}/referencia`
  const d = useApi<Row[]>(url)
  const refs = useApi<Row[]>(refUrl, { staleTime: 0 })
  const [edit, setEdit] = useState<Record<string, string>>({})
  const salvar = async (chave: string) => {
    const txt = (edit[chave] ?? '').trim()
    await send('PUT', refUrl, { chave, valor_num: txt === '' ? null : Number(txt.replace(',', '.')) / 100, fonte: 'referência interna' })
    setEdit({ ...edit, [chave]: '' })
    qc.invalidateQueries({ queryKey: [refUrl] }); qc.invalidateQueries({ queryKey: [url] })
  }
  const st = useMemo(() => {
    const c: Record<string, number> = {}
    for (const r of d.data ?? []) c[r.status_sub] = (c[r.status_sub] ?? 0) + 1
    return c
  }, [d.data])
  return (
    <div className="stack">
      <div className="card stack" style={{ gap: 6 }}>
        <b>Referência da categoria</b>
        <span className="muted">Vale para os fundos sem mínimo próprio (manual, leitura IA ou por regras do regulamento).
          Ao lado, a distribuição dos mínimos lidos nos regulamentos da categoria para calibrar.</span>
        <table className="simple">
          <thead><tr><th>Parâmetro</th><th className="r">Regulamentos lidos</th><th className="r">P25</th><th className="r">Mediana</th>
            <th className="r">P75</th><th className="r">Referência atual</th><th>Nova referência (%)</th><th /></tr></thead>
          <tbody>{refs.data?.map((r) => (
            <tr key={r.chave}><td>{r.label}</td><td className="r">{r.n_regulamentos}</td>
              <td className="r">{fmtValue(r.p25, 'pct')}</td><td className="r">{fmtValue(r.mediana, 'pct')}</td><td className="r">{fmtValue(r.p75, 'pct')}</td>
              <td className="r">{r.valor_num != null ? fmtValue(r.valor_num, 'pct') : '–'}{r.autor && <div className="muted">{r.autor}</div>}</td>
              <td><input type="text" style={{ width: 90 }} placeholder="ex.: 33,33" value={edit[r.chave] ?? ''}
                onChange={(e) => setEdit({ ...edit, [r.chave]: e.target.value })} /></td>
              <td><button style={{ padding: '0 8px' }} onClick={() => salvar(r.chave)}>{(edit[r.chave] ?? '') === '' && r.valor_num != null ? 'Limpar' : 'Salvar'}</button></td></tr>))}</tbody>
        </table>
      </div>
      <div className="sub">Subordinação vs mínimo: {['abaixo do mínimo', 'folga < 3 p.p.', 'ok', 'sem mínimo'].map((k) => `${k} ${st[k] ?? 0}`).join(' · ')}</div>
      <Loading q={d} />
      <DataGrid rows={d.data} exportUrl={url} height={560}
        cols={['nome', 'gestor', { field: 'pl', sort: 'desc' }, 'status_sub', 'subordinacao', 'sub_min_senior', 'sub_min_senior_fonte',
               'folga_sub_min_senior', 'jr_pl', 'jr_min_pl', 'jr_min_pl_fonte', 'folga_jr_min_pl', 'top1_cedente_frac',
               'limite_maior_cedente', 'limite_maior_cedente_fonte', 'limite_maior_sacado']} />
      <p className="muted">Mínimo por fundo: manual &gt; leitura IA &gt; leitura por regras &gt; referência da categoria. Maior cedente do informe
        é % da carteira; o limite do regulamento costuma ser % do PL - comparação aproximada.</p>
    </div>
  )
}
