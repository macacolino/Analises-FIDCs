import type { Dic } from './api'

const nf = (d: number) => new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d })

export function brl(v: number | null | undefined, compact = true): string {
  if (v == null || Number.isNaN(v)) return '–'
  if (!compact) return 'R$ ' + nf(0).format(v)
  const a = Math.abs(v)
  if (a >= 1e9) return 'R$ ' + nf(2).format(v / 1e9) + ' bi'
  if (a >= 1e6) return 'R$ ' + nf(1).format(v / 1e6) + ' mi'
  if (a >= 1e3) return 'R$ ' + nf(0).format(v / 1e3) + ' mil'
  return 'R$ ' + nf(0).format(v)
}

export function fmtValue(v: any, fmt: string | undefined): string {
  if (v == null || v === '' || (typeof v === 'number' && !Number.isFinite(v))) return '–'
  switch (fmt) {
    case 'brl': return brl(v)
    case 'pct': return nf(2).format(v * 100) + '%'
    case 'pct100': return nf(2).format(v) + '%'
    case 'x': return nf(2).format(v) + 'x'
    case 'dias': return nf(0).format(v) + ' d'
    case 'int': return nf(0).format(v)
    case 'data': return fmtDate(v)
    default:
      return typeof v === 'number' ? nf(2).format(v) : String(v)
  }
}

export function fmtDate(v: string | null | undefined) {
  if (!v) return '–'
  const [y, m, d] = v.slice(0, 10).split('-')
  return d ? `${d}/${m}/${y}` : v
}

export const mesAno = (v: string | null | undefined) => (v ? `${v.slice(5, 7)}/${v.slice(0, 4)}` : '–')

export const fmtCnpj = (c: string) =>
  c && c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : c

/** fmt de uma coluna, aceitando sufixos derivados (_mediana, setor_, d3m_) */
export function colFmt(dic: Dic | undefined, col: string): string | undefined {
  if (!dic) return undefined
  if (dic[col]) return dic[col].fmt
  if (col.endsWith('_mediana')) return colFmt(dic, col.slice(0, -8))
  if (col.startsWith('setor_')) return colFmt(dic, col.slice(6))
  if (col.startsWith('d3m_')) {
    const f = colFmt(dic, col.slice(4))
    return col === 'd3m_pl' ? 'pct' : f
  }
  return undefined
}

export function colLabel(dic: Dic | undefined, col: string): string {
  if (!dic) return col
  if (dic[col]) return dic[col].label
  if (col.endsWith('_mediana')) return colLabel(dic, col.slice(0, -8)) + ' (mediana)'
  if (col.startsWith('setor_')) return colLabel(dic, col.slice(6)) + ' – setor'
  if (col.startsWith('d3m_')) return 'Δ3m ' + colLabel(dic, col.slice(4))
  const extra: Record<string, string> = {
    serie: 'Série', tipo: 'Tipo', pl_serie: 'PL da série', rentab_mes: 'Rentab. mês', qt_cotas: 'Qtd. cotas',
    valor_cota: 'Valor da cota', desempenho_real: 'Desempenho real', desempenho_esperado: 'Desempenho esperado',
    categoria: 'Categoria (id)', ultimo_informe: 'Último informe', revisar: 'Revisar', alertas: 'Alertas',
    alertas_desc: 'Detalhe dos alertas', tese: 'Tese', rank: '#', cedente_doc: 'CPF/CNPJ cedente', pct: '%',
    categoria_nome: 'Categoria',
  }
  return extra[col] ?? col
}

/** Rótulo curto para eixos de gráfico (casas decimais só quando necessárias) */
export function fmtAxis(v: number, fmt: string): string {
  if (v == null || !Number.isFinite(v)) return ''
  const short = (x: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: Math.abs(x) < 10 ? 2 : 1 }).format(x)
  if (fmt === 'brl') {
    const a = Math.abs(v)
    if (a >= 1e9) return short(v / 1e9) + ' bi'
    if (a >= 1e6) return short(v / 1e6) + ' mi'
    return short(v)
  }
  if (fmt === 'pct') return short(v * 100) + '%'
  if (fmt === 'pct100') return short(v) + '%'
  return fmtValue(v, fmt)
}
