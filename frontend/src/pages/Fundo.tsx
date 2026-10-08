import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { send, useApi, useDic, useTaxonomia, type Row } from '../api'
import { Bars, TimeLines } from '../components/Charts'
import { DataGrid } from '../components/DataGrid'
import { Alertas, Kpi, Loading, Tabs, type Alerta } from '../components/ui'
import ComparePanel, { defaultPeers, PeerSelector, RedFlagChip, type PeerOpts } from '../components/Comparar'
import { Casa, Mudancas, QualidadeBadge, QualidadeFundo, Regulamento, ResumoMensal, Roteiro, Safras, Stress } from './FundoTabs'
import { fmtCnpj, fmtDate, fmtValue, mesAno } from '../fmt'

type Lamina = {
  cabecalho: Row; kpis: Row; comparativo: Row[]; series: Row[]; cedentes: Row[]; aging: Row[]
  alertas: Alerta[]; listas: string[]; notas: Row[]
}

const SEG: Record<string, string> = {
  A: 'Industrial', B: 'Imobiliário', C1: 'Comercial', C2: 'Varejo', C3: 'Arrendamento', D1: 'Serviços',
  D2: 'Serviços públicos', D3: 'Educação', D4: 'Entretenimento', E: 'Agronegócio', F1: 'Crédito pessoal',
  F2: 'Consignado', F3: 'Corporativo', F4: 'Middle market', F5: 'Veículos', F6: 'Imob. empresarial',
  F7: 'Imob. residencial', F8: 'Financeiro - outros', G: 'Cartão de crédito', H1: 'Factoring PF',
  H2: 'Factoring PJ', I1: 'Precatórios', I2: 'Tributário', I3: 'Royalties', I4: 'Setor público - outros',
  J: 'Ações judiciais', K: 'Marcas/PI',
}

