import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ColumnState, type GridApi } from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useApi, useDic, xlsxUrl, type Row } from '../api'
import { colFmt, colLabel, fmtCnpj, fmtValue } from '../fmt'

ModuleRegistry.registerModules([AllCommunityModule])

const theme = themeQuartz.withParams({
  backgroundColor: 'var(--surface)',
  foregroundColor: 'var(--ink)',
  textColor: 'var(--ink)',
  headerBackgroundColor: 'var(--surface-2)',
  headerTextColor: 'var(--ink-2)',
  headerFontWeight: 600,
  borderColor: 'var(--grid)',
  rowBorder: { color: 'var(--grid)' },
  columnBorder: false,
  rowHoverColor: 'var(--accent-soft)',
  selectedRowBackgroundColor: 'var(--accent-soft)',
  accentColor: 'var(--accent)',
  fontFamily: 'var(--font)',
  fontSize: 13,
  headerFontSize: 12,
  rowHeight: 40,
  headerHeight: 42,
  spacing: 7,
  wrapperBorderRadius: 14,
  borderRadius: 8,
  inputBorder: { color: 'var(--border-strong)' },
  inputFocusBorder: { color: 'var(--accent)' },
})

/** coluna: nome do campo (rótulo/formato do dicionário) ou ColDef; `fmt` força o formato de campos fora do dicionário */
export type ColSpec = string | (ColDef & { field: string; fmt?: string })

/* ---------- filtros: expressões na unidade exibida (% como %, R$ em milhões) ---------- */
const semAcento = (t: string) => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

/** valor da célula na unidade em que o usuário pensa ao filtrar */
function unidade(v: any, fmt: string | undefined): number | null {
  if (v == null || v === '' || typeof v !== 'number' || !Number.isFinite(v)) return null
  if (fmt === 'pct') return v * 100
  if (fmt === 'brl') return v / 1e6
  return v
}

const DICA: Record<string, string> = {
  pct: 'em %: >5, <1,5, 5-10', pct100: 'em %: >5, 1-2', brl: 'R$ mi: >100, 50-200, <1bi', x: '>1, 0,5-1',
  dias: 'dias: >360', int: '>10, 5-20',
}

/** casa uma expressão (">5", "<=1,5", "5-10", "=0", "7") com um número; null se a expressão não é numérica */
export function casaNumero(expr: string, n: number | null): boolean | null {
  let t = expr.trim().toLowerCase().replace(/\s+/g, '').replace(',', '.').replace(',', '.')
  if (!t) return true
  // R$ em milhões na tela: "1bi" = 1000, "50mi" = 50
  t = t.replace(/(\d+(?:\.\d+)?)bi/g, (_, x) => String(Number(x) * 1000)).replace(/(\d+(?:\.\d+)?)mi/g, '$1')
  let m = t.match(/^(>=|<=|>|<|=|<>|!=)(-?\d+(?:\.\d+)?)%?$/)
  if (m) {
    if (n == null) return false
    const x = Number(m[2])
    switch (m[1]) {
      case '>': return n > x
      case '<': return n < x
      case '>=': return n >= x
      case '<=': return n <= x
      case '<>': case '!=': return Math.abs(n - x) > 1e-9
      default: return Math.abs(n - x) < 0.005 + Math.abs(x) * 1e-9
    }
  }
  m = t.match(/^(-?\d+(?:\.\d+)?)(?:-|a|\.\.|:)(-?\d+(?:\.\d+)?)%?$/)
  if (m) return n != null && n >= Math.min(+m[1], +m[2]) && n <= Math.max(+m[1], +m[2])
  m = t.match(/^(-?\d+(?:\.\d+)?)%?$/)
  if (m) {   // número solto: igual ao valor arredondado como aparece na tela
    if (n == null) return false
    const casas = (m[1].split('.')[1] ?? '').length
    return Math.abs(n - Number(m[1])) < 0.5 * 10 ** -casas + 1e-9
  }
  if (t === 'vazio' || t === '–') return n == null
  return null
}

