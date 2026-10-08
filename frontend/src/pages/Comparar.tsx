import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi, xlsxUrl, type Row } from '../api'
import ComparePanel, { defaultPeers, PeerSelector, type PeerOpts } from '../components/Comparar'
import FundPicker from '../components/FundPicker'
import { Loading, Tabs } from '../components/ui'
import { fmtValue, mesAno } from '../fmt'

export default function Comparar() {
  const [sp, setSp] = useSearchParams()
  const cnpj = sp.get('cnpj') ?? ''
  const lista = (sp.get('lista') ?? '').split(',').filter(Boolean)
  const [tab, setTab] = useState<'pares' | 'lado'>(sp.get('lista') ? 'lado' : 'pares')
  const [peers, setPeers] = useState<PeerOpts>(defaultPeers)
  const nome = useApi<Row[]>(cnpj ? `/api/fundos?limit=1&ativos=false&q=${cnpj}` : null)
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }

  return (
    <div className="stack">
      <div>
        <h1>Comparar</h1>
        <div className="sub">Fundo contra os pares (categoria ou mercado) ou vários fundos lado a lado.</div>
      </div>
      <Tabs value={tab} onChange={setTab} options={[['pares', 'Fundo × pares'], ['lado', 'Lado a lado']]} />
      {tab === 'pares' && (
        <>
          <div className="card stack" style={{ gap: 10 }}>
            <div className="row">
              <FundPicker onPick={(r) => set('cnpj', r.cnpj)} />
              {cnpj && <span className="chip">{nome.data?.[0]?.nome ?? cnpj}
                <Link to={`/fundo/${cnpj}`}>lâmina ↗</Link></span>}
            </div>
            <PeerSelector value={peers} onChange={setPeers} />
          </div>
          {cnpj ? <ComparePanel cnpj={cnpj} peers={peers} /> : <div className="card muted">Escolha um fundo para comparar.</div>}
        </>
      )}
      {tab === 'lado' && <LadoALado lista={lista} setLista={(l) => set('lista', l.join(','))} />}
    </div>
  )
}

function LadoALado({ lista, setLista }: { lista: string[]; setLista: (l: string[]) => void }) {
  const url = lista.length ? `/api/lado-a-lado?cnpjs=${lista.join(',')}` : null
  const d = useApi<{ metricas: Row[]; fundos: Row[] }>(url)
  const fundos = d.data?.fundos ?? []
  return (
    <div className="stack">
      <div className="card row">
        <FundPicker onPick={(r) => !lista.includes(r.cnpj) && lista.length < 8 && setLista([...lista, r.cnpj])}
          placeholder="Adicionar fundo (até 8)…" />
        {url && <a className="btn" href={xlsxUrl(url)}>⬇ Excel</a>}
      </div>
      <Loading q={d} />
      {fundos.length > 0 && (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="simple">
            <thead>
              <tr><th>Métrica</th>{fundos.map((f) => (
                <th key={f.cnpj} className="r" style={{ minWidth: 140 }}>
                  <Link to={`/fundo/${f.cnpj}`}>{f.nome.slice(0, 40)}</Link>
                  <div className="muted">{f.categoria_nome} · {mesAno(f.dt)}</div>
                  <button style={{ padding: '0 6px', marginTop: 4 }} onClick={() => setLista(lista.filter((c) => c !== f.cnpj))}>remover</button>
                </th>))}</tr>
            </thead>
            <tbody>
              {d.data!.metricas.map((m) => {
                const vals = fundos.map((f) => m[f.cnpj]).filter((v) => v != null) as number[]
                const best = m.sentido > 0 ? Math.max(...vals) : Math.min(...vals)
                const worst = m.sentido > 0 ? Math.min(...vals) : Math.max(...vals)
                return (
                  <tr key={m.metrica}>
                    <td>{m.label}<div className="muted">{m.bloco}</div></td>
                    {fundos.map((f) => {
                      const v = m[f.cnpj]
                      const cls = m.sentido === 0 || vals.length < 2 || v == null ? '' : v === best ? 'best' : v === worst ? 'worst' : ''
                      return <td key={f.cnpj} className={`r ${cls}`}>{cls === 'best' ? '▲ ' : cls === 'worst' ? '▼ ' : ''}{fmtValue(v, m.fmt)}</td>
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="muted">▲ melhor e ▼ pior entre os fundos escolhidos, no sentido de cada métrica (métricas de contexto sem marcação).</p>
        </div>
      )}
    </div>
  )
}
