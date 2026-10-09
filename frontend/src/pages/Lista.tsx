import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { send, useApi, useMeta, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'
import { Loading } from '../components/ui'
import { brl, fmtDate } from '../fmt'

const TITULO = { carteira: 'Carteira', watchlist: 'Watchlist' }

export default function Lista({ tipo }: { tipo: 'carteira' | 'watchlist' }) {
  const qc = useQueryClient()
  const meta = useMeta()
  const url = `/api/listas/${tipo}`
  const painel = useApi<Row[]>(url, { staleTime: 0 })
  const [verEventos, setVerEventos] = useState(false)
  const eventos = useApi<Row[]>(verEventos ? `${url}/eventos?dias=90` : null)
  const refresh = () => qc.invalidateQueries({ queryKey: [url] })

  const remover = async (cnpj: string) => {
    if (!confirm('Remover este fundo da lista?')) return
    await send('DELETE', `${url}/${cnpj}`); refresh()
  }

  return (
    <div className="stack">
      <div className="row">
        <div>
          <h1>{TITULO[tipo]}</h1>
          <div className="sub">Atualiza sozinha quando a CVM publica novos informes (ETL diário). Alertas comparam o último mês com 3 meses antes.</div>
        </div>
        <div className="spacer" />
        <a className="btn" href={`${url}/relatorio.xlsx`}>⬇ Relatório mensal (Excel)</a>
      </div>
      {meta.data?.persistencia?.erro && (
        <div className="alert sev-alta"><span className="dot" aria-hidden />
          <span><b>Atenção:</b> as alterações desta lista podem não estar sendo salvas ({meta.data.persistencia.erro}).</span></div>
      )}
      <Adicionar tipo={tipo} onDone={refresh} />
      <div className="card">
        <Loading q={painel} />
        <DataGrid rows={painel.data} exportUrl={url} height={480}
          cols={[
            'nome', 'categoria_nome',
            { field: 'alertas', width: 95, cellStyle: (p: any) => (p.value > 0 ? { color: 'var(--critical)', fontWeight: 600 } : null) },
            'pl', 'd3m_pl', 'inad_90', 'd3m_inad_90', 'setor_inad_90', 'pdd_carteira', 'd3m_pdd_carteira',
            'subordinacao', 'd3m_subordinacao', 'setor_subordinacao', 'rentab_senior', 'setor_rentab_senior',
            'rentab_subordinada', 'roll_60_90', 'inad_90_lag12', 'recompra_subst_3m_carteira', 'top1_cedente_pct',
            'dt', 'gestor', { field: 'alertas_desc', width: 400 }, { field: 'tese', width: 300 },
            { field: 'cnpj', headerName: '', width: 90, sortable: false, filter: false,
              cellRenderer: (p: any) => <button style={{ padding: '0 8px' }} onClick={() => remover(p.value)}>remover</button> },
          ]} />
      </div>
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>Eventos FNET (90 dias)</h2>
          <span className="muted">fatos relevantes, assembleias, alterações de regulamento, relatórios</span>
          <div className="spacer" />
          {!verEventos && <button onClick={() => setVerEventos(true)}>Carregar eventos</button>}
        </div>
        {verEventos && <Loading q={eventos} />}
        {eventos.data && (
          <table className="simple" style={{ marginTop: 10 }}>
            <thead><tr><th>Entrega</th><th>Fundo</th><th>Categoria</th><th>Tipo</th><th /></tr></thead>
            <tbody>{eventos.data.map((e) => (
              <tr key={e.id}><td className="num">{fmtDate(e.data_entrega)}</td>
                <td><Link to={`/fundo/${e.cnpj}`}>{e.fundo}</Link></td><td>{e.categoria}</td><td>{e.tipo}</td>
                <td><a href={e.link} target="_blank" rel="noreferrer">abrir ↗</a></td></tr>))}
              {!eventos.data.length && <tr><td colSpan={5} className="muted">Nenhum evento no período.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function Adicionar({ tipo, onDone }: { tipo: string; onDone: () => void }) {
  const [q, setQ] = useState('')
  const [deb, setDeb] = useState('')
  const [tese, setTese] = useState('')
  useEffect(() => { const t = setTimeout(() => setDeb(q), 300); return () => clearTimeout(t) }, [q])
  const res = useApi<Row[]>(deb.length >= 3 ? `/api/fundos?limit=8&q=${encodeURIComponent(deb)}` : null)
  const add = async (cnpj: string) => {
    await send('POST', `/api/listas/${tipo}`, { cnpj, tese: tese || null })
    setQ(''); setDeb(''); setTese(''); onDone()
  }
  return (
    <div className="card stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8 }}>
        <input type="search" style={{ flex: 2, minWidth: 240 }} placeholder="Adicionar fundo: nome ou CNPJ…" value={q} onChange={(e) => setQ(e.target.value)} />
        <input type="text" style={{ flex: 3, minWidth: 240 }} placeholder="Tese / motivo (opcional)" value={tese} onChange={(e) => setTese(e.target.value)} />
      </div>
      {res.data && (
        <table className="simple">
          <tbody>{res.data.map((r) => (
            <tr key={r.cnpj}><td>{r.nome}</td><td className="muted">{r.categoria_nome}</td><td className="r">{brl(r.pl)}</td>
              <td className="r"><button onClick={() => add(r.cnpj)}>+ adicionar</button></td></tr>))}
            {!res.data.length && <tr><td className="muted">Nada encontrado.</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  )
}