export default function Fundo() {
  const { cnpj = '' } = useParams()
  const qc = useQueryClient()
  const { data: dic } = useDic()
  const lam = useApi<Lamina>(`/api/fundos/${cnpj}`)
  const hist = useApi<Row[]>(`/api/fundos/${cnpj}/historico?meses=60`)
  type Tab = 'pares' | 'geral' | 'casa' | 'safra' | 'stress' | 'carteira' | 'series' | 'qualidade' | 'regulamento' | 'roteiro' | 'eventos' | 'notas'
  const [tab, setTab] = useState<Tab>('pares')
  const [peers, setPeers] = useState<PeerOpts>(defaultPeers)
  const comp = useApi<any>(`/api/comparar/${cnpj}?modo=categoria&ignorar_sem_vencido=true`)
  const eventos = useApi<{ ok: boolean; aviso?: string; documentos: Row[] }>(tab === 'eventos' ? `/api/fundos/${cnpj}/eventos` : null)

  if (!lam.data) return <Loading q={lam} />
  const { cabecalho: h, kpis: k, listas } = lam.data
  const refresh = () => qc.invalidateQueries({ queryKey: [`/api/fundos/${cnpj}`] })
  const toggle = async (tipo: string) => {
    if (listas.includes(tipo)) await send('DELETE', `/api/listas/${tipo}/${cnpj}`)
    else await send('POST', `/api/listas/${tipo}`, { cnpj })
    refresh(); qc.invalidateQueries({ queryKey: [`/api/listas/${tipo}`] })
  }
  const compSetor = Object.fromEntries(lam.data.comparativo.map((c) => [c.metrica, c]))
  const vsSetor = (key: string) => {
    const c = compSetor[key]
    if (!c || c.mediana == null) return undefined
    return <>mediana setor {fmtValue(c.mediana, dic?.[key]?.fmt)}</>
  }

  return (
    <div className="stack">
      <div className="card stack" style={{ gap: 10 }}>
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 280 }}>
            <h1>{h.nome}</h1>
            <div className="sub">
              {fmtCnpj(h.cnpj)} · <Link to={`/setores/${h.categoria}`}>{h.categoria_nome}</Link>
              {h.revisar && <span className="badge" style={{ marginLeft: 6 }} title="Classificação automática de baixa confiança">⚠ revisar categoria</span>}
              {h.ia_diverge_informe && <span className="badge" style={{ marginLeft: 6 }}
                title={`O regulamento (leitura por IA) indica tese "${h.ia_tese}", mas só ${fmtValue(h.ia_carteira_compat, 'pct')} da carteira declarada no informe CVM (Tab. II, sem os segmentos "outros") está em segmentos compatíveis. Pode ser leitura errada do regulamento, fundo fora da política ou informe preenchido no segmento errado.`}>
                ⚠ regulamento x carteira</span>}
              {' '}<QualidadeBadge status={comp.data?.fundo?.q_status} checks={comp.data?.fundo?.q_checks} />
              {' '}· segmento CVM: {SEG[h.segmento_principal] ?? '–'} ({fmtValue(h.segmento_principal_pct, 'pct')})
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className={listas.includes('carteira') ? 'primary' : ''} onClick={() => toggle('carteira')}>
              {listas.includes('carteira') ? '✓ Na carteira' : '+ Carteira'}</button>
            <button className={listas.includes('watchlist') ? 'primary' : ''} onClick={() => toggle('watchlist')}>
              {listas.includes('watchlist') ? '✓ Na watchlist' : '+ Watchlist'}</button>
            <Link className="btn" to={`/comparar?cnpj=${cnpj}`}>Comparar</Link>
            <a className="btn primary" href={`/lamina/${cnpj}?print=1`} target="_blank" rel="noreferrer"
              title="Relatório de 3 páginas A4 para a diretoria; abre em nova aba e chama Salvar como PDF">⬇ Lâmina PDF</a>
            <a className="btn" href={`/api/fundos/${cnpj}/lamina.xlsx`}>⬇ Lâmina Excel</a>
            <a className="btn" href={`/api/fundos/${cnpj}/comite.xlsx`}>⬇ Pacote do comitê</a>
          </div>
        </div>
        <table className="simple" style={{ maxWidth: 1100 }}>
          <tbody>
            <tr><th>Gestor</th><td>{h.gestor ?? '–'}</td><th>Administrador</th><td>{h.admin ?? '–'}</td></tr>
            <tr><th>Custodiante</th><td>{h.custodiante ?? '–'}</td><th>Auditor</th><td>{h.auditor ?? '–'}</td></tr>
            <tr><th>Condomínio</th><td>{h.condominio ?? '–'}{h.exclusivo === 'S' ? ' · exclusivo' : ''}</td>
              <th>Situação CVM</th><td>{h.situacao ?? '–'}</td></tr>
            <tr><th>Início (cadastro)</th><td>{fmtDate(h.data_inicio)}</td>
              <th>Informes desde</th><td>{mesAno(h.primeiro_informe)} · último {mesAno(h.ultimo_informe)}</td></tr>
          </tbody>
        </table>
      </div>

      <div className="grid2">
        <div className="card"><h2>Alertas</h2><Alertas items={lam.data.alertas} />
          {comp.data && comp.data.red_flags.some((f: Row) => f.nivel > 0) && (
            <table className="simple" style={{ marginTop: 10 }}>
              <thead><tr><th>Red flag</th><th>Nível</th><th>Número</th></tr></thead>
              <tbody>{comp.data.red_flags.filter((f: Row) => f.nivel > 0).map((f: Row) => (
                <tr key={f.id} title={`${f.definicao ?? ''}\n\nRegra: ${f.regra}`}><td style={{ textDecoration: 'underline dotted', cursor: 'help' }}>{f.nome}</td><td><RedFlagChip nivel={f.nivel} /></td>
                  <td className="muted">{f.detalhe}</td></tr>))}</tbody>
            </table>)}
        </div>
        <div className="card"><h2>O que mudou no mês</h2><Mudancas cnpj={cnpj} /></div>
      </div>

      <div className="kpis">
        <Kpi k="pl" v={k.pl} compare={<>mês {fmtValue(k.pl_var_mes, 'pct')}</>} />
        <Kpi k="inad_90" v={k.inad_90} compare={vsSetor('inad_90')} />
        <Kpi k="inad_contratos" v={k.inad_contratos} compare={vsSetor('inad_contratos')} />
        <Kpi k="pdd_carteira" v={k.pdd_carteira} compare={vsSetor('pdd_carteira')} />
        <Kpi k="cobertura_pdd_90" v={k.cobertura_pdd_90} compare={vsSetor('cobertura_pdd_90')} />
        <Kpi k="subordinacao" v={k.subordinacao} compare={vsSetor('subordinacao')} />
        <Kpi k="rentab_senior" v={k.rentab_senior} compare={vsSetor('rentab_senior')} />
        <Kpi k="rentab_subordinada" v={k.rentab_subordinada} compare={vsSetor('rentab_subordinada')} />
        <Kpi k="prazo_medio_dias" v={k.prazo_medio_dias} compare={vsSetor('prazo_medio_dias')} />
        <Kpi k="top1_cedente_pct" v={k.top1_cedente_pct} compare={vsSetor('top1_cedente_pct')} />
        <Kpi k="liquidez_30_pl" v={k.liquidez_30_pl} />
        <Kpi k="nr_cotistas" v={k.nr_cotistas} />
      </div>

      <div className="card">
        <Tabs value={tab} onChange={setTab} options={[
          ['pares', 'Vs. pares'], ['geral', 'Evolução'], ['casa', 'Métricas da casa'], ['safra', 'Safras e proxies'],
          ['stress', 'Stress'], ['carteira', 'Carteira e cedentes'], ['series', 'Séries'], ['qualidade', 'Qualidade do dado'],
          ['regulamento', 'Regulamento e gestor'], ['roteiro', 'Roteiro de DD'], ['eventos', 'Eventos FNET'],
          ['notas', `Notas (${lam.data.notas.length})`]]} />
        {tab === 'pares' && (
          <div className="stack">
            <PeerSelector value={peers} onChange={setPeers} />
            <ComparePanel cnpj={cnpj} peers={peers} />
          </div>
        )}
        {tab === 'casa' && <Casa cnpj={cnpj} />}
        {tab === 'stress' && <Stress cnpj={cnpj} />}
        {tab === 'qualidade' && <QualidadeFundo cnpj={cnpj} />}
        {tab === 'regulamento' && <Regulamento cnpj={cnpj} />}
        {tab === 'roteiro' && <Roteiro cnpj={cnpj} />}
        <Loading q={hist} />
        {tab === 'geral' && hist.data && (
          <div className="grid2">
            <TimeLines title="PL" data={hist.data} fmt="brl" series={[{ key: 'pl', label: 'PL' }]} />
            <TimeLines title="Inadimplência >90d" data={hist.data} fmt="pct"
              series={[{ key: 'inad_90', label: 'Fundo' }, { key: 'setor_inad_90', label: 'Mediana da categoria', dashed: true, color: 'var(--muted)' }]} />
            <TimeLines title="PDD / carteira" data={hist.data} fmt="pct"
              series={[{ key: 'pdd_carteira', label: 'Fundo' }, { key: 'setor_pdd_carteira', label: 'Mediana da categoria', dashed: true, color: 'var(--muted)' }]} />
            <TimeLines title="Subordinação" data={hist.data} fmt="pct"
              series={[{ key: 'subordinacao', label: 'Fundo' }, { key: 'setor_subordinacao', label: 'Mediana da categoria', dashed: true, color: 'var(--muted)' }]} />
            <TimeLines title="Rentabilidade sênior (mês)" data={hist.data} fmt="pct100"
              series={[{ key: 'rentab_senior', label: 'Fundo' }, { key: 'setor_rentab_senior', label: 'Mediana da categoria', dashed: true, color: 'var(--muted)' }]} />
            <TimeLines title="Rentabilidade subordinada (mês)" data={hist.data} fmt="pct100"
              series={[{ key: 'rentab_subordinada', label: 'Fundo' }, { key: 'setor_rentab_subordinada', label: 'Mediana da categoria', dashed: true, color: 'var(--muted)' }]} />
          </div>
        )}
        {tab === 'geral' && <ResumoMensal cnpj={cnpj} />}
        {tab === 'safra' && hist.data && (
          <div className="stack">
            <Safras cnpj={cnpj} />
            <h2 style={{ marginTop: 12 }}>Outros proxies (faixas de atraso e fluxos)</h2>
            <p className="sub" style={{ margin: 0 }}>
              O informe da CVM não traz dados por safra de originação. Estes indicadores aproximam o comportamento
              de safra a partir das faixas de atraso (Tab. V/VI) e das compras/recompras do mês (Tab. VII). Ver definição de cada um passando o mouse nos indicadores.
            </p>
            <div className="grid2">
              <TimeLines title="Roll rates (quanto do atraso migra para a faixa seguinte)" data={hist.data} fmt="pct"
                series={[{ key: 'roll_30_60', label: '1-30→31-60' }, { key: 'roll_60_90', label: '31-60→61-90' }, { key: 'roll_90_120', label: '61-90→91-120' }]} />
              <TimeLines title="Inadimplência >90d: corrente vs. defasada" data={hist.data} fmt="pct"
                series={[{ key: 'inad_90', label: 'Corrente' }, { key: 'inad_90_lag6', label: 'Defasada 6m' }, { key: 'inad_90_lag12', label: 'Defasada 12m' }]} />
              <TimeLines title="Fluxo para >90d / aquisições (4 a 15 meses antes)" data={hist.data} fmt="pct"
                series={[{ key: 'perda_aquisicoes_12m', label: 'Fundo' }]} />
              <TimeLines title="Inadimplência ajustada por recompra/substituição" data={hist.data} fmt="pct"
                series={[{ key: 'inad_90', label: 'Inad. >90d' }, { key: 'inad_90_ajustada', label: 'Ajustada' }, { key: 'recompra_subst_3m_carteira', label: 'Recompra+subst. 3m' }]} />
              <TimeLines title="Perda implícita (baixa de vencidos >360d e variação de PDD)" data={hist.data} fmt="pct"
                series={[{ key: 'baixa_implicita_mes', label: 'Baixa implícita' }, { key: 'var_pdd_mes', label: 'Var. PDD' }]} />
              <TimeLines title="Roll 31-60→61-90: fundo vs. mediana da categoria" data={hist.data} fmt="pct"
                series={[{ key: 'roll_60_90', label: 'Fundo' }, { key: 'setor_roll_60_90', label: 'Mediana da categoria', dashed: true, color: 'var(--muted)' }]} />
            </div>
          </div>
        )}
        {tab === 'carteira' && (
          <div className="grid2">
            <Bars title="Carteira por prazo: a vencer vs. vencido" data={lam.data.aging} x="faixa" fmt="brl"
              series={[{ key: 'a_vencer', label: 'A vencer (por prazo)' }, { key: 'vencido', label: 'Vencido (por atraso)' }]} />
            <div>
              <h3>Maiores cedentes (Tab. I)</h3>
              {lam.data.cedentes.length ? (
                <table className="simple">
                  <thead><tr><th>#</th><th>CPF/CNPJ</th><th className="r">% carteira</th></tr></thead>
                  <tbody>{lam.data.cedentes.map((c) => (
                    <tr key={c.rank}><td>{c.rank}</td><td>{c.cedente_doc?.length === 14 ? fmtCnpj(c.cedente_doc) : c.cedente_doc}</td>
                      <td className="r">{fmtValue(c.pct, 'pct100')}</td></tr>))}</tbody>
                </table>
              ) : <div className="muted">Fundo não informou cedentes.</div>}
              <CategoriaAjuste cnpj={cnpj} atual={h.categoria} origem={h.origem} onDone={refresh} />
            </div>
          </div>
        )}
        {tab === 'series' && (
          <DataGrid rows={lam.data.series} height={360} exportUrl={`/api/fundos/${cnpj}/series`}
            cols={['serie', 'tipo', 'pl_serie', 'valor_cota', 'rentab_mes', 'rentab_12m', 'desempenho_esperado',
                   'desempenho_real', 'nr_cotistas']} />
        )}
        {tab === 'eventos' && (
          <div className="stack" style={{ gap: 6 }}>
            <Loading q={eventos} />
            {eventos.data?.aviso && <div className="alert sev-media"><span className="dot" />{eventos.data.aviso}</div>}
            {eventos.data && (
              <table className="simple">
                <thead><tr><th>Entrega</th><th>Categoria</th><th>Tipo</th><th>Referência</th><th /></tr></thead>
                <tbody>{eventos.data.documentos.map((d) => (
                  <tr key={d.id}><td className="num">{fmtDate(d.data_entrega)}</td><td>{d.categoria}</td>
                    <td>{d.tipo}{d.status?.startsWith('Cancelado') ? ' (cancelado)' : ''}</td><td>{d.data_referencia}</td>
                    <td><a href={d.link} target="_blank" rel="noreferrer">abrir ↗</a></td></tr>))}</tbody>
              </table>
            )}
            <a href={`/api/fundos/${cnpj}/eventos?todos=true`} target="_blank" rel="noreferrer" className="muted">ver todos os documentos (JSON)</a>
          </div>
        )}
        {tab === 'notas' && <Notas cnpj={cnpj} notas={lam.data.notas} onDone={refresh} />}
      </div>
      <p className="muted">Fonte: CVM (informe mensal e cadastro) e FNET/B3. Dados declarados pelo administrador, sem auditoria.</p>
    </div>
  )
}

