import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useMeta, type Row } from '../api'
import { StackedArea } from '../components/Charts'
import { DataGrid } from '../components/DataGrid'
import { Comparativo } from '../components/Comparativo'
import { Kpi, Loading } from '../components/ui'
import { mesAno } from '../fmt'

const MAX_SERIES = 8

export default function Mercado() {
  const meta = useMeta()
  const cats = useApi<Row[]>('/api/categorias')
  const hist = useApi<Row[]>('/api/mercado/historico')
  const estr = useApi<Row[]>('/api/mercado/estrutura')

  const { data, series } = useMemo(() => {
    if (!hist.data) return { data: [], series: [] }
    // grupos ordenados pelo PL no último mês; além de 7, vira "Outros" (paleta tem 8 cores fixas)
    const last = hist.data.reduce((m, r) => (r.dt > m ? r.dt : m), '')
    const rank = hist.data.filter((r) => r.dt === last).sort((a, b) => b.pl_total - a.pl_total).map((r) => r.grupo)
    const keep = new Set(rank.filter((g) => g !== 'Outros').slice(0, MAX_SERIES - 1))
    const byDt = new Map<string, Row>()
    for (const r of hist.data) {
      if (r.dt < '2016-01-01') continue
      const g = keep.has(r.grupo) ? r.grupo : 'Outros'
      const row = byDt.get(r.dt) ?? { dt: r.dt }
      row[g] = (row[g] ?? 0) + r.pl_total
      byDt.set(r.dt, row)
    }
    const order = [...rank.filter((g) => keep.has(g)), 'Outros']
    return { data: [...byDt.values()], series: order.map((g) => ({ key: g, label: g })) }
  }, [hist.data])

  const tot = useMemo(() => {
    const rows = cats.data ?? []
    const all = rows.reduce((s, r) => s + (r.pl_total ?? 0), 0)
    const fic = rows.find((r) => r.categoria === 'fic_fidc')?.pl_total ?? 0
    const n = rows.reduce((s, r) => s + (r.n_fundos ?? 0), 0)
    return { all, semFic: all - fic, n }
  }, [cats.data])

  return (
    <div className="stack">
      <div>
        <h1>Mercado de FIDCs</h1>
        <div className="sub">Informe mensal CVM · referência {mesAno(meta.data?.mes_referencia)} (último mês com ≥90% dos informes entregues)</div>
      </div>
      <div className="kpis">
        <Kpi k="n_fundos" label="Fundos/classes com PL" v={tot.n} />
        <Kpi k="pl_total" label="PL total (sem FIC-FIDC)" v={tot.semFic} compare="FIC-FIDC excluído para evitar dupla contagem" />
        <Kpi k="pl_total" label="PL total (com FIC-FIDC)" v={tot.all} />
      </div>
      <div className="card">
        <Loading q={hist} />
        {hist.data && <StackedArea title="PL por grupo de estratégia (inclui FIC-FIDC)" data={data} series={series} fmt="brl" height={300} />}
      </div>
      <div className="card">
        <Loading q={cats} />
        <DataGrid title="Categorias" rows={cats.data} exportUrl="/api/categorias" height={560}
          cols={[
            { field: 'categoria_nome', minWidth: 260,
              cellRenderer: (p: any) => <Link to={`/setores/${p.data.categoria}`}>{p.value}</Link> },
            'grupo', 'n_fundos',
            { field: 'pl_total', sort: 'desc' },
            'inad_90', 'inad_90_mediana', 'pdd_carteira', 'subordinacao', 'rentab_senior_mediana',
            'rentab_subordinada_mediana', 'roll_60_90_mediana', 'prazo_medio_dias_mediana',
          ]} />
        <p className="muted">
          Inad./PDD/subordinação da categoria = agregados ponderados (soma dos numeradores / soma dos denominadores).
          Medianas são por fundo, menos sensíveis a poucos fundos grandes ou com dado ruim.
        </p>
      </div>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Comparativo por estratégia</h2>
        <Comparativo />
      </div>
      <div className="card">
        <Loading q={estr} />
        <DataGrid title="Estrutura x regulamento por categoria" rows={estr.data} exportUrl="/api/mercado/estrutura" height={480}
          cols={[
            { field: 'categoria_nome', minWidth: 260,
              cellRenderer: (p: any) => <Link to={`/setores/${p.data.categoria}`}>{p.value}</Link> },
            { field: 'n_fundos', sort: 'desc' }, 'n_com_minimo', 'sub_min_p25', 'sub_min_mediana', 'sub_min_p75',
            'sub_min_referencia', 'subordinacao_mediana', 'folga_mediana', 'n_abaixo', 'n_folga_3pp', 'pl_abaixo', 'jr_min_mediana',
          ]} />
        <p className="muted">
          Subordinação mínima lida nos regulamentos (manual &gt; IA &gt; regras) e referência editável por categoria
          (aba "Estrutura x regulamento" de cada setor). Folga = subordinação atual (informe) − mínimo.
        </p>
      </div>
    </div>
  )
}
