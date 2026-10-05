import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
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
