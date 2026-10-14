import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { useDic, type Row } from '../api'
import { colFmt, colLabel, fmtValue } from '../fmt'
import { SERIES } from './Charts'

/** eixos prontos: pares que respondem uma pergunta de análise */
export const PARES: { nome: string; x: string; y: string }[] = [
  { nome: 'Risco × remuneração da sênior', x: 'inad_90', y: 'spread_senior_aa' },
  { nome: 'Colchão × remuneração da sênior', x: 'subordinacao', y: 'spread_senior_aa' },
  { nome: 'Folga sobre a subordinação mínima', x: 'sub_min_senior', y: 'subordinacao' },
  { nome: 'Inadimplência × provisão', x: 'inad_90', y: 'pdd_carteira' },
  { nome: 'Custo × tamanho', x: 'pl', y: 'taxa_gestao' },
  { nome: 'Taxa das aquisições × inadimplência', x: 'taxa_desconto_aa', y: 'inad_90' },
  { nome: 'Sub 12m (% CDI) × inadimplência', x: 'inad_90', y: 'rentab_subordinada_12m_pct_cdi' },
]

const NUMERICOS = ['pct', 'pct100', 'brl', 'int', 'x', 'dias', 'num']

/** valor na unidade da tela (% como %, R$ em milhões) */
function tela(v: any, f?: string): number | null {
  if (v == null || v === '' || typeof v !== 'number' || !Number.isFinite(v)) return null
  return f === 'pct' ? v * 100 : f === 'brl' ? v / 1e6 : v
}
function quantil(xs: number[], q: number) {
  const s = [...xs].sort((a, b) => a - b)
  if (!s.length) return 0
  const i = (s.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i)
  return s[lo] + (s[hi] - s[lo]) * (i - lo)
}