function CategoriaAjuste({ cnpj, atual, origem, onDone }: { cnpj: string; atual: string; origem: string; onDone: () => void }) {
  const tax = useTaxonomia()
  const [cat, setCat] = useState(atual)
  const [msg, setMsg] = useState('')
  const salvar = async () => {
    const r = await send('PUT', `/api/fundos/${cnpj}/categoria`, { categoria: cat })
    setMsg(r.aviso ?? 'ok')
    setTimeout(onDone, 30_000)
  }
  return (
    <div style={{ marginTop: 20 }}>
      <h3>Categoria</h3>
      <div className="sub" style={{ marginBottom: 6 }}>Origem atual: {origem === 'manual' ? 'ajuste manual' : `automática (${origem})`}</div>
      <div className="row" style={{ gap: 8 }}>
        <select value={cat} onChange={(e) => setCat(e.target.value)}>
          {tax.data?.map((c) => <option key={c.id} value={c.id}>{c.grupo} · {c.nome}</option>)}
        </select>
        <button onClick={salvar} disabled={cat === atual}>Salvar ajuste</button>
        {origem === 'manual' && <button onClick={async () => { await send('DELETE', `/api/fundos/${cnpj}/categoria`); setMsg('Voltando para a regra automática…'); setTimeout(onDone, 30_000) }}>Voltar ao automático</button>}
      </div>
      {msg && <div className="muted" style={{ marginTop: 6 }}>{msg}</div>}
    </div>
  )
}

