import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi, useTaxonomia, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'

// faixas numéricas: campo, rótulo, escala da tela (pct = fração x100; brl = R$ em milhões)
const FAIXAS: [string, string, 'pct' | 'brl' | 'num'][] = [
  ['pl', 'PL (R$ mi)', 'brl'], ['pl_medio_12m', 'PL médio 12m (R$ mi)', 'brl'],
  ['subordinacao', 'Subordinação atual (%)', 'pct'], ['sub_min_senior', 'Subordinação mínima (%)', 'pct'],
  ['taxa_gestao', 'Taxa de gestão (% a.a.)', 'pct'], ['taxa_administracao', 'Taxa de adm. (% a.a.)', 'pct'],
  ['taxa_desconto_aa', 'Taxa nas aquisições (% a.a.)', 'num'], ['inad_90', 'Inad. >90d (%)', 'pct'],
  ['cotistas_senior', 'Cotistas sênior', 'num'], ['cotistas_mezanino', 'Cotistas mezanino', 'num'],
  ['cotistas_subordinada', 'Cotistas subordinada', 'num'],
  ['spread_senior_aa', 'Remuneração sênior (CDI + % a.a.)', 'pct'],
]
const EXTREMOS = { min: '20', max: '5000' }   // R$ 20 mi a R$ 5 bi

function naTela(v: any, esc: string): number | null {
  if (v == null || v === '' || !Number.isFinite(Number(v))) return null
  return esc === 'pct' ? Number(v) * 100 : esc === 'brl' ? Number(v) / 1e6 : Number(v)
}
const num = (x: string) => (x.trim() === '' ? null : Number(x.replace(',', '.')))

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

  const [faixa, setFaixa] = useState<Record<string, { min: string; max: string }>>({})
  const [estrutura, setEstrutura] = useState('')
  const [abrir, setAbrir] = useState(false)
  const extremos = faixa.pl?.min === EXTREMOS.min && faixa.pl?.max === EXTREMOS.max
  const setF = (k: string, lado: 'min' | 'max', v: string) =>
    setFaixa((f) => ({ ...f, [k]: { min: f[k]?.min ?? '', max: f[k]?.max ?? '', [lado]: v } }))
  const ativosF = Object.entries(faixa).filter(([, v]) => v.min.trim() || v.max.trim()).length + (estrutura ? 1 : 0)

  const url = `/api/fundos?limit=10000&q=${encodeURIComponent(debounced)}` +
    (categoria ? `&categoria=${categoria}` : '') + (ativos ? '' : '&ativos=false')
  const res = useApi<Row[]>(url)
  const linhas = useMemo(() => (res.data ?? []).filter((r) => {
    if (estrutura && r.estrutura !== estrutura) return false
    for (const [k, rot, esc] of FAIXAS) {
      void rot
      const f = faixa[k]
      if (!f) continue
      const lo = num(f.min), hi = num(f.max)
      if (lo == null && hi == null) continue
      const v = naTela(r[k], esc)
      if (v == null) return false
      if (lo != null && v < lo) return false
      if (hi != null && v > hi) return false
    }
    return true
  }), [res.data, faixa, estrutura])

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
          <label className="row" style={{ gap: 6 }} title="PL entre R$ 20 mi e R$ 5 bi (ajustável no filtro de PL)">
            <input type="checkbox" checked={extremos} onChange={(e) =>
              setFaixa((f) => ({ ...f, pl: e.target.checked ? { ...EXTREMOS } : { min: '', max: '' } }))} />
            excluir muito pequenos e muito grandes
          </label>
          <select value={estrutura} onChange={(e) => setEstrutura(e.target.value)}>
            <option value="">Qualquer estrutura</option>
            <option value="classes">Com classes (sênior/mez/sub)</option>
            <option value="classe única">Classe única</option>
          </select>
          <div className="spacer" />
          <button onClick={() => setAbrir((x) => !x)}>{abrir ? 'Esconder filtros' : 'Mais filtros'}{ativosF ? ` (${ativosF})` : ''}</button>
          {ativosF > 0 && <button className="ghost" onClick={() => { setFaixa({}); setEstrutura('') }}>Limpar</button>}
        </div>
        {abrir && (
          <div className="filtros-grid">
            {FAIXAS.map(([k, rot]) => (
              <div key={k} className="filtro-faixa">
                <span>{rot}</span>
                <div className="row" style={{ gap: 6 }}>
                  <input type="text" inputMode="decimal" placeholder="mín" value={faixa[k]?.min ?? ''}
                    onChange={(e) => setF(k, 'min', e.target.value)} />
                  <span className="muted">a</span>
                  <input type="text" inputMode="decimal" placeholder="máx" value={faixa[k]?.max ?? ''}
                    onChange={(e) => setF(k, 'max', e.target.value)} />
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="muted" style={{ fontSize: 12 }}>
          {res.data ? `${linhas.length.toLocaleString('pt-BR')} de ${res.data.length.toLocaleString('pt-BR')} fundos` : ''}
          {' · '}Nas colunas da tabela também dá para filtrar por valor: &gt;20, &lt;1,5, 5-10 (em % ou R$ mi; &lt;1bi).
          Subordinação vazia = fundo de classe única (não há subordinação a medir).
        </div>
      </div>
      <div className="card">
        <DataGrid rows={linhas} exportUrl={url} height={620}
          cols={['nome', 'cnpj', 'categoria_nome', 'gestor', 'admin', 'consultoria', 'pl', 'pl_medio_12m', 'estrutura',
                 'subordinacao', 'sub_min_senior', 'inad_90', 'pdd_carteira', 'taxa_administracao', 'taxa_gestao',
                 'taxa_desconto_aa', 'spread_senior_aa', 'spread_mezanino_aa', 'cotistas_senior', 'cotistas_mezanino',
                 'cotistas_subordinada', 'nr_cotistas', 'ultimo_informe',
                 { field: 'revisar', valueFormatter: (p: any) => (p.value ? 'revisar' : ''), width: 90 },
                 { field: 'ia_diverge_informe', headerName: 'Regulamento x carteira', width: 130,
                   headerTooltip: 'A tese lida no regulamento não bate com a carteira declarada no informe CVM (Tab. II)',
                   valueFormatter: (p: any) => (p.value ? 'diverge' : '') }]} />
      </div>
    </div>
  )
}
