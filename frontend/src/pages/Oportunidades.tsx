import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useTaxonomia, type Row } from '../api'
import { TimeLines } from '../components/Charts'
import { DataGrid } from '../components/DataGrid'
import { Kpi, Loading, Tabs } from '../components/ui'
import { mesAno } from '../fmt'

export default function Oportunidades() {
  const tax = useTaxonomia()
  const m = useApi<{ serie: Row[]; resumo: Row[]; total: Row[]; n_excluidos: number }>('/api/oportunidades/mercado')
  const [sel, setSel] = useState<string[] | null>(null)
  const [tab, setTab] = useState<'ofertas' | 'fundos' | 'novos' | 'cat'>('ofertas')
  const [dias, setDias] = useState(90)
  const [meses, setMeses] = useState(3)
  const [cat, setCat] = useState('')
  const fundosUrl = `/api/oportunidades/fundos?meses=${meses}${cat ? `&categoria=${cat}` : ''}`
  const fundos = useApi<Row[]>(tab === 'fundos' ? fundosUrl : null)
  const novos = useApi<Row[]>(tab === 'novos' ? '/api/oportunidades/novos?meses=6' : null)
  const ofertasUrl = `/api/oportunidades/ofertas?dias=${dias}${cat ? `&categoria=${cat}` : ''}`
  const ofertas = useApi<Row[]>(tab === 'ofertas' ? ofertasUrl : null)

  const top = useMemo(() => (m.data?.resumo ?? []).slice(0, 5).map((r) => r.categoria), [m.data])
  const escolhidas = sel ?? top
  const porCat = useMemo(() => {
    const byDt = new Map<string, Row>()
    for (const r of m.data?.serie ?? []) {
      if (!escolhidas.includes(r.categoria)) continue
      const row = byDt.get(r.dt) ?? { dt: r.dt }
      row[r.categoria] = r.captacao
      byDt.set(r.dt, row)
    }
    return [...byDt.values()].sort((a, b) => (a.dt < b.dt ? -1 : 1))
  }, [m.data, escolhidas])
  const nome = (id: string) => tax.data?.find((c) => c.id === id)?.nome ?? id
  const ult = m.data?.total?.[m.data.total.length - 1]
  const media12 = useMemo(() => {
    const t = (m.data?.total ?? []).slice(-12)
    return t.length ? t.reduce((s, r) => s + r.captacao, 0) / t.length : null
  }, [m.data])

  return (
    <div className="stack">
      <div>
        <h1>Novas oportunidades</h1>
        <div className="sub">Como o mercado está captando e quais fundos estão captando ou acabaram de nascer. Captação, resgates e
          amortizações da Tab. X.4 do informe CVM (todas as classes de cota); ofertas registradas na CVM (dados abertos, diário) –
          a oferta aparece antes da captação chegar ao informe.</div>
      </div>
      <Loading q={m} />
      {m.data && (
        <>
          <div className="kpis">
            <Kpi k="captacao" label={`Captação em ${mesAno(ult?.dt)}`} v={ult?.captacao} />
            <Kpi k="captacao" label="Média mensal 12m" v={media12} />
            <Kpi k="liquida" label={`Captação líquida em ${mesAno(ult?.dt)}`} v={ult?.liquida} />
            <Kpi k="novos_3m" label={`Fundos novos em ${mesAno(ult?.dt)}`} v={ult?.n_novos} />
          </div>
          <div className="grid2">
            <div className="card">
              <TimeLines title="Mercado: captação e captação líquida por mês" data={m.data.total} fmt="brl"
                series={[{ key: 'captacao', label: 'Captação' }, { key: 'liquida', label: 'Líquida (− resgates − amortizações)' }]} />
            </div>
            <div className="card">
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                <span className="sub">Captação mensal por categoria:</span>
                <select value="" onChange={(e) => e.target.value && setSel([...escolhidas, e.target.value].slice(-6))}>
                  <option value="">+ adicionar categoria</option>
                  {m.data.resumo.filter((r) => !escolhidas.includes(r.categoria)).map((r) => <option key={r.categoria} value={r.categoria}>{r.categoria_nome}</option>)}
                </select>
                {escolhidas.map((c) => <span key={c} className="chip">{nome(c)}<button title="Remover" onClick={() => setSel(escolhidas.filter((x) => x !== c))}>×</button></span>)}
              </div>
              <TimeLines data={porCat} fmt="brl" series={escolhidas.map((c) => ({ key: c, label: nome(c) }))} />
            </div>
          </div>
          {m.data.n_excluidos > 0 && <p className="muted">{m.data.n_excluidos} registros de captação fora do padrão (captação maior que
            1,5x o PL mais resgates e amortizações do mês) ficaram de fora como erro de preenchimento; a lista está no Excel.</p>}
        </>
      )}
      <div className="card">
        <Tabs value={tab} onChange={setTab} options={[['ofertas', 'Ofertas registradas (CVM)'], ['fundos', 'Fundos captando'], ['novos', 'Fundos novos (6 meses)'], ['cat', 'Por categoria']]} />
        {tab === 'ofertas' && (
          <DataGrid rows={ofertas.data} exportUrl={ofertasUrl} height={600}
            extra={(
              <>
                <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
                  {[30, 90, 180, 365].map((n) => <option key={n} value={n}>últimos {n} dias</option>)}
                </select>
                <select value={cat} onChange={(e) => setCat(e.target.value)}>
                  <option value="">Todas as categorias</option>
                  {tax.data?.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                </select>
              </>
            )}
            cols={['nome', 'categoria_nome', { field: 'data_registro', sort: 'desc' }, 'data_requerimento', 'valor_registrado', 'status',
                   'publico_alvo', 'tipo_oferta', 'emissao', 'rito', 'lider', 'gestor', 'pl', 'subordinacao',
                   { field: 'fundo_novo_sem_informe', valueFormatter: (p: any) => (p.value ? 'sim' : '') },
                   { field: 'lastro', width: 420 }, 'data_encerramento', 'cnpj_emissor']} />
        )}
        {tab === 'fundos' && (
          <DataGrid rows={fundos.data} exportUrl={fundosUrl} height={600}
            extra={(
              <>
                <select value={meses} onChange={(e) => setMeses(Number(e.target.value))}>
                  {[1, 3, 6, 12].map((n) => <option key={n} value={n}>últimos {n} {n === 1 ? 'mês' : 'meses'}</option>)}
                </select>
                <select value={cat} onChange={(e) => setCat(e.target.value)}>
                  <option value="">Todas as categorias</option>
                  {tax.data?.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                </select>
              </>
            )}
            cols={['nome', 'categoria_nome', 'gestor', { field: 'captacao', sort: 'desc' }, 'liquida', 'cap_senior', 'cap_mezanino',
                   'cap_sub', 'captacao_pct_pl', 'meses_captando', 'pl', { field: 'novo', valueFormatter: (p: any) => (p.value ? 'novo' : '') },
                   'primeiro_informe', 'ultima_oferta_registro', 'ultima_oferta_valor', 'ultima_oferta_status', 'ofertas_12m',
                   'valor_ofertas_12m', 'subordinacao', 'jr_pl', 'over90_carteira', { field: 'lastro', width: 420 }, 'q_status', 'admin']} />
        )}
        {tab === 'novos' && (
          <DataGrid rows={novos.data} exportUrl="/api/oportunidades/novos?meses=6" height={600}
            cols={['nome', 'categoria_nome', 'gestor', { field: 'primeiro_informe', sort: 'desc' }, 'ultima_oferta_registro',
                   'ultima_oferta_valor', 'ultima_oferta_publico', 'pl', 'subordinacao', 'jr_pl',
                   { field: 'lastro', width: 460 }, 'q_status', 'admin']} />
        )}
        {tab === 'cat' && m.data && (
          <DataGrid rows={m.data.resumo} exportUrl="/api/oportunidades/mercado" height={600}
            cols={[{ field: 'categoria_nome', minWidth: 260, cellRenderer: (p: any) => <Link to={`/setores/${p.data.categoria}`}>{p.value}</Link> },
                   'cap_media_3m', 'cap_media_12m_ant', { field: 'aceleracao', sort: 'desc' }, 'liquida_3m', 'captacao_12m',
                   'liquida_12m', 'novos_3m', 'novos_12m']} />
        )}
      </div>
    </div>
  )
}
