import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi, useTaxonomia, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'

export default function Pesquisa() {
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState(sp.get('q') ?? '')
  const [debounced, setDebounced] = useState(q)
  const categoria = sp.get('categoria') ?? ''
  const ativos = sp.get('inativos') !== '1'
  const tax = useTaxonomia()

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 300)
    return () => clearTimeout(t)
  }, [q])

  const url = `/api/fundos?limit=2000&q=${encodeURIComponent(debounced)}` +
    (categoria ? `&categoria=${categoria}` : '') + (ativos ? '' : '&ativos=false')
  const res = useApi<Row[]>(url)

  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp)
    if (v) n.set(k, v); else n.delete(k)
    setSp(n, { replace: true })
  }

  return (
    <div className="stack">
      <h1>Pesquisa de FIDCs</h1>
      <div className="card stack" style={{ gap: 10 }}>
        <input type="search" className="big" autoFocus placeholder="Nome do fundo ou CNPJ…" value={q}
          onChange={(e) => { setQ(e.target.value); set('q', e.target.value) }} />
        <div className="row">
          <select value={categoria} onChange={(e) => set('categoria', e.target.value)}>
            <option value="">Todas as categorias</option>
            {tax.data?.map((c) => <option key={c.id} value={c.id}>{c.grupo} · {c.nome}</option>)}
          </select>
          <label className="row" style={{ gap: 6 }}>
            <input type="checkbox" checked={!ativos} onChange={(e) => set('inativos', e.target.checked ? '1' : '')} />
            incluir fundos sem informe recente
          </label>
        </div>
      </div>
      <div className="card">
        <DataGrid rows={res.data} exportUrl={url} height={620}
          cols={['nome', 'cnpj', 'categoria_nome', 'gestor', 'admin', 'pl', 'inad_90', 'pdd_carteira',
                 'subordinacao', 'rentab_senior', 'ultimo_informe',
                 { field: 'revisar', valueFormatter: (p: any) => (p.value ? 'revisar' : ''), width: 90 },
                 { field: 'ia_diverge_informe', headerName: 'Regulamento x carteira', width: 130,
                   headerTooltip: 'A tese lida no regulamento não bate com a carteira declarada no informe CVM (Tab. II)',
                   valueFormatter: (p: any) => (p.value ? 'diverge' : '') }]} />
      </div>
    </div>
  )
}
