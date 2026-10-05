import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { send, useApi, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'
import FundPicker from '../components/FundPicker'
import { Loading } from '../components/ui'

export default function Grupos() {
  const qc = useQueryClient()
  const grupos = useApi<Row[]>('/api/grupos', { staleTime: 0 })
  const [sel, setSel] = useState<number | null>(null)
  const [novo, setNovo] = useState('')
  const g = grupos.data?.find((x) => x.id === (sel ?? grupos.data?.[0]?.id))
  const painel = useApi<Row[]>(g ? `/api/grupos/${g.id}/painel` : null, { staleTime: 0 })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['/api/grupos'] }); if (g) qc.invalidateQueries({ queryKey: [`/api/grupos/${g.id}/painel`] }) }

  const criar = async () => { const r = await send('POST', '/api/grupos', { nome: novo }); setNovo(''); setSel(r.id); refresh() }
  const membro = async (cnpj: string, incluir: boolean, motivo?: string) => {
    await send('PUT', `/api/grupos/${g!.id}/membros`, { cnpj, incluir, motivo }); refresh()
  }

  return (
    <div className="stack">
      <div>
        <h1>Grupos de pares</h1>
        <div className="sub">Benchmarks montados pela equipe (ex.: Pares MCMS). A coluna "incluir" manda nas estatísticas, como o filtro S/N da Base MCMS.</div>
      </div>
      <div className="card row">
        <select value={g?.id ?? ''} onChange={(e) => setSel(Number(e.target.value))}>
          {grupos.data?.map((x) => <option key={x.id} value={x.id}>{x.nome} ({x.membros.filter((m: Row) => m.incluir).length} incluídos)</option>)}
        </select>
        <div className="spacer" />
        <input type="text" placeholder="Nome do novo grupo" value={novo} onChange={(e) => setNovo(e.target.value)} />
        <button disabled={!novo.trim()} onClick={criar}>Criar grupo</button>
      </div>
      <Loading q={grupos} />
      {g && (
        <>
          <div className="card stack" style={{ gap: 8 }}>
            <div className="sub">{g.descricao}</div>
            <div className="row">
              <FundPicker onPick={(r) => membro(r.cnpj, true, 'Adicionado pela equipe')} placeholder="Adicionar fundo ao grupo…" />
              <label className="row" style={{ gap: 4 }}>
                <input type="checkbox" checked={!!g.uma_por_gestora} onChange={async (e) => {
                  await send('PUT', `/api/grupos/${g.id}`, { nome: g.nome, descricao: g.descricao, uma_por_gestora: e.target.checked }); refresh()
                }} /> aplicar automaticamente "1 fundo por gestora"
              </label>
              <button onClick={async () => { if (confirm(`Apagar o grupo ${g.nome}?`)) { await send('DELETE', `/api/grupos/${g.id}`); setSel(null); refresh() } }}>Apagar grupo</button>
            </div>
          </div>
          <div className="card">
            <DataGrid title="Membros e métricas" rows={painel.data} exportUrl={`/api/grupos/${g.id}/painel`} height={560}
              cols={[
                'nome',
                { field: 'incluir', headerName: 'Incluir', width: 90, cellRenderer: (p: any) => (
                  <input type="checkbox" checked={!!p.value} onChange={(e) => membro(p.data.cnpj, e.target.checked, p.data.motivo)} />) },
                { field: 'motivo', width: 260 }, 'gestor', 'q_status', 'pl', 'over90_carteira', 'pdd_carteira', 'pdd_over90',
                'subordinacao', 'jr_pl', 'm01_jr_pdd', 'm02_jr_vencidos360', 'm05_recompra_carteira', 'm16_custo_credito',
                'm19_excesso_spread', 'm21_retorno_jr_12m', 'retorno_jr_pct_cdi', 'm23_pmr', 'm29_colchao_carteira',
                'top1_cedente_pct', 'm17_f30_media',
                { field: 'cnpj', headerName: '', width: 170, sortable: false, filter: false, cellRenderer: (p: any) => (
                  <span><Link to={`/comparar?cnpj=${p.value}`}>comparar</Link>{' · '}
                    <button style={{ padding: '0 6px' }} onClick={async () => { await send('DELETE', `/api/grupos/${g.id}/membros/${p.value}`); refresh() }}>remover</button></span>) },
              ]} />
          </div>
        </>
      )}
    </div>
  )
}
