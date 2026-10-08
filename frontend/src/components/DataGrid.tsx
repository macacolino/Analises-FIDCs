import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type GridApi } from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDic, xlsxUrl, type Row } from '../api'
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
  pct: 'em %: >5, <1,5, 5-10', pct100: 'em %: >5, 1-2', brl: 'R$ mi: >100, 50-200', x: '>1, 0,5-1',
  dias: 'dias: >360', int: '>10, 5-20',
}

/** casa uma expressão (">5", "<=1,5", "5-10", "=0", "7") com um número; null se a expressão não é numérica */
export function casaNumero(expr: string, n: number | null): boolean | null {
  const t = expr.trim().replace(/\s+/g, '').replace(',', '.').replace(',', '.')
  if (!t) return true
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

export function DataGrid({ rows, cols, exportUrl, height = 520, title, extra, pinned = 1 }: {
  rows: Row[] | undefined
  cols: ColSpec[]
  exportUrl?: string
  height?: number | string
  title?: string
  extra?: React.ReactNode
  pinned?: number
}) {
  const { data: dic } = useDic()
  const api = useRef<GridApi | null>(null)
  const [busca, setBusca] = useState('')
  const [visiveis, setVisiveis] = useState<number | null>(null)
  const [temFiltro, setTemFiltro] = useState(false)
  const atualizar = useCallback(() => {
    if (!api.current) return
    setVisiveis(api.current.getDisplayedRowCount())
    setTemFiltro(api.current.isAnyFilterPresent())
  }, [])
  const colDefs = useMemo<ColDef[]>(() => cols.map((c, i) => {
    const field = typeof c === 'string' ? c : c.field
    const { fmt: fmtForcado, ...resto } = typeof c === 'string' ? { fmt: undefined } : c
    const base: ColDef = typeof c === 'string' ? { field } : resto
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
      resizable: true,
      minWidth: 80, maxWidth: 420, suppressHeaderMenuButton: true,
      pinned: i < pinned ? 'left' : undefined,
      type: numeric ? 'rightAligned' : undefined,
      valueFormatter: (p) => fmtValue(p.value, f),
      ...base,
    }
    if (field === 'nome' && !base.cellRenderer) {
      def.minWidth = 280
      def.cellRenderer = (p: any) => p.data?.cnpj
        ? <Link to={`/fundo/${p.data.cnpj}`} title={p.value}>{p.value}</Link> : p.value
    }
    if (field === 'cnpj' && !base.valueFormatter) def.valueFormatter = (p) => fmtCnpj(p.value)
    return def
  }), [cols, dic, pinned])

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
        {exportUrl && <a className="btn" href={xlsxUrl(exportUrl)}>⬇ Excel</a>}
      </div>
      <div style={rows && rows.length <= 12 ? undefined : { height }}>
        <AgGridReact theme={theme} rowData={rows} columnDefs={colDefs}
          defaultColDef={{ flex: 0, width: 130 }} animateRows={false} domLayout={rows && rows.length <= 12 ? 'autoHeight' : 'normal'}
          tooltipShowDelay={300} autoSizeStrategy={{ type: 'fitCellContents' }} enableCellTextSelection ensureDomOrder
          overlayNoRowsTemplate="Sem dados" loading={!rows}
          quickFilterText={busca} cacheQuickFilter
          quickFilterParser={(q) => semAcento(q).split(/\s+/).filter(Boolean)}
          quickFilterMatcher={(partes, texto) => { const t = semAcento(texto); return partes.every((p) => t.includes(p)) }}
          onGridReady={(e) => { api.current = e.api; atualizar() }}
          onFilterChanged={atualizar} onRowDataUpdated={atualizar} />
      </div>
    </div>
  )
}
