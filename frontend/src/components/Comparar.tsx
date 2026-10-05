import { Fragment, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, type Row } from '../api'
import { fmtValue, mesAno } from '../fmt'
import { BandChart, RankBars, Scatter2 } from './Charts'
import { Loading } from './ui'

export type PeerOpts = { modo: string; grupo_id?: number; uma_por_gestora: boolean; excluir_erro: boolean; ignorar_sem_vencido: boolean }
export const defaultPeers: PeerOpts = { modo: 'categoria', uma_por_gestora: false, excluir_erro: true, ignorar_sem_vencido: true }

export function peerQs(p: PeerOpts) {
  const q = new URLSearchParams({ modo: p.modo, uma_por_gestora: String(p.uma_por_gestora), excluir_erro: String(p.excluir_erro),
    ignorar_sem_vencido: String(p.ignorar_sem_vencido) })
  if (p.modo === 'grupo' && p.grupo_id) q.set('grupo_id', String(p.grupo_id))
  return q.toString()
}

export function PeerSelector({ value, onChange }: { value: PeerOpts; onChange: (p: PeerOpts) => void }) {
  const grupos = useApi<Row[]>('/api/grupos', { staleTime: 30_000 })
  return (
    <div className="row" style={{ gap: 10 }}>
      <label className="sub">Comparar com</label>
      <select value={value.modo === 'grupo' ? `g${value.grupo_id}` : value.modo}
        onChange={(e) => {
          const v = e.target.value
          onChange(v.startsWith('g') ? { ...value, modo: 'grupo', grupo_id: Number(v.slice(1)) } : { ...value, modo: v, grupo_id: undefined })
        }}>
        <option value="categoria">Fundos da mesma categoria</option>
        <option value="mercado">Mercado inteiro</option>
        {grupos.data?.map((g) => <option key={g.id} value={`g${g.id}`}>Grupo: {g.nome}</option>)}
      </select>
      <label className="row" style={{ gap: 4 }} title="Fica só o maior fundo de cada gestora nas estatísticas">
        <input type="checkbox" checked={value.uma_por_gestora} onChange={(e) => onChange({ ...value, uma_por_gestora: e.target.checked })} />
        1 fundo por gestora
      </label>
      <label className="row" style={{ gap: 4 }} title="Pares com erro de consistência no informe ficam fora das estatísticas">
        <input type="checkbox" checked={value.excluir_erro} onChange={(e) => onChange({ ...value, excluir_erro: e.target.checked })} />
        excluir pares com dado inconsistente
      </label>
      <label className="row" style={{ gap: 4 }} title="Fundos que declaram zero vencido em todas as faixas e na Tab. I ficam fora das estatísticas de inadimplência (zero não verificável)">
        <input type="checkbox" checked={value.ignorar_sem_vencido} onChange={(e) => onChange({ ...value, ignorar_sem_vencido: e.target.checked })} />
        ignorar "zero vencido" declarado nas métricas de inadimplência
      </label>
    </div>
  )
}

const POS: Record<string, [string, string, string]> = {
  favoravel: ['▲', 'quartil favorável', 'var(--good-ink)'],
  desfavoravel: ['▼', 'quartil desfavorável', 'var(--critical)'],
  neutro: ['●', 'entre P25 e P75', 'var(--muted)'],
  contexto: ['○', 'contexto', 'var(--muted)'],
  'n/d': ['–', 'sem dado', 'var(--muted)'],
  zero_declarado: ['?', 'zero declarado (não verificável)', 'var(--muted)'],
}

export function Posicao({ p }: { p: string }) {
  const [ic, lb, color] = POS[p] ?? POS['n/d']
  return <span style={{ color, whiteSpace: 'nowrap' }} title={lb}>{ic} {lb}</span>
}

const NIVEL = ['', 'amarelo', 'vermelho']

