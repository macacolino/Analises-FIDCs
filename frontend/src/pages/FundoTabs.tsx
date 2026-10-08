import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { send, useApi, useDic, type Row } from '../api'
import { Bars, TimeLines } from '../components/Charts'
import { DataGrid } from '../components/DataGrid'
import { Loading } from '../components/ui'
import { colLabel, fmtDate, fmtValue, mesAno } from '../fmt'

/* ---------- selo de qualidade do dado ---------- */
export function QualidadeBadge({ status, checks }: { status?: string; checks?: string }) {
  if (!status) return null
  const color = status === 'erro' ? 'var(--critical)' : status === 'alerta' ? 'var(--warning)' : 'var(--good)'
  const label = status === 'erro' ? 'dado com erro de consistência' : status === 'alerta' ? 'dado com alertas' : 'dado consistente'
  return <span className="qbadge" title={checks ? `Checagens: ${checks}` : undefined}>
    <span className="dot" style={{ background: color }} />{label}{checks ? ` (${checks})` : ''}</span>
}

/* ---------- o que mudou no mês ---------- */
export function Mudancas({ cnpj }: { cnpj: string }) {
  const d = useApi<Row[]>(`/api/fundos/${cnpj}/mudancas`)
  if (!d.data) return <Loading q={d} />
  if (!d.data.length) return <div className="muted">Sem variação relevante contra o mês anterior.</div>
  return (
    <table className="simple">
      <tbody>{d.data.map((m) => (
        <tr key={m.metrica}>
          <td style={{ width: 24, color: m.direcao === 'piora' ? 'var(--critical)' : m.direcao === 'melhora' ? 'var(--good-ink)' : 'var(--muted)' }}>
            {m.direcao === 'piora' ? '▼' : m.direcao === 'melhora' ? '▲' : '●'}</td>
          <td>{m.label}</td>
          {m.fmt !== 'txt' ? <>
            <td className="r">{fmtValue(m.anterior, m.fmt)} → <b>{fmtValue(m.atual, m.fmt)}</b></td>
            <td className="r muted">{m.delta_fmt === 'pct' && m.fmt !== 'brl' ? `${(m.delta * 100).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} p.p.` : fmtValue(m.delta, m.delta_fmt)}</td>
            <td className="muted">{m.direcao}</td></> : <td colSpan={3} className="muted">{m.detalhe}</td>}
        </tr>))}</tbody>
    </table>
  )
}