function casaTexto(expr: string, v: any): boolean {
  const e = semAcento(expr.trim())
  if (!e) return true
  const txt = semAcento(v == null ? '' : String(v))
  if (e.startsWith('-') && e.length > 1) return !txt.includes(e.slice(1))    // -termo exclui
  return e.split('|').some((p) => txt.includes(p.trim()))                    // a|b = a ou b
}

/* ---------- colunas escolhidas pelo usuário (por tabela, guardadas no navegador) ---------- */
type Prefs = { ocultas: string[]; extras: string[]; estado?: ColumnState[] }
const PREFS0: Prefs = { ocultas: [], extras: [] }
function lerPrefs(chave: string): Prefs {
  try { const v = localStorage.getItem(chave); return v ? { ...PREFS0, ...JSON.parse(v) } : PREFS0 } catch { return PREFS0 }
}
function gravarPrefs(chave: string, p: Prefs) {
  try { localStorage.setItem(chave, JSON.stringify(p)) } catch { /* modo privado: só nesta sessão */ }
}
// campos internos que não fazem sentido como coluna
const NAO_COLUNA = new Set(['id', 'categoria', 'grupo', 'alertas', 'detalhe', 'trecho'])
// tabela de fundos: todos os campos da Pesquisa, para acrescentar em qualquer tabela que tenha um fundo por linha
const CATALOGO = '/api/fundos?limit=20000&ativos=false'

/** visão pronta: conjunto de colunas com nome (ex.: "Crédito", "Rentabilidade") */
export type Visao = { nome: string; cols: string[] }

function PainelColunas({ todas, base, mostradas, dic, onToggle, onRestaurar, onFechar, catalogoCarregando }: {
  todas: string[]; base: Set<string>; mostradas: Set<string>; dic: any
  onToggle: (f: string, on: boolean) => void; onRestaurar: () => void; onFechar: () => void
  catalogoCarregando: boolean
}) {
  const [q, setQ] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const fora = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onFechar() }
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [onFechar])
  const t = semAcento(q)
  const casa = (f: string) => { const alvo = semAcento(colLabel(dic, f) + ' ' + f); return t.split(/\s+/).every((p) => alvo.includes(p)) }
  const naTabela = todas.filter((f) => mostradas.has(f) && casa(f))
  const fora = todas.filter((f) => !mostradas.has(f) && casa(f))
    .sort((a, b) => colLabel(dic, a).localeCompare(colLabel(dic, b), 'pt-BR'))
  const item = (f: string, on: boolean) => (
    <label key={f} className="col-item" title={dic?.[f]?.desc || f}>
      <input type="checkbox" checked={on} onChange={(e) => onToggle(f, e.target.checked)} />
      <span>{colLabel(dic, f)}</span>
      {!base.has(f) && on && <span className="muted" style={{ fontSize: 11 }}>adicionada</span>}
    </label>
  )
  return (
    <div className="painel-colunas" ref={ref}>
      <div className="row" style={{ gap: 6 }}>
        <input type="search" autoFocus placeholder="Procurar coluna…" value={q} onChange={(e) => setQ(e.target.value)}
          style={{ flex: 1 }} />
        <button className="ghost" onClick={onRestaurar} title="Volta às colunas originais desta tabela">Restaurar</button>
      </div>
      <div className="col-sec">Na tabela ({naTabela.length}) <span className="muted">· arraste o cabeçalho para reordenar</span></div>
      {naTabela.map((f) => item(f, true))}
      <div className="col-sec">Adicionar ({fora.length}){catalogoCarregando ? ' · carregando campos do fundo…' : ''}</div>
      {fora.map((f) => item(f, false))}
    </div>
  )
}

