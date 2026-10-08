import { useEffect, useState } from 'react'
import { useApi, type Row } from '../api'
import { brl } from '../fmt'

/** Caixa de busca de fundo (nome ou CNPJ) com lista de resultados. */
export default function FundPicker({ onPick, placeholder = 'Buscar fundo por nome ou CNPJ…' }: {
  onPick: (r: Row) => void; placeholder?: string
}) {
  const [q, setQ] = useState('')
  const [deb, setDeb] = useState('')
  useEffect(() => { const t = setTimeout(() => setDeb(q), 300); return () => clearTimeout(t) }, [q])
  const res = useApi<Row[]>(deb.length >= 3 ? `/api/fundos?limit=8&q=${encodeURIComponent(deb)}` : null)
  return (
    <div style={{ position: 'relative', minWidth: 280, flex: 1 }}>
      <input type="search" style={{ width: '100%' }} placeholder={placeholder} value={q} onChange={(e) => setQ(e.target.value)} />
      {res.data && q.length >= 3 && (
        <div className="popover">
          {res.data.map((r) => (
            <div key={r.cnpj} className="pick" onClick={() => { onPick(r); setQ(''); setDeb('') }}
              style={{ padding: '8px 10px', cursor: 'pointer', borderRadius: 8 }}>
              <div style={{ fontWeight: 500 }}>{r.nome}</div>
              <div className="muted">{r.categoria_nome} · {brl(r.pl)}</div>
            </div>
          ))}
          {!res.data.length && <div className="muted" style={{ padding: 8 }}>Nada encontrado.</div>}
        </div>
      )}
    </div>
  )
}