/* ---------- métricas da casa ao longo do tempo ---------- */
export function Casa({ cnpj }: { cnpj: string }) {
  const d = useApi<Row[]>(`/api/fundos/${cnpj}/casa?meses=36`)
  const ult = d.data?.[d.data.length - 1]
  return (
    <div className="stack">
      <Loading q={d} />
      {ult && (
        <div className="kpis">
          {['m01_jr_pdd', 'm02_jr_vencidos360', 'm29_colchao_carteira', 'm16_custo_credito', 'm16b_custo_credito_simples',
            'm19_excesso_spread', 'm21_retorno_jr_12m', 'retorno_jr_pct_cdi', 'm05_recompra_carteira', 'm06_preco_recompra',
            'm12_sem_aquisicao', 'm14_outros_ativos_pl', 'm15_fora_core_pl', 'm22_taxa_ix_aa', 'pdd_over90', 'pdd_sobre_2682',
            'cobertura_liquidez_30d', 'resgate_liq_sr_12m'].map((k) => <KpiSmall key={k} k={k} v={ult[k]} />)}
        </div>
      )}
      {d.data && (
        <div className="grid2">
          <TimeLines title="Colchão: Jr ÷ PDD média e Jr ÷ vencidos até 360 d (x)" data={d.data} fmt="x"
            series={[{ key: 'm01_jr_pdd', label: 'Jr ÷ PDD média 12m' }, { key: 'm02_jr_vencidos360', label: 'Jr ÷ vencidos 1-360d' }]} />
          <TimeLines title="Custo de crédito 12m × excesso de spread observado" data={d.data} fmt="pct"
            series={[{ key: 'm16_custo_credito', label: 'Custo de crédito (baixas mensais)' }, { key: 'm16b_custo_credito_simples', label: 'Custo (variante simples)' },
                     { key: 'm19_excesso_spread', label: 'Excesso de spread' }]} />
          <TimeLines title="Retorno da Jr 12m e CDI" data={d.data} fmt="pct"
            series={[{ key: 'm21_retorno_jr_12m', label: 'Retorno Jr 12m' }, { key: 'retorno_jr_menos_cdi', label: 'Retorno Jr − CDI' }]} />
          <TimeLines title="Recompra média ÷ carteira e preço da recompra" data={d.data} fmt="pct"
            series={[{ key: 'm05_recompra_carteira', label: 'Recompra ÷ carteira' }, { key: 'm06_preco_recompra', label: 'Preço ÷ contábil' }]} />
          <TimeLines title="Cenário extremo: Jr antes e depois (todo o vencido + a vencer de inadimplentes vira perda)" data={d.data} fmt="brl"
            series={[{ key: 'jr', label: 'Jr' }, { key: 'jr_pos_extremo', label: 'Jr após o choque' }]} />
          <TimeLines title="PDD ÷ Over 90 e PDD ÷ PDD implícita (Res. 2.682 sobre SCR)" data={d.data} fmt="x"
            series={[{ key: 'pdd_over90', label: 'PDD ÷ Over 90' }, { key: 'pdd_sobre_2682', label: 'PDD ÷ 2.682 implícita' }]} />
        </div>
      )}
      {d.data && <DataGrid title="Histórico (36 meses)" rows={[...d.data].reverse()} exportUrl={`/api/fundos/${cnpj}/casa?meses=36`} height={360}
        cols={['dt', 'pl', 'jr', 'mz', 'sr', 'subordinacao', 'm01_jr_pdd', 'm02_jr_vencidos360', 'm16_custo_credito', 'm19_excesso_spread',
               'm21_retorno_jr_12m', 'm05_recompra_carteira', 'm06_preco_recompra', 'over90_carteira', 'over180_pl', 'pdd_over90',
               'm29_colchao_carteira', 'q_status', 'q_checks']} />}
    </div>
  )
}

function KpiSmall({ k, v }: { k: string; v: any }) {
  const { data: dic } = useDic()
  return <div className="kpi" title={dic?.[k]?.desc}><div className="l">{colLabel(dic, k)}</div>
    <div className="v" style={{ fontSize: 17 }}>{fmtValue(v, dic?.[k]?.fmt)}</div></div>
}

/* ---------- safras por mês de vencimento ---------- */
export function Safras({ cnpj }: { cnpj: string }) {
  const d = useApi<Row[]>(`/api/fundos/${cnpj}/safras`)
  const rows = (d.data ?? []).map((r) => ({ ...r, dt: r.safra }))
  return (
    <div className="stack">
      <p className="sub" style={{ margin: 0 }}>
        Safras por mês de vencimento (proxy sem fita, método da análise do MR FIDC): base = a vencer em até 30 dias no fim do mês anterior;
        F30 = vencidos 31-60 d um mês depois; F60 = 61-90 d dois meses depois; F180 ≈ perda da safra. Safras recentes ainda não têm F60/F180.
      </p>
      <Loading q={d} />
      {d.data && <TimeLines title="F30 / F60 / F180 por safra" data={rows} fmt="pct"
        series={[{ key: 'f30', label: 'F30' }, { key: 'f60', label: 'F60' }, { key: 'f180', label: 'F180' }]} />}
      {d.data && <DataGrid rows={[...d.data].reverse()} exportUrl={`/api/fundos/${cnpj}/safras`} height={340}
        cols={['safra', 'base', 'f30', 'f60', 'f180', 'f360', 'f30_base_aquisicoes']} />}
    </div>
  )
}