export function Dispersao({ rows, campos }: { rows: Row[]; campos: string[] }) {
  const { data: dic } = useDic()
  const nav = useNavigate()
  const [par, setPar] = useState(0)
  const [x, setX] = useState(PARES[0].x)
  const [y, setY] = useState(PARES[0].y)
  const [cortar, setCortar] = useState(true)
  const [logX, setLogX] = useState(false)
  const fx = colFmt(dic, x), fy = colFmt(dic, y)
  const numericos = campos.filter((c) => NUMERICOS.includes(colFmt(dic, c) ?? ''))
    .sort((a, b) => colLabel(dic, a).localeCompare(colLabel(dic, b), 'pt-BR'))

  const { grupos, n, mx, my, dom } = useMemo(() => {
    let pts = rows.map((r) => ({ r, x: tela(r[x], fx), y: tela(r[y], fy), z: r.pl ?? 0 }))
      .filter((p) => p.x != null && p.y != null && (!logX || p.x > 0)) as { r: Row; x: number; y: number; z: number }[]
    let dom: { x?: [number, number]; y?: [number, number] } = {}
    if (cortar && pts.length > 20) {   // extremos (2,5% de cada ponta) achatam o gráfico: ficam fora da escala
      const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y)
      const x0 = quantil(xs, 0.025), x1 = quantil(xs, 0.975), y0 = quantil(ys, 0.025), y1 = quantil(ys, 0.975)
      pts = pts.filter((p) => p.x >= x0 && p.x <= x1 && p.y >= y0 && p.y <= y1)
      dom = { x: [x0, x1], y: [y0, y1] }
    }
    const porGrupo = new Map<string, typeof pts>()
    for (const p of pts) {
      const g = p.r.categoria_nome ? String(p.r.grupo ?? p.r.categoria_nome) : 'Sem categoria'
      porGrupo.set(g, [...(porGrupo.get(g) ?? []), p])
    }
    // 7 grupos com mais fundos + "Outros" (paleta de 8 cores)
    const ord = [...porGrupo.entries()].sort((a, b) => b[1].length - a[1].length)
    const grupos = ord.slice(0, 7).map(([g, ps]) => ({ g, ps }))
    const resto = ord.slice(7).flatMap(([, ps]) => ps)
    if (resto.length) grupos.push({ g: 'Outros', ps: resto })
    return { grupos, n: pts.length, mx: quantil(pts.map((p) => p.x), 0.5), my: quantil(pts.map((p) => p.y), 0.5), dom }
  }, [rows, x, y, fx, fy, cortar, logX])

  const fmtEixo = (v: number, f?: string) =>
    f === 'brl' ? `${v.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}` :
    (f === 'pct' || f === 'pct100') ? `${v.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%` :
    v.toLocaleString('pt-BR', { maximumFractionDigits: 1 })
  const unid = (f?: string) => (f === 'brl' ? ' (R$ mi)' : '')

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <select value={par} onChange={(e) => {
          const i = Number(e.target.value); setPar(i)
          if (i >= 0) { setX(PARES[i].x); setY(PARES[i].y); setLogX(PARES[i].x === 'pl') }
        }}>
          {PARES.map((p, i) => <option key={p.nome} value={i}>{p.nome}</option>)}
          <option value={-1}>Escolher eixos…</option>
        </select>
        <label className="row" style={{ gap: 4 }}>X
          <select value={x} onChange={(e) => { setX(e.target.value); setPar(-1) }}>
            {numericos.map((c) => <option key={c} value={c}>{colLabel(dic, c)}</option>)}
          </select>
        </label>
        <label className="row" style={{ gap: 4 }}>Y
          <select value={y} onChange={(e) => { setY(e.target.value); setPar(-1) }}>
            {numericos.map((c) => <option key={c} value={c}>{colLabel(dic, c)}</option>)}
          </select>
        </label>
        <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={cortar}
          onChange={(e) => setCortar(e.target.checked)} />cortar extremos (2,5% de cada ponta)</label>
        <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={logX}
          onChange={(e) => setLogX(e.target.checked)} />X em escala log</label>
      </div>
      <div className="muted" style={{ fontSize: 12 }}>
        {n.toLocaleString('pt-BR')} fundos com os dois valores (segue os filtros acima) · tamanho do ponto = PL ·
        linhas tracejadas = medianas, dividem em quadrantes · clique no ponto abre o fundo
      </div>
      <div style={{ height: 460 }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 10 }}>
            <CartesianGrid stroke="var(--grid)" />
            <XAxis type="number" dataKey="x" name={colLabel(dic, x)} scale={logX ? 'log' : 'auto'}
              domain={logX ? ['auto', 'auto'] : (dom.x ?? ['auto', 'auto'])} allowDataOverflow
              tickFormatter={(v) => fmtEixo(v, fx)} stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 11 }}
              label={{ value: colLabel(dic, x) + unid(fx), position: 'insideBottom', offset: -18, fill: 'var(--ink-2)', fontSize: 12 }} />
            <YAxis type="number" dataKey="y" name={colLabel(dic, y)} domain={dom.y ?? ['auto', 'auto']} allowDataOverflow
              tickFormatter={(v) => fmtEixo(v, fy)} stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 11 }}
              label={{ value: colLabel(dic, y) + unid(fy), angle: -90, position: 'insideLeft', fill: 'var(--ink-2)', fontSize: 12 }} />
            <ZAxis type="number" dataKey="z" range={[14, 260]} />
            <ReferenceLine x={mx} stroke="var(--axis)" strokeDasharray="4 4" />
            <ReferenceLine y={my} stroke="var(--axis)" strokeDasharray="4 4" />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => {
              const p = payload?.[0]?.payload as any
              if (!p) return null
              return (
                <div className="card" style={{ padding: 8, fontSize: 12 }}>
                  <b>{p.r.nome}</b><br />
                  {p.r.gestor && <>{p.r.gestor}<br /></>}
                  {colLabel(dic, x)}: {fmtValue(p.r[x], fx)}<br />
                  {colLabel(dic, y)}: {fmtValue(p.r[y], fy)}<br />
                  PL: {fmtValue(p.r.pl, 'brl')}
                </div>
              )
            }} />
            {grupos.map((g, i) => (
              <Scatter key={g.g} name={g.g} data={g.ps} fill={SERIES[i]} fillOpacity={0.65} isAnimationActive={false}
                onClick={(p: any) => p?.payload?.r?.cnpj && nav(`/fundo/${p.payload.r.cnpj}`)} style={{ cursor: 'pointer' }} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap', fontSize: 12 }}>
        {grupos.map((g, i) => (
          <span key={g.g} className="row" style={{ gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 999, background: SERIES[i], display: 'inline-block' }} />
            {g.g} ({g.ps.length})
          </span>
        ))}
      </div>
    </div>
  )
}
