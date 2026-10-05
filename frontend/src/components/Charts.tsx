import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { Row } from '../api'
import { fmtAxis, fmtValue, mesAno } from '../fmt'

// Paleta categórica (ordem fixa, validada para daltonismo nos pares adjacentes) - ver index.css
export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)', 'var(--s8)']

export type SerieSpec = { key: string; label: string; color?: string; dashed?: boolean }

const axisProps = {
  stroke: 'var(--axis)',
  tick: { fill: 'var(--muted)', fontSize: 11 },
  tickLine: false,
}

function Legend({ series }: { series: SerieSpec[] }) {
  if (series.length < 2) return null
  return (
    <div className="legend">
      {series.map((s, i) => (
        <span key={s.key}>
          <i style={{
            background: s.dashed ? 'none' : (s.color ?? SERIES[i]),
            border: s.dashed ? `2px dashed ${s.color ?? SERIES[i]}` : undefined, height: s.dashed ? 0 : 10,
          }} />
          {s.label}
        </span>
      ))}
    </div>
  )
}

function Tip({ active, payload, label, fmt, xFmt }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="t">{xFmt ? xFmt(label) : label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="row" style={{ gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color, display: 'inline-block' }} />
          <span>{p.name}</span><span className="spacer" />
          <b className="num">{fmtValue(p.value, fmt)}</b>
        </div>
      ))}
    </div>
  )
}

