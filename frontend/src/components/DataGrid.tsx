import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from 'ag-grid-community'
import { AgGridReact } from 'ag-grid-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useDic, xlsxUrl, type Row } from '../api'
import { colFmt, colLabel, fmtCnpj, fmtValue } from '../fmt'

ModuleRegistry.registerModules([AllCommunityModule])

const theme = themeQuartz.withParams({
  backgroundColor: 'var(--surface)',
  foregroundColor: 'var(--ink)',
  headerBackgroundColor: 'var(--surface-2)',
  borderColor: 'var(--grid)',
  rowHoverColor: 'var(--surface-2)',
  accentColor: 'var(--accent)',
  fontSize: 13,
  headerFontSize: 12,
  spacing: 6,
  wrapperBorderRadius: 10,
})

type ColSpec = string | (ColDef & { field: string })

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
  const colDefs = useMemo<ColDef[]>(() => cols.map((c, i) => {
    const field = typeof c === 'string' ? c : c.field
    const base: ColDef = typeof c === 'string' ? { field } : { ...c }
    const f = colFmt(dic, field)
    const numeric = !!f && f !== 'txt' && f !== 'data'
    const def: ColDef = {
      headerName: colLabel(dic, field),
      headerTooltip: dic?.[field]?.desc || colLabel(dic, field),
      sortable: true,
      filter: numeric ? 'agNumberColumnFilter' : 'agTextColumnFilter',
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
      {(title || exportUrl || extra) && (
        <div className="row">
          {title && <h2 style={{ margin: 0 }}>{title}</h2>}
          <span className="muted">{rows ? `${rows.length.toLocaleString('pt-BR')} linhas` : ''}</span>
          <div className="spacer" />
          {extra}
          {exportUrl && <a className="btn" href={xlsxUrl(exportUrl)}>⬇ Excel</a>}
        </div>
      )}
      <div style={rows && rows.length <= 12 ? undefined : { height }}>
        <AgGridReact theme={theme} rowData={rows} columnDefs={colDefs}
          defaultColDef={{ flex: 0, width: 130 }} animateRows={false} domLayout={rows && rows.length <= 12 ? 'autoHeight' : 'normal'}
          tooltipShowDelay={300} autoSizeStrategy={{ type: 'fitCellContents' }} enableCellTextSelection ensureDomOrder
          overlayNoRowsTemplate="Sem dados" loading={!rows} />
      </div>
    </div>
  )
}
