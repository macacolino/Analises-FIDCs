import { useMemo, useState } from 'react'
import { useApi, type Row } from '../api'
import { TimeLines } from '../components/Charts'
import { DataGrid } from '../components/DataGrid'
import { Loading } from '../components/ui'

export default function Qualidade() {
  const checks = useApi<Row[]>('/api/qualidade/checks', { staleTime: Infinity })
  const resumo = useApi<{ por_mes: Row[]; por_checagem: Row[] }>('/api/qualidade/resumo')
  const [check, setCheck] = useState('')
  const url = `/api/qualidade/fundos${check ? `?check=${check}` : ''}`
  const fundos = useApi<Row[]>(url)
  const serie = useMemo(() => (resumo.data?.por_mes ?? []).map((r) => ({
    ...r, pct_erro: r.com_erro / r.n_informes, pct_alerta: r.com_alerta / r.n_informes })), [resumo.data])
  const ultimo = useMemo(() => {
    const pc = resumo.data?.por_checagem ?? []
    const last = pc.reduce((m, r) => (r.dt > m ? r.dt : m), '')
    return Object.fromEntries(pc.filter((r) => r.dt === last).map((r) => [r.id, r.n_fundos]))
  }, [resumo.data])

  return (
    <div className="stack">
      <div>
        <h1>Qualidade dos dados</h1>
        <div className="sub">Checagens de consistência em cada informe mensal. Pares com erro ficam fora das estatísticas de comparação por padrão.</div>
      </div>
      <div className="card">
        <Loading q={resumo} />
        {serie.length > 0 && <TimeLines title="% dos informes com erro / com alerta" data={serie} fmt="pct"
          series={[{ key: 'pct_erro', label: 'Com erro' }, { key: 'pct_alerta', label: 'Com alerta (sem erro)' }]} />}
      </div>
      <div className="card" style={{ overflowX: 'auto' }}>
        <h2>Checagens</h2>
        <table className="simple">
          <thead><tr><th>#</th><th>Checagem</th><th>Severidade</th><th>O que fazer</th><th className="r">Fundos no mês de referência</th></tr></thead>
          <tbody>{checks.data?.map((c) => (
            <tr key={c.id} style={{ cursor: 'pointer', background: check === c.id ? 'var(--surface-2)' : undefined }}
              onClick={() => setCheck(check === c.id ? '' : c.id)}>
              <td>{c.id}</td><td>{c.descricao}</td><td className={`sev-${c.severidade}`}>{c.severidade}</td>
              <td className="muted">{c.recomendacao}</td><td className="r">{ultimo[c.id] ?? 0}</td></tr>))}</tbody>
        </table>
        <p className="muted">Clique numa checagem para filtrar a lista abaixo.</p>
      </div>
      <div className="card">
        <DataGrid title={`Fundos com falha no mês de referência${check ? ` (${check})` : ''}`} rows={fundos.data} exportUrl={url} height={520}
          cols={['nome', 'categoria_nome', 'pl', 'id', { field: 'severidade', width: 100 }, { field: 'descricao', width: 420 },
                 { field: 'valor', headerName: 'Valor', width: 110 }]} />
      </div>
    </div>
  )
}