/** Linhas ao longo do tempo (eixo único). x = 'dt' por padrão. */
export function TimeLines({ data, series, fmt, height = 240, x = 'dt', xFmt = mesAno, title }: {
  data: Row[] | undefined; series: SerieSpec[]; fmt: string; height?: number; x?: string
  xFmt?: (v: any) => string; title?: string
}) {
  return (
    <div>
      {title && <h3>{title}</h3>}
      <Legend series={series} />
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data ?? []} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey={x} tickFormatter={xFmt} minTickGap={28} {...axisProps} />
          <YAxis tickFormatter={(v) => fmtAxis(v, fmt)} width={56} {...axisProps} axisLine={false} />
          <Tooltip content={<Tip fmt={fmt} xFmt={xFmt} />} cursor={{ stroke: 'var(--axis)' }} />
          {series.map((s, i) => (
            <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color ?? SERIES[i]} strokeWidth={2}
              strokeDasharray={s.dashed ? '5 4' : undefined} dot={false} connectNulls
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Área empilhada (composição ao longo do tempo). */
export function StackedArea({ data, series, fmt, height = 280, title }: {
  data: Row[]; series: SerieSpec[]; fmt: string; height?: number; title?: string
}) {
  return (
    <div>
      {title && <h3>{title}</h3>}
      <Legend series={series} />
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="dt" tickFormatter={mesAno} minTickGap={28} {...axisProps} />
          <YAxis tickFormatter={(v) => fmtAxis(v, fmt)} width={60} {...axisProps} axisLine={false} />
          <Tooltip content={<Tip fmt={fmt} xFmt={mesAno} />} />
          {series.map((s, i) => (
            <Area key={s.key} dataKey={s.key} name={s.label} stackId="1" stroke="var(--surface)" strokeWidth={1}
              fill={s.color ?? SERIES[i]} fillOpacity={0.9} isAnimationActive={false} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Barras verticais por categoria (ex.: faixas de atraso). */
export function Bars({ data, x, series, fmt, height = 220, title }: {
  data: Row[]; x: string; series: SerieSpec[]; fmt: string; height?: number; title?: string
}) {
  return (
    <div>
      {title && <h3>{title}</h3>}
      <Legend series={series} />
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: 0 }} barGap={2}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey={x} {...axisProps} interval={0} fontSize={10} />
          <YAxis tickFormatter={(v) => fmtAxis(v, fmt)} width={56} {...axisProps} axisLine={false} />
          <Tooltip content={<Tip fmt={fmt} />} cursor={{ fill: 'var(--surface-2)' }} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color ?? SERIES[i]} radius={[4, 4, 0, 0]}
              maxBarSize={36} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Fundo vs. faixa P25–P75 e mediana dos pares ao longo do tempo. */
export function BandChart({ data, fmt, height = 260, title, fundoLabel = 'Fundo' }: {
  data: Row[] | undefined; fmt: string; height?: number; title?: string; fundoLabel?: string
}) {
  const rows = (data ?? []).map((r) => ({ ...r, faixa: r.p25 != null && r.p75 != null ? [r.p25, r.p75] : null }))
  return (
    <div>
      {title && <h3>{title}</h3>}
      <div className="legend">
        <span><i style={{ background: 'var(--s1)' }} />{fundoLabel}</span>
        <span><i style={{ background: 'none', border: '2px dashed var(--muted)', height: 0 }} />Mediana dos pares</span>
        <span><i style={{ background: 'var(--grid)' }} />P25–P75 dos pares</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="dt" tickFormatter={mesAno} minTickGap={28} {...axisProps} />
          <YAxis tickFormatter={(v) => fmtAxis(v, fmt)} width={56} {...axisProps} axisLine={false} />
          <Tooltip content={<BandTip fmt={fmt} />} cursor={{ stroke: 'var(--axis)' }} />
          <Area dataKey="faixa" name="P25–P75" stroke="none" fill="var(--axis)" fillOpacity={0.45} isAnimationActive={false} connectNulls />
          <Line dataKey="mediana" name="Mediana dos pares" stroke="var(--muted)" strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          <Line dataKey="fundo" name={fundoLabel} stroke="var(--s1)" strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function BandTip({ active, payload, label, fmt }: any) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="t">{mesAno(label)}</div>
      <div>Fundo: <b className="num">{fmtValue(r.fundo, fmt)}</b></div>
      <div>Mediana pares: <b className="num">{fmtValue(r.mediana, fmt)}</b></div>
      <div className="muted">P25 {fmtValue(r.p25, fmt)} · P75 {fmtValue(r.p75, fmt)} · n={r.n}</div>
    </div>
  )
}

/** Dispersão (pares + fundo em destaque). */
export function Scatter2({ data, xFmt, yFmt, xLabel, yLabel, height = 340, onClick }: {
  data: Row[]; xFmt: string; yFmt: string; xLabel: string; yLabel: string; height?: number
  onClick?: (r: Row) => void
}) {
  const pares = data.filter((d) => !d.destaque && d.x != null && d.y != null)
  const fundo = data.filter((d) => d.destaque && d.x != null && d.y != null)
  // escala pelos percentis 2-98 dos pares (outliers ficam na borda) - sempre incluindo o fundo
  const dom = (k: 'x' | 'y'): [number, number] | ['auto', 'auto'] => {
    const v = pares.map((d) => d[k] as number).sort((a, b) => a - b)
    if (v.length < 10) return ['auto', 'auto']
    let lo = v[Math.floor(0.02 * (v.length - 1))], hi = v[Math.ceil(0.98 * (v.length - 1))]
    for (const f of fundo) { lo = Math.min(lo, f[k]); hi = Math.max(hi, f[k]) }
    const pad = (hi - lo) * 0.05 || Math.abs(hi) * 0.1 || 1
    return [lo - pad, hi + pad]
  }
  const clip = (d: Row) => {
    const [x0, x1] = dom('x'), [y0, y1] = dom('y')
    const c = (v: number, a: any, b: any) => (typeof a === 'number' ? Math.min(Math.max(v, a), b) : v)
    return { ...d, x: c(d.x, x0, x1), y: c(d.y, y0, y1), xr: d.x, yr: d.y }
  }
  const paresC = pares.map(clip)
  return (
    <div>
      <div className="legend">
        <span><i style={{ background: 'var(--s1)' }} />Fundo</span>
        <span><i style={{ background: 'var(--axis)' }} />Pares</span>
        <span className="muted">escala nos percentis 2–98 dos pares; valores extremos ficam na borda (valor real no tooltip)</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 6, right: 16, bottom: 24, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis type="number" dataKey="x" name={xLabel} domain={dom('x')} allowDataOverflow tickFormatter={(v) => fmtAxis(v, xFmt)} {...axisProps}
            label={{ value: xLabel, position: 'insideBottom', offset: -14, fill: 'var(--ink-2)', fontSize: 12 }} />
          <YAxis type="number" dataKey="y" name={yLabel} domain={dom('y')} allowDataOverflow tickFormatter={(v) => fmtAxis(v, yFmt)} width={60} {...axisProps}
            label={{ value: yLabel, angle: -90, position: 'insideLeft', fill: 'var(--ink-2)', fontSize: 12 }} />
          <Tooltip content={({ active, payload }: any) => {
            if (!active || !payload?.length) return null
            const r = payload[0].payload
            return (
              <div className="chart-tip">
                <div className="t">{r.nome}</div>
                <div>{xLabel}: <b>{fmtValue(r.xr ?? r.x, xFmt)}</b></div>
                <div>{yLabel}: <b>{fmtValue(r.yr ?? r.y, yFmt)}</b></div>
                <div className="muted">PL {fmtValue(r.pl, 'brl')}</div>
              </div>
            )
          }} />
          <Scatter data={paresC} fill="var(--axis)" stroke="var(--muted)" isAnimationActive={false}
            onClick={(p: any) => onClick?.(p.payload ?? p)} cursor="pointer" />
          <Scatter data={fundo} fill="var(--s1)" stroke="var(--surface)" strokeWidth={2} isAnimationActive={false}
            shape={(p: any) => <circle cx={p.cx} cy={p.cy} r={7} fill="var(--s1)" stroke="var(--surface)" strokeWidth={2} />} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Barras ordenadas de todos os pares numa métrica, com o fundo em destaque. */
export function RankBars({ data, fmt, destaque, height = 260, onClick }: {
  data: { nome: string; valor: number; cnpj: string; marca?: string }[]; fmt: string; destaque: string
  height?: number; onClick?: (cnpj: string) => void
}) {
  const sorted = [...data].sort((a, b) => a.valor - b.valor)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} margin={{ top: 6, right: 12, bottom: 0, left: 0 }} barCategoryGap={1}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="cnpj" {...axisProps} tick={false} />
        <YAxis tickFormatter={(v) => fmtAxis(v, fmt)} width={56} {...axisProps} axisLine={false} />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={({ active, payload }: any) => {
          if (!active || !payload?.length) return null
          const r = payload[0].payload
          return <div className="chart-tip"><div className="t">{r.nome}</div><b>{fmtValue(r.valor, fmt)}</b>
            {r.marca && <div className="muted">{r.marca}</div>}</div>
        }} />
        <Bar dataKey="valor" isAnimationActive={false} radius={[2, 2, 0, 0]} onClick={(p: any) => onClick?.(p.cnpj)} cursor="pointer">
          {sorted.map((d) => (
            <Cell key={d.cnpj} fill={d.cnpj === destaque ? 'var(--s1)' : d.marca ? 'var(--s2)' : 'var(--axis)'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