/* ---------- stress test ---------- */
export function Stress({ cnpj }: { cnpj: string }) {
  const [p, setP] = useState({ perda_base: '', lgd_evento: '60', evento_pct_pl: '', spread_aa: '' })
  const q = new URLSearchParams()
  if (p.perda_base) q.set('perda_base', String(Number(p.perda_base) / 100))
  if (p.lgd_evento) q.set('lgd_evento', String(Number(p.lgd_evento) / 100))
  if (p.evento_pct_pl) q.set('evento_pct_pl', String(Number(p.evento_pct_pl) / 100))
  if (p.spread_aa) q.set('spread_aa', String(Number(p.spread_aa) / 100))
  const d = useApi<any>(`/api/fundos/${cnpj}/stress?${q}`)
  const field = (k: keyof typeof p, label: string, ph: string) => (
    <label className="stack" style={{ gap: 2 }}><span className="muted">{label}</span>
      <input type="text" style={{ width: 130 }} placeholder={ph} value={p[k]} onChange={(e) => setP({ ...p, [k]: e.target.value })} /></label>)
  return (
    <div className="stack">
      <div className="row" style={{ alignItems: 'flex-end' }}>
        {field('perda_base', 'Perda anual base (% carteira)', d.data?.custo_credito_base != null ? (d.data.custo_credito_base * 100).toFixed(2) : 'M16')}
        {field('spread_aa', 'Excesso de spread (% a.a.)', d.data?.excesso_spread != null ? (d.data.excesso_spread * 100).toFixed(2) : 'M19')}
        {field('evento_pct_pl', 'Evento: exposição (% PL)', d.data?.evento_pct_pl != null ? (d.data.evento_pct_pl * 100).toFixed(2) : 'maior cedente')}
        {field('lgd_evento', 'LGD do evento (%)', '60')}
        <span className="muted">Vazio = valor observado no informe.</span>
      </div>
      <Loading q={d} />
      {d.data && !d.data.disponivel && <div className="muted">{d.data.motivo}</div>}
      {d.data?.disponivel && (
        <>
          <div className="kpis">
            <KpiFmt label="Perda anual que zera a Jr" v={d.data.limiar_perda_jr} fmt="pct" sub={`${fmtValue(d.data.multiplo_limiar_jr, 'x')} o custo de crédito`} />
            <KpiFmt label="Perda anual que atinge a sênior" v={d.data.limiar_perda_senior} fmt="pct" sub={`${fmtValue(d.data.multiplo_limiar_senior, 'x')} o custo de crédito`} />
            <KpiFmt label="Custo de crédito base (M16)" v={d.data.custo_credito_base} fmt="pct" />
            <KpiFmt label="Excesso de spread (M19)" v={d.data.excesso_spread} fmt="pct" />
          </div>
          <table className="simple">
            <thead><tr><th>Cenário</th><th className="r">Perda anual</th><th className="r">Evento</th><th className="r">Receita para absorver</th>
              <th className="r">Consumo do colchão</th><th className="r">Perda Jr</th><th className="r">Perda Mz</th><th className="r">Perda Sênior</th><th className="r">Jr/PL final</th></tr></thead>
            <tbody>{d.data.cenarios.map((c: Row) => (
              <tr key={c.cenario}><td>{c.cenario}</td><td className="r">{fmtValue(c.perda_anual_pct, 'pct')}</td><td className="r">{fmtValue(c.evento_rs, 'brl')}</td>
                <td className="r">{fmtValue(c.receita_rs, 'brl')}</td><td className="r">{fmtValue(c.consumo_rs, 'brl')}</td>
                <td className="r">{fmtValue(c.perda_jr_pct, 'pct')}</td><td className="r">{fmtValue(c.perda_mz_pct, 'pct')}</td>
                <td className={`r ${c.perda_sr_pct > 0 ? 'worst' : ''}`}>{fmtValue(c.perda_sr_pct, 'pct')}</td><td className="r">{fmtValue(c.jr_pl_final, 'pct')}</td></tr>))}</tbody>
          </table>
          <p className="muted">{d.data.premissas} Modelo simplificado para triagem e acompanhamento mensal; o stress de comitê (planilha) usa
            premissas de regulamento, taxa de cessão e custos que o informe não traz.</p>
        </>
      )}
    </div>
  )
}