export function DataGrid({ rows, cols, exportUrl, height = 520, title, extra, pinned = 1, id, visoes }: {
  rows: Row[] | undefined
  cols: ColSpec[]
  exportUrl?: string
  height?: number | string
  title?: string
  extra?: React.ReactNode
  pinned?: number
  /** identifica a tabela para guardar as colunas escolhidas (padrão: página + título) */
  id?: string
  /** conjuntos de colunas prontos, mostrados como botões */
  visoes?: Visao[]
}) {
  const { data: dic } = useDic()
  const { pathname } = useLocation()
  const camposBase = useMemo(() => cols.map((c) => (typeof c === 'string' ? c : c.field)), [cols])
  const chave = `fidc.grid:${pathname.replace(/\/\d{8,}/g, '/:cnpj').replace(/^\/setores\/[^/]+/, '/setores/:categoria')}:${id ?? title ?? camposBase.slice(0, 3).join(',')}`
  const [prefs, setPrefsRaw] = useState<Prefs>(() => lerPrefs(chave))
  useEffect(() => { setPrefsRaw(lerPrefs(chave)) }, [chave])
  const setPrefs = useCallback((f: (p: Prefs) => Prefs) => setPrefsRaw((p) => { const n = f(p); gravarPrefs(chave, n); return n }), [chave])
  const [painel, setPainel] = useState(false)

  // um fundo por linha? então dá para acrescentar qualquer campo da Pesquisa (catálogo por CNPJ)
  const porFundo = useMemo(() => !!rows?.length && rows[0].cnpj != null &&
    new Set(rows.map((r) => r.cnpj)).size === rows.length, [rows])
  const precisaCatalogo = porFundo && (painel || prefs.extras.some((f) => !(rows?.[0] && f in rows[0])))
  const cat = useApi<Row[]>(precisaCatalogo ? CATALOGO : null, { staleTime: 30 * 60_000 })
  const catMap = useMemo(() => new Map((cat.data ?? []).map((r) => [r.cnpj, r])), [cat.data])
  const linhas = useMemo(() => {
    if (!rows || !porFundo || !catMap.size || !prefs.extras.length) return rows
    const faltam = prefs.extras.filter((f) => !(rows[0] && f in rows[0]))
    if (!faltam.length) return rows
    return rows.map((r) => {
      const c = catMap.get(r.cnpj); if (!c) return r
      const n = { ...r }; for (const f of faltam) n[f] = c[f]; return n
    })
  }, [rows, porFundo, catMap, prefs.extras])

  const disponiveis = useMemo(() => {
    const s = new Set<string>(camposBase)
    for (const r of (rows ?? []).slice(0, 50)) for (const k of Object.keys(r)) s.add(k)
    if (porFundo && cat.data?.[0]) for (const k of Object.keys(cat.data[0])) s.add(k)
    for (const f of prefs.extras) s.add(f)
    return [...s].filter((f) => !NAO_COLUNA.has(f) || camposBase.includes(f))
  }, [camposBase, rows, porFundo, cat.data, prefs.extras])
  const base = useMemo(() => new Set(camposBase), [camposBase])
  const mostradas = useMemo(() => {
    const oc = new Set(prefs.ocultas)
    return new Set([...camposBase.filter((f) => !oc.has(f)), ...prefs.extras])
  }, [camposBase, prefs])
  const alterarColuna = (f: string, on: boolean) => setPrefs((p) => {
    if (base.has(f)) return { ...p, ocultas: on ? p.ocultas.filter((x) => x !== f) : [...p.ocultas, f] }
    return { ...p, extras: on ? [...p.extras, f] : p.extras.filter((x) => x !== f) }
  })
  const aplicarVisao = (v: Visao) => {
    setPrefs((p) => ({
      ...p,
      ocultas: camposBase.filter((f) => !v.cols.includes(f) && f !== camposBase[0]),
      extras: v.cols.filter((f) => !base.has(f)),
    }))
    // depois que as colunas novas existirem: põe na ordem da visão
    setTimeout(() => {
      api.current?.applyColumnState({ state: [camposBase[0], ...v.cols].map((colId) => ({ colId })), applyOrder: true })
      salvarRef.current?.()
    }, 50)
  }
  const salvarRef = useRef<(() => void) | null>(null)
  const api = useRef<GridApi | null>(null)
  const [busca, setBusca] = useState('')
  const [visiveis, setVisiveis] = useState<number | null>(null)
  const [temFiltro, setTemFiltro] = useState(false)
  const atualizar = useCallback(() => {
    if (!api.current) return
    setVisiveis(api.current.getDisplayedRowCount())
    setTemFiltro(api.current.isAnyFilterPresent())
  }, [])
  const specs = useMemo<ColSpec[]>(() => [...cols, ...prefs.extras.filter((f) => !base.has(f))], [cols, prefs.extras, base])
  const colDefs = useMemo<ColDef[]>(() => specs.map((c, i) => {
    const field = typeof c === 'string' ? c : c.field
    const { fmt: fmtForcado, ...resto } = typeof c === 'string' ? { fmt: undefined } : c
    const baseDef: ColDef = typeof c === 'string' ? { field } : resto
    const f = fmtForcado ?? colFmt(dic, field)
    const numeric = !!f && f !== 'txt' && f !== 'data'
    const def: ColDef = {
      headerName: colLabel(dic, field),
      headerTooltip: dic?.[field]?.desc || colLabel(dic, field),
      sortable: true,
      filter: 'agTextColumnFilter',
      floatingFilter: true, suppressFloatingFilterButton: true,
      filterValueGetter: (p) => {
        const v = p.data?.[field]
        return numeric ? unidade(v, f) : (v == null ? '' : field === 'cnpj' ? `${v} ${fmtCnpj(v)}` : String(v))
      },
      filterParams: {
        filterOptions: ['contains'], maxNumConditions: 1, debounceMs: 250, trimInput: true,
        filterPlaceholder: numeric ? (DICA[f!] ?? '>10, 5-20') : 'contém… (a|b, -excluir)',
        textFormatter: (t: any) => t,
        textMatcher: ({ value, filterText }: any) => {
          if (numeric) {
            const n = value === '' || value == null ? null : Number(value)
            const r = casaNumero(filterText ?? '', n)
            return r ?? casaTexto(filterText ?? '', value)
          }
          return casaTexto(filterText ?? '', value)
        },
      },
      resizable: true, wrapHeaderText: true, autoHeaderHeight: true,
      minWidth: 80, maxWidth: 420, suppressHeaderMenuButton: true,
      pinned: i < pinned ? 'left' : undefined,
      type: numeric ? 'rightAligned' : undefined,
      valueFormatter: (p) => fmtValue(p.value, f),
      ...baseDef,
      colId: field,
      hide: !mostradas.has(field),
    }
    if (field === 'nome' && !baseDef.cellRenderer) {
      def.minWidth = 280
      def.cellRenderer = (p: any) => p.data?.cnpj
        ? <Link to={`/fundo/${p.data.cnpj}`} title={p.value}>{p.value}</Link> : p.value
    }
    if (field === 'cnpj' && !baseDef.valueFormatter) def.valueFormatter = (p) => fmtCnpj(p.value)
    return def
  }), [specs, dic, pinned, mostradas])

  // ordem/largura arrastadas pelo usuário
  const salvarEstado = useCallback(() => {
    if (!api.current) return
    const estado = api.current.getColumnState().map(({ colId, width }) => ({ colId, width }))
    setPrefs((p) => ({ ...p, estado }))
  }, [setPrefs])
  salvarRef.current = salvarEstado
  const exportarCsv = () => api.current?.exportDataAsCsv({
    columnSeparator: ';', fileName: `${(title ?? 'tabela').replace(/[^\w-]+/g, '_')}.csv`,
    processCellCallback: (p) => {
      const v = p.value
      return typeof v === 'number' ? String(v).replace('.', ',') : v == null ? '' : String(v)
    },
  })
  const personalizada = prefs.ocultas.length > 0 || prefs.extras.length > 0

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        {title && <h2 style={{ margin: 0 }}>{title}</h2>}
        <input type="search" placeholder="Buscar em todas as colunas…" value={busca} style={{ width: 240 }}
          onChange={(e) => setBusca(e.target.value)} />
        {(temFiltro || busca) && <button style={{ padding: '0 8px' }} onClick={() => {
          setBusca(''); api.current?.setFilterModel(null) }}>Limpar filtros</button>}
        <span className="muted">{rows ? (visiveis != null && (temFiltro || busca) && visiveis !== rows.length
          ? `${visiveis.toLocaleString('pt-BR')} de ${rows.length.toLocaleString('pt-BR')} linhas`
          : `${rows.length.toLocaleString('pt-BR')} linhas`) : ''}</span>
        <span className="muted" style={{ fontSize: 12 }} title={'Filtro sob cada coluna, na unidade exibida:\n' +
          '• números: >5   <=1,5   5-10   =0   (percentuais em %, valores em R$ milhões)\n' +
          '• texto: parte do nome; a|b = a ou b; -termo = exclui'}>ⓘ filtros: &gt;5, 5-10, texto, a|b, -excluir</span>
        <div className="spacer" />
        {extra}
        {visoes && visoes.length > 0 && (
          <div className="row visoes" style={{ gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Visões:</span>
            {visoes.map((v) => <button key={v.nome} className="visao" onClick={() => aplicarVisao(v)}>{v.nome}</button>)}
          </div>
        )}
        <div style={{ position: 'relative' }}>
          <button onClick={() => setPainel((x) => !x)} title="Esconder, adicionar e reordenar colunas (fica salvo neste navegador)">
            ☰ Colunas{personalizada ? ' •' : ''}
          </button>
          {painel && <PainelColunas todas={disponiveis} base={base} mostradas={mostradas} dic={dic}
            onToggle={alterarColuna} onFechar={() => setPainel(false)} catalogoCarregando={porFundo && cat.isLoading}
            onRestaurar={() => { setPrefs(() => PREFS0); api.current?.resetColumnState() }} />}
        </div>
        <button onClick={exportarCsv} title="CSV só com as colunas e linhas que estão na tela (abre no Excel)">⬇ CSV da tela</button>
        {exportUrl && <a className="btn" href={xlsxUrl(exportUrl)} title="Excel com todas as colunas da consulta">⬇ Excel</a>}
      </div>
      <div style={rows && rows.length <= 12 ? undefined : { height }}>
        <AgGridReact theme={theme} rowData={linhas} columnDefs={colDefs} maintainColumnOrder
          defaultColDef={{ flex: 0, width: 130 }} animateRows={false} domLayout={rows && rows.length <= 12 ? 'autoHeight' : 'normal'}
          tooltipShowDelay={300} autoSizeStrategy={{ type: 'fitCellContents' }} enableCellTextSelection ensureDomOrder
          overlayNoRowsTemplate="Sem dados" loading={!rows}
          quickFilterText={busca} cacheQuickFilter
          quickFilterParser={(q) => semAcento(q).split(/\s+/).filter(Boolean)}
          quickFilterMatcher={(partes, texto) => { const t = semAcento(texto); return partes.every((p) => t.includes(p)) }}
          onGridReady={(e) => {
            api.current = e.api
            if (prefs.estado?.length) e.api.applyColumnState({ state: prefs.estado, applyOrder: true })
            atualizar()
          }}
          onColumnMoved={(e) => { if (e.finished) salvarEstado() }}
          onColumnResized={(e) => { if (e.finished && e.source === 'uiColumnResized') salvarEstado() }}
          onFilterChanged={atualizar} onRowDataUpdated={atualizar} />
      </div>
    </div>
  )
}
