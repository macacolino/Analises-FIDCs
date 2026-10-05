import { useDic } from '../api'
import { colLabel, fmtValue } from '../fmt'

export function Kpi({ k, v, compare, label }: { k: string; v: any; compare?: React.ReactNode; label?: string }) {
  const { data: dic } = useDic()
  return (
    <div className="kpi" title={dic?.[k]?.desc}>
      <div className="l">{label ?? colLabel(dic, k)}</div>
      <div className="v">{fmtValue(v, dic?.[k]?.fmt)}</div>
      {compare && <div className="c">{compare}</div>}
    </div>
  )
}

export type Alerta = { id: string; descricao: string; severidade: 'alta' | 'media' | 'info'; detalhe?: string }

const SEV_LABEL = { alta: 'Alta', media: 'Média', info: 'Info' }

export function Alertas({ items }: { items: Alerta[] }) {
  if (!items.length) return <div className="muted">Nenhum alerta pelas regras atuais.</div>
  return (
    <div className="stack" style={{ gap: 6 }}>
      {items.map((a) => (
        <div key={a.id} className={`alert sev-${a.severidade}`}>
          <span className="dot" aria-hidden />
          <span><b>{SEV_LABEL[a.severidade]}:</b> {a.descricao}{a.detalhe && <span className="muted"> — {a.detalhe}</span>}</span>
        </div>
      ))}
    </div>
  )
}

export function Loading({ q }: { q: { isLoading: boolean; error: unknown } }) {
  if (q.error) return <div className="err">Erro: {String((q.error as Error).message)}</div>
  if (q.isLoading) return <div className="loading">Carregando…</div>
  return null
}

export function Tabs<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: [T, string][]
}) {
  return (
    <div className="tabs" role="tablist">
      {options.map(([k, l]) => (
        <button key={k} role="tab" aria-selected={value === k} className={value === k ? 'on' : ''}
          onClick={() => onChange(k)}>{l}</button>
      ))}
    </div>
  )
}