function KpiFmt({ label, v, fmt, sub }: { label: string; v: any; fmt: string; sub?: string }) {
  return <div className="kpi"><div className="l">{label}</div><div className="v">{fmtValue(v, fmt)}</div>{sub && <div className="c">{sub}</div>}</div>
}

/* ---------- qualidade do fundo ---------- */
export function QualidadeFundo({ cnpj }: { cnpj: string }) {
  const d = useApi<Row[]>(`/api/fundos/${cnpj}/qualidade`)
  return (
    <div className="stack">
      <Loading q={d} />
      {d.data && !d.data.length && <div className="muted">Nenhuma checagem falhou nos últimos 13 meses.</div>}
      {d.data && d.data.length > 0 && (
        <table className="simple">
          <thead><tr><th>Mês</th><th>#</th><th>Severidade</th><th>Checagem</th><th>O que fazer</th></tr></thead>
          <tbody>{d.data.map((q, i) => (
            <tr key={i}><td>{mesAno(q.dt)}</td><td>{q.id}</td><td className={`sev-${q.severidade}`}>{q.severidade}</td>
              <td>{q.descricao}</td><td className="muted">{q.recomendacao}</td></tr>))}</tbody>
        </table>
      )}
    </div>
  )
}

/* ---------- regulamento vigente lido do FNET ---------- */
const STATUS_REG: Record<string, string> = {
  ok: 'lido', ilegivel: 'PDF sem texto legível (escaneado ou fonte sem tabela de caracteres) - preencha manualmente',
  sem_regulamento: 'nenhum regulamento encontrado no FNET para este CNPJ', nao_pdf: 'documento do FNET não é PDF',
  erro: 'falha ao baixar do FNET', nao_processado: 'ainda não processado (rode python -m fidc.regulamentos)',
}