export function RedFlagChip({ nivel }: { nivel: number | null }) {
  if (nivel == null) return <span className="muted">n/d</span>
  if (nivel === 0) return <span className="muted">ok</span>
  return <span className="badge" style={{ borderColor: nivel === 2 ? 'var(--critical)' : 'var(--warning)', color: 'var(--ink)', whiteSpace: 'nowrap' }}>
    <span style={{ width: 8, height: 8, borderRadius: 4, background: nivel === 2 ? 'var(--critical)' : 'var(--warning)' }} />
    {NIVEL[nivel]}
  </span>
}

export default function ComparePanel({ cnpj, peers }: { cnpj: string; peers: PeerOpts }) {
  const qs = peerQs(peers)
  const nav = useNavigate()
  const r = useApi<any>(`/api/comparar/${cnpj}?${qs}`)
  const [sel, setSel] = useState('over90_carteira')
  const [xy, setXy] = useState<[string, string]>(['over90_carteira', 'm21_retorno_jr_12m'])
  const serie = useApi<Row[]>(`/api/comparar/${cnpj}/serie?metrica=${sel}&meses=24&${qs}`)
  const rank = useApi<Row[]>(`/api/comparar/${cnpj}/dispersao?x=${sel}&y=${sel}&${qs}`)
  const disp = useApi<Row[]>(`/api/comparar/${cnpj}/dispersao?x=${xy[0]}&y=${xy[1]}&${qs}`)

  const metricas: Row[] = r.data?.metricas ?? []
  const byKey = useMemo(() => Object.fromEntries(metricas.map((m) => [m.metrica, m])), [metricas])
  const blocos = useMemo(() => [...new Set(metricas.map((m) => m.bloco))], [metricas])
  if (!r.data) return <Loading q={r} />
  const d = r.data
  const selM = byKey[sel]

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8 }}>
        <span className="sub">Data-base {mesAno(d.fundo.dt)}{d.fundo.defasado ? ' (defasado)' : ''} · {d.pares.descricao} · <b>n = {d.pares.n}</b> pares
          (sem o próprio fundo){d.pares.n_sem_vencido > 0 && peers.ignorar_sem_vencido
            ? ` · ${d.pares.n_sem_vencido} declaram zero vencido e ficam fora das métricas de inadimplência` : ''}
          {d.fundo.sem_vencido_declarado && <b> · este fundo declara zero vencido (não verificável)</b>}</span>
        <div className="spacer" />
        <a className="btn" href={`/api/comparar/${cnpj}?${qs}&formato=xlsx`}>⬇ Excel comparação</a>
        <a className="btn" href={`/api/fundos/${cnpj}/comite.xlsx?${qs}`}>⬇ Pacote do comitê</a>
      </div>
      <div className="kpis">
        {d.blocos.map((b: Row) => (
          <div key={b.bloco} className="kpi">
            <div className="l">{b.bloco}</div>
            <div className="row" style={{ gap: 10, marginTop: 4 }}>
              <span style={{ color: 'var(--good-ink)' }} title="métricas no quartil favorável">▲ {b.favoravel}</span>
              <span className="muted" title="entre P25 e P75">● {b.neutro}</span>
              <span style={{ color: 'var(--critical)' }} title="métricas no quartil desfavorável">▼ {b.desfavoravel}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="stack">
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="simple">
            <thead><tr><th>Métrica</th><th className="r">Fundo</th><th className="r">P25</th><th className="r">Mediana</th>
              <th className="r">P75</th><th className="r" title="Pares com dado nesta métrica">n</th><th>Posição</th><th className="r" title="Percentil do fundo entre os pares (n ≥ 5)">Pctl</th>
              <th className="r" title="Mediana do mercado inteiro">Mercado</th></tr></thead>
            <tbody>
              {blocos.map((b) => (
                <Fragment key={b}>
                  <tr><td colSpan={9} style={{ background: 'var(--surface-2)', fontWeight: 600 }}>{b}</td></tr>
                  {metricas.filter((m) => m.bloco === b).map((m) => (
                    <tr key={m.metrica} onClick={() => setSel(m.metrica)} title={`${m.codigo ? m.codigo + ' · ' : ''}${m.definicao}`}
                      style={{ cursor: 'pointer', background: sel === m.metrica ? 'var(--surface-2)' : undefined }}>
                      <td>{m.label}</td>
                      <td className="r"><b>{fmtValue(m.valor, m.fmt)}</b></td>
                      <td className="r">{fmtValue(m.p25, m.fmt)}</td>
                      <td className="r">{fmtValue(m.mediana, m.fmt)}</td>
                      <td className="r">{fmtValue(m.p75, m.fmt)}</td>
                      <td className="r muted">{m.n}</td>
                      <td><Posicao p={m.posicao} /></td>
                      <td className="r">{m.percentil == null ? '–' : Math.round(m.percentil * 100)}</td>
                      <td className="r muted">{fmtValue(m.mercado_mediana, m.fmt)}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid2" style={{ alignItems: 'start' }}>
          <div className="card">
            <h2>{selM?.label}</h2>
            <div className="muted" style={{ marginBottom: 8 }}>{selM?.definicao}</div>
            <Loading q={serie} />
            {serie.data && <BandChart data={serie.data} fmt={selM?.fmt ?? 'pct'} title="24 meses: fundo × pares" />}
          </div>
          <div className="card">
            <h3>Todos os pares nesta métrica (azul = fundo; clique para abrir)</h3>
            {rank.data && <RankBars fmt={selM?.fmt ?? 'pct'} destaque={cnpj}
              data={rank.data.filter((x) => x.x != null).map((x) => ({ cnpj: x.cnpj, nome: x.nome, valor: x.x }))}
              onClick={(c) => c !== cnpj && nav(`/fundo/${c}`)} />}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>Risco × retorno (ou qualquer par de métricas)</h2>
          <div className="spacer" />
          <select value={xy[0]} onChange={(e) => setXy([e.target.value, xy[1]])}>
            {metricas.map((m) => <option key={m.metrica} value={m.metrica}>X: {m.label}</option>)}
          </select>
          <select value={xy[1]} onChange={(e) => setXy([xy[0], e.target.value])}>
            {metricas.map((m) => <option key={m.metrica} value={m.metrica}>Y: {m.label}</option>)}
          </select>
        </div>
        {disp.data && <Scatter2 data={disp.data} xFmt={byKey[xy[0]]?.fmt} yFmt={byKey[xy[1]]?.fmt}
          xLabel={byKey[xy[0]]?.label} yLabel={byKey[xy[1]]?.label} onClick={(p) => !p.destaque && nav(`/fundo/${p.cnpj}`)} />}
      </div>

      <div className="card">
        <h2>Red flags (biblioteca MCMS, calculáveis pelo informe)</h2>
        <table className="simple">
          <thead><tr><th>Red flag</th><th>Fundo</th><th>Número do fundo</th><th>Regra</th><th className="r">% dos pares com flag</th></tr></thead>
          <tbody>{d.red_flags.map((f: Row) => (
            <tr key={f.id} title={f.codigo}><td>{f.nome}</td><td><RedFlagChip nivel={f.nivel} /></td><td>{f.detalhe}</td>
              <td className="muted">{f.regra}</td><td className="r">{fmtValue(f.pct_pares_com_flag, 'pct')}</td></tr>))}</tbody>
        </table>
        <p className="muted">RF03, RF05, RF07, RF11–RF13, RF18, RF20–RF22 e RF25 dependem de regulamento, relatório do gestor ou notícias: ficam no Roteiro de DD.</p>
      </div>

      <details className="card">
        <summary style={{ cursor: 'pointer' }}><b>Pares usados ({d.pares.n})</b></summary>
        <table className="simple" style={{ marginTop: 8 }}>
          <thead><tr><th>Fundo</th><th>Gestor</th><th className="r">PL</th><th>Qualidade</th></tr></thead>
          <tbody>{d.pares.lista.map((p: Row) => (
            <tr key={p.cnpj} style={{ cursor: 'pointer' }} onClick={() => nav(`/fundo/${p.cnpj}`)}>
              <td>{p.nome}</td><td className="muted">{p.gestor}</td><td className="r">{fmtValue(p.pl, 'brl')}</td><td>{p.q_status}</td></tr>))}</tbody>
        </table>
      </details>
    </div>
  )
}
