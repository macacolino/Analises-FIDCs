import { useQuery } from '@tanstack/react-query'

export type Row = Record<string, any>

/** Sessão expirada (senha do time): volta para o login e retorna depois para a mesma tela. */
function checarSessao(r: Response) {
  if (r.status === 401) window.location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`
}

export async function get<T = any>(url: string): Promise<T> {
  const r = await fetch(url)
  checarSessao(r)
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* sem corpo */ }
    throw new Error(msg)
  }
  return r.json()
}

export async function send(method: string, url: string, body?: unknown) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  checarSessao(r)
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json()
}

export const useApi = <T = any>(url: string | null, opts: { staleTime?: number } = {}) =>
  useQuery<T>({ queryKey: [url], queryFn: () => get<T>(url!), enabled: !!url, staleTime: opts.staleTime ?? 5 * 60_000 })

export type DicItem = { label: string; fmt: string; desc: string }
export type Dic = Record<string, DicItem>

export const useDic = () => useApi<Dic>('/api/dicionario', { staleTime: Infinity })

export type Meta = { atualizado_em: string; ultimo_mes: string; mes_referencia: string; fundos_ativos: number; etl: any }
export const useMeta = () => useApi<Meta>('/api/meta', { staleTime: 60_000 })

export type Categoria = { id: string; nome: string; grupo: string }
export const useTaxonomia = () => useApi<Categoria[]>('/api/taxonomia', { staleTime: Infinity })

export function xlsxUrl(url: string) {
  return url + (url.includes('?') ? '&' : '?') + 'formato=xlsx'
}