function Notas({ cnpj, notas, onDone }: { cnpj: string; notas: Row[]; onDone: () => void }) {
  const [texto, setTexto] = useState('')
  const [autor, setAutor] = useState(() => { try { return localStorage.getItem('autor') ?? '' } catch { return '' } })
  const add = async () => {
    try { localStorage.setItem('autor', autor) } catch { /* ignore */ }
    await send('POST', `/api/fundos/${cnpj}/notas`, { texto, autor })
    setTexto(''); onDone()
  }
  return (
    <div className="stack">
      <div className="stack" style={{ gap: 6 }}>
        <textarea placeholder="Tese, conversa com o gestor, ponto de atenção…" value={texto} onChange={(e) => setTexto(e.target.value)} />
        <div className="row" style={{ gap: 8 }}>
          <input type="text" placeholder="Seu nome" value={autor} onChange={(e) => setAutor(e.target.value)} />
          <button className="primary" disabled={!texto.trim()} onClick={add}>Adicionar nota</button>
        </div>
      </div>
      {notas.map((n) => (
        <div key={n.id} className="card" style={{ padding: 12 }}>
          <div className="muted">{n.autor || 'anônimo'} · {fmtDate(n.criado_em)}
            <button style={{ float: 'right', padding: '0 6px' }} title="Excluir"
              onClick={async () => { await send('DELETE', `/api/notas/${n.id}`); onDone() }}>×</button></div>
          <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{n.texto}</div>
        </div>
      ))}
    </div>
  )
}