function RegulamentoExtraido({ cnpj, onConfirm }: { cnpj: string; onConfirm: () => void }) {
  const d = useApi<Row>(`/api/fundos/${cnpj}/regulamento/extraido`, { staleTime: 0 })
  const r = d.data
  if (!r) return <Loading q={d} />
  const confirmar = async (c: Row) => {
    await send('PUT', `/api/fundos/${cnpj}/params`, { chave: c.campo, competencia: '', valor_num: c.valor_num,
      valor_txt: c.valor_txt, fonte: `Regulamento${c.pagina ? ` p. ${c.pagina}` : ''} (${c.fonte === 'ia' ? 'leitura IA' : 'extração'} confirmada)`, data_base: r.data_entrega?.slice(0, 10) ?? null })
    onConfirm(); d.refetch()
  }
  const params = (r.campos ?? []).filter((c: Row) => c.parametro)
  const textos = (r.campos ?? []).filter((c: Row) => !c.parametro && c.campo.startsWith('eventos'))
  return (
    <div className="card stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 12, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>Regulamento vigente (FNET)</h2>
        <span className="muted">{STATUS_REG[r.status] ?? r.status}</span>
        {r.data_entrega && <span className="muted">entregue em {r.data_entrega} · {r.n_paginas} páginas · {r.tipo}</span>}
        {r.url_ver && <a href={r.url_ver} target="_blank" rel="noreferrer">abrir no FNET</a>}
        {r.url_pdf && <a href={r.url_pdf} target="_blank" rel="noreferrer">baixar PDF</a>}
      </div>
      <p className="muted" style={{ margin: 0 }}>Leitura automática do regulamento (IA quando disponível, senão regras de texto). Os valores abaixo entram nas métricas derivadas
        enquanto não houver dado manual; confira o trecho e clique em Confirmar para gravar como dado manual.</p>
      {r.ia && (
        <div className="card" style={{ background: 'var(--surface-2, transparent)' }}>
          <b>Leitura por IA</b> <span className="muted">({r.ia.modelo}, confiança {r.ia.confianca}, {String(r.ia.processado_em).slice(0, 10)})</span>
          <div>Tese: <b>{r.ia.tese}</b>{r.ia.consignado && r.ia.consignado !== 'nao_e_consignado' && <> · consignado: <b>{r.ia.consignado}</b></>}
            {r.ia.multicedente != null && <> · multicedente: {r.ia.multicedente ? 'sim' : 'não'}</>}
            {r.ia.multissacado != null && <> · multissacado: {r.ia.multissacado ? 'sim' : 'não'}</>}</div>
          <div className="muted">{r.ia.lastro}</div>
          {r.ia.observacoes && <div className="muted">{r.ia.observacoes}</div>}
          {(r.ia.eventos_avaliacao?.length > 0 || r.ia.eventos_liquidacao?.length > 0) && (
            <div className="grid2" style={{ marginTop: 6 }}>
              <div><b>Eventos de avaliação</b><ul>{r.ia.eventos_avaliacao.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul></div>
              <div><b>Eventos de liquidação</b><ul>{r.ia.eventos_liquidacao.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul></div>
            </div>)}
        </div>
      )}
      {r.teses?.length > 0 && (
        <div className="muted">Tese pelo texto (menções): {r.teses.slice(0, 5).map((t: Row) => `${t.tese} ${t.mencoes}`).join(' · ')}</div>
      )}
      {params.length > 0 && (
        <table className="simple">
          <thead><tr><th>Dado</th><th className="r">Valor extraído</th><th>Leitura</th><th>Página</th><th>Confiança</th><th>Trecho</th><th /></tr></thead>
          <tbody>{params.map((c: Row) => (
            <tr key={c.campo}>
              <td>{c.label}</td>
              <td className="r">{c.valor_num != null ? fmtValue(c.valor_num, c.fmt) : c.valor_txt}</td>
              <td className="muted">{c.fonte === 'ia' ? 'IA' : 'regras'}</td>
              <td>{c.pagina ?? ''}</td><td className="muted">{c.confianca}</td>
              <td style={{ maxWidth: 640 }}><details><summary className="muted" style={{ cursor: 'pointer' }}>{String(c.trecho).slice(0, 90)}…</summary>
                <div style={{ whiteSpace: 'pre-wrap' }}>{c.trecho}</div></details></td>
              <td>{c.tem_manual ? <span className="muted">manual prevalece</span>
                : <button style={{ padding: '0 8px' }} onClick={() => confirmar(c)}>Confirmar</button>}</td>
            </tr>))}</tbody>
        </table>
      )}
      {textos.map((c: Row) => (
        <details key={c.campo}><summary style={{ cursor: 'pointer' }}><b>{c.campo === 'eventos_avaliacao' ? 'Eventos de avaliação' : 'Eventos de liquidação'}</b>
          <span className="muted"> (p. {c.pagina}, início da seção)</span></summary>
          <div style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>{c.valor_txt}…</div></details>
      ))}
    </div>
  )
}

/* ---------- regulamento e dados do gestor (manuais) ---------- */
export function Regulamento({ cnpj }: { cnpj: string }) {
  const qc = useQueryClient()
  const cat = useApi<any>('/api/catalogo', { staleTime: Infinity })
  const params = useApi<Row[]>(`/api/fundos/${cnpj}/params`, { staleTime: 0 })
  const der = useApi<Row[]>(`/api/fundos/${cnpj}/regulamento`, { staleTime: 0 })
  const [f, setF] = useState({ chave: '', competencia: '', valor: '', fonte: '', data_base: '' })
  const meta = cat.data?.parametros?.find((p: Row) => p.chave === f.chave)
  const refresh = () => { qc.invalidateQueries({ queryKey: [`/api/fundos/${cnpj}/params`] }); qc.invalidateQueries({ queryKey: [`/api/fundos/${cnpj}/regulamento`] }) }
  const salvar = async () => {
    const isNum = meta && meta.fmt !== 'txt'
    const num = isNum ? Number(f.valor.replace(',', '.')) / (meta.fmt === 'pct' ? 100 : 1) : null
    await send('PUT', `/api/fundos/${cnpj}/params`, { chave: f.chave, competencia: f.competencia, valor_num: num,
      valor_txt: isNum ? null : f.valor, fonte: f.fonte, data_base: f.data_base || null })
    setF({ ...f, valor: '' }); refresh()
  }
  return (
    <div className="stack">
      <RegulamentoExtraido cnpj={cnpj} onConfirm={refresh} />
      <p className="sub" style={{ margin: 0 }}>Dados que o informe não traz (regulamento, suplemento, rating, relatório do gestor). Sempre com fonte e data-base.
        Alimentam M03/M04, folga de subordinação (RF08), RF21 e o roteiro de DD.</p>
      {der.data && der.data.length > 0 && (
        <table className="simple">
          <thead><tr><th>Métrica derivada</th><th className="r">Valor</th><th>Red flag</th><th>Fonte</th></tr></thead>
          <tbody>{der.data.map((m) => (
            <tr key={m.metrica}><td>{m.metrica}{m.nota && <div className="muted">{m.nota}</div>}</td><td className="r">{fmtValue(m.valor, m.fmt)}</td>
              <td className={m.red_flag?.includes(' V') ? 'worst' : ''}>{m.red_flag ?? 'ok'}</td><td className="muted">{m.fonte}</td></tr>))}</tbody>
        </table>
      )}
      <div className="card stack" style={{ gap: 8 }}>
        <div className="row" style={{ gap: 8, alignItems: 'flex-end' }}>
          <select value={f.chave} onChange={(e) => setF({ ...f, chave: e.target.value })}>
            <option value="">Escolha o dado…</option>
            {cat.data?.parametros?.map((p: Row) => <option key={p.chave} value={p.chave}>{p.label}</option>)}
          </select>
          <input type="text" style={{ width: 120 }} placeholder={meta?.fmt === 'pct' ? 'valor em %' : 'valor'} value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} />
          <input type="text" style={{ width: 110 }} placeholder="competência AAAA-MM (opcional)" value={f.competencia} onChange={(e) => setF({ ...f, competencia: e.target.value })} />
          <input type="text" style={{ width: 220 }} placeholder="fonte (ex.: Anexo I cl. 5.1)" value={f.fonte} onChange={(e) => setF({ ...f, fonte: e.target.value })} />
          <input type="text" style={{ width: 120 }} placeholder="data-base" value={f.data_base} onChange={(e) => setF({ ...f, data_base: e.target.value })} />
          <button className="primary" disabled={!f.chave || !f.valor || !f.fonte} onClick={salvar}>Salvar</button>
        </div>
        {meta && <div className="muted">Fonte típica: {meta.fonte} · usado em: {meta.uso}</div>}
      </div>
      <table className="simple">
        <thead><tr><th>Dado</th><th>Competência</th><th className="r">Valor</th><th>Fonte</th><th>Data-base</th><th>Autor</th><th /></tr></thead>
        <tbody>{params.data?.map((p) => {
          const m = cat.data?.parametros?.find((x: Row) => x.chave === p.chave)
          return (
            <tr key={p.chave + p.competencia}><td>{m?.label ?? p.chave}</td><td>{p.competencia || 'estático'}</td>
              <td className="r">{p.valor_num != null ? fmtValue(p.valor_num, m?.fmt) : p.valor_txt}</td>
              <td className="muted">{p.fonte}</td><td>{p.data_base}</td><td className="muted">{p.autor}</td>
              <td><button style={{ padding: '0 6px' }} onClick={async () => {
                await send('DELETE', `/api/fundos/${cnpj}/params/${p.chave}?competencia=${p.competencia}`); refresh() }}>×</button></td></tr>)
        })}</tbody>
      </table>
    </div>
  )
}

/* ---------- roteiro de DD ---------- */
const STATUS: [string, string][] = [['pendente', 'Pendente'], ['ok', 'OK'], ['atencao', 'Atenção'], ['red_flag', 'Red flag'], ['nao_se_aplica', 'N/A']]
const FONTE_COR: Record<string, string> = { informe: 'var(--s3)', externo: 'var(--s7)', regulamento: 'var(--s2)', gestor: 'var(--s4)', rating: 'var(--s5)' }

export function Roteiro({ cnpj }: { cnpj: string }) {
  const qc = useQueryClient()
  const d = useApi<Row[]>(`/api/fundos/${cnpj}/roteiro`, { staleTime: 0 })
  const salvar = async (pid: string, body: Row) => {
    await send('PUT', `/api/fundos/${cnpj}/roteiro/${pid}`, body); qc.invalidateQueries({ queryKey: [`/api/fundos/${cnpj}/roteiro`] })
  }
  return (
    <div className="stack">
      <Loading q={d} />
      <div className="legend">{Object.entries(FONTE_COR).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}
        <span className="muted">· itens "informe" e "externo" já vêm calculados; os demais dependem de documento ou do gestor.</span></div>
      {d.data?.map((r) => (
        <div key={r.id} className="stack">
          <h2 style={{ margin: 0 }}>{r.nome}</h2>
          {r.blocos.map((b: Row) => (
            <details key={b.nome} className="card" open>
              <summary style={{ cursor: 'pointer' }}><b>{b.nome}</b> <span className="muted">
                ({b.itens.filter((i: Row) => i.resposta && i.resposta.status !== 'pendente').length}/{b.itens.length} respondidos)</span></summary>
              <table className="simple" style={{ marginTop: 8 }}>
                <tbody>{b.itens.map((i: Row) => <ItemDD key={i.id} i={i} onSave={(body) => salvar(i.id, body)} />)}</tbody>
              </table>
            </details>
          ))}
        </div>
      ))}
    </div>
  )
}

function ItemDD({ i, onSave }: { i: Row; onSave: (b: Row) => void }) {
  const [txt, setTxt] = useState(i.resposta?.resposta ?? '')
  const [status, setStatus] = useState(i.resposta?.status ?? 'pendente')
  const a = i.auto
  return (
    <tr>
      <td style={{ width: 8, background: FONTE_COR[i.fonte] ?? 'var(--axis)' }} title={i.fonte} />
      <td style={{ width: '38%' }}>{i.pergunta}<div className="muted">{i.fonte}</div></td>
      <td style={{ width: '22%' }}>{a ? (
        <div className="num">
          <b>{typeof a.valor === 'number' ? (a.unidade ? `${a.valor.toLocaleString('pt-BR')} ${a.unidade}` : fmtValue(a.valor, a.fmt ?? 'num')) : a.valor ?? '–'}</b>
          {a.mediana_pares != null && <div className="muted">mediana pares {fmtValue(a.mediana_pares, a.fmt)} · {a.posicao}</div>}
          {a.valor_12m_antes != null && <div className="muted">12m antes: {a.valor_12m_antes.toLocaleString('pt-BR')}</div>}
          <div className="muted">{a.fonte}{a.data_base ? ` · ${fmtDate(a.data_base)}` : ''}</div>
        </div>) : <span className="muted">–</span>}</td>
      <td>
        <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
          <select value={status} onChange={(e) => { setStatus(e.target.value); onSave({ status: e.target.value, resposta: txt }) }}>
            {STATUS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input type="text" style={{ flex: 1 }} placeholder="resposta / evidência" value={txt} onChange={(e) => setTxt(e.target.value)}
            onBlur={() => txt !== (i.resposta?.resposta ?? '') && onSave({ status, resposta: txt })} />
        </div>
        {i.resposta?.autor && <div className="muted">{i.resposta.autor} · {fmtDate(i.resposta.atualizado_em)}</div>}
      </td>
    </tr>
  )
}

export function AgingBars({ data }: { data: Row[] }) {
  return <Bars title="Carteira por prazo: a vencer vs. vencido" data={data} x="faixa" fmt="brl"
    series={[{ key: 'a_vencer', label: 'A vencer (por prazo)' }, { key: 'vencido', label: 'Vencido (por atraso)' }]} />
}

/* ---------- resumo mês a mês (informe CVM) + rentabilidade por série ---------- */
export type MensalResp = {
  meses: Row[]
  series: { key: string; serie: string; tipo: string; rotulo: string }[]
  janelas: Row[]
}

export function ResumoMensal({ cnpj }: { cnpj: string }) {
  const d = useApi<MensalResp>(`/api/fundos/${cnpj}/mensal?meses=60`)
  if (!d.data) return <Loading q={d} />
  const { meses, series, janelas } = d.data
  const ativas = series.filter((s) => meses.some((m) => m[`${s.key}_rentab`] != null))
  const cols: any[] = [
    'dt', 'pl', 'pl_senior', 'pl_mezanino', 'pl_subordinada', 'subordinacao', 'subordinacao_junior', 'carteira',
    'inad_90', 'inad_total', 'pdd_carteira', 'cobertura_pdd_90', 'cdi_mes',
    ...ativas.flatMap((s) => [
      { field: `${s.key}_rentab`, headerName: `${s.rotulo} · mês`, fmt: 'pct', width: 120,
        headerTooltip: `${s.serie}: rentabilidade do mês (ajustada por amortização quando a informada não a considera)` },
      { field: `${s.key}_pct_cdi`, headerName: `${s.rotulo} · %CDI`, fmt: 'pct', width: 120,
        headerTooltip: `${s.serie}: rentabilidade do mês / CDI do mês` },
    ]),
    'captacoes', 'resgates', 'amortizacoes', 'aquisicoes', 'recompras', 'prazo_medio_dias', 'top1_cedente_pct',
    'nr_cotistas',
  ]
  return (
    <div className="stack" style={{ marginTop: 16 }}>
      {janelas.length > 0 && (
        <div>
          <h3>Rentabilidade acumulada por série vs. CDI</h3>
          <table className="simple">
            <thead><tr><th>Série</th>{['3 meses', '6 meses', '12 meses', '24 meses', 'Desde o início*'].map((h) => (
              <th key={h} className="r" colSpan={2}>{h}</th>))}</tr>
              <tr><th />{['3m', '6m', '12m', '24m', 'inicio'].flatMap((k) => [
                <th key={k + 'c'} className="r muted">cota</th>, <th key={k + 'p'} className="r muted">% CDI</th>])}</tr></thead>
            <tbody>{janelas.map((j) => (
              <tr key={j.serie} title={j.serie}><td>{j.rotulo}</td>
                {['3m', '6m', '12m', '24m', 'inicio'].flatMap((k) => [
                  <td key={k + 'c'} className="r num">{fmtValue(j[`cota_${k}`], 'pct')}</td>,
                  <td key={k + 'p'} className="r num muted">{fmtValue(j[`pct_cdi_${k}`], 'pct')}</td>])}</tr>))}</tbody>
          </table>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            * desde o primeiro mês da série no informe. Janela só aparece com todos os meses disponíveis.
            Rentabilidade ajustada por amortização quando o administrador informou a variação crua da cota (estimativa).
          </div>
        </div>
      )}
      <DataGrid title="Mês a mês (informe CVM)" rows={meses} cols={cols} height={460}
        exportUrl={`/api/fundos/${cnpj}/mensal?meses=120`} />
    </div>
  )
}
