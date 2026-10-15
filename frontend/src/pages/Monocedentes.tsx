import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi, type Row } from '../api'
import { DataGrid, type Visao } from '../components/DataGrid'
import { Loading, Tabs } from '../components/ui'
import { fmtValue } from '../fmt'
import { RemuneracaoPrometida } from '../components/Remuneracao'

type Aba = 'bt' | 'remuneracao' | 'universo' | 'calibracao'

const COLS = ['nome', 'bt_score', 'bt_faixa', 'bt_estagio', 'bt_meses_estagio1', 'mono_grupo', 'mono_grupo_atividade',
  'mono_conc_grupo',
  'mono_grupo_cnpjs', 'pl', 'nr_cotistas', 'estrutura', 'taxa_gestao', 'taxa_gestao_min_mes', 'taxa_administracao_min_mes',
  'consultoria', 'consultoria_tipo', 'rem_senior_texto', 'rem_senior_alvo_aa', 'spread_senior_aa',
  'rem_senior_gap_aa', 'rentab_subordinada_12m_pct_cdi',
  'bt_ia_sub', 'bt_ia_indicio', 'gestor', 'admin', 'categoria_nome', 'bt_rotulo', 'bt_sinais']
const COLS_REM = ['nome', 'rem_senior_texto', 'rem_senior_alvo_aa', 'rem_senior_entregue_aa', 'rem_senior_gap_aa', 'rem_senior_n',
  'rentab_senior_12m_pct_cdi', 'rem_mez_texto', 'rem_mez_alvo_aa', 'rem_mez_gap_aa', 'bt_faixa', 'pl', 'gestor', 'rem_senior_doc',
  'rem_senior_data', 'rem_confianca']
const VISOES: Visao[] = [
  { nome: 'Triagem', cols: ['bt_score', 'bt_faixa', 'bt_estagio', 'mono_grupo', 'pl', 'nr_cotistas', 'taxa_gestao', 'gestor', 'bt_sinais'] },
  { nome: 'Estrutura', cols: ['bt_estagio', 'bt_meses_estagio1', 'bt_inicio', 'estrutura', 'nr_cotistas', 'cotistas_senior',
    'cotistas_subordinada', 'subordinacao', 'pl'] },
  { nome: 'Economia', cols: ['bt_score', 'taxa_gestao', 'taxa_gestao_min_mes', 'taxa_administracao', 'taxa_administracao_min_mes',
    'consultoria_taxa_aa', 'consultoria_taxa_min_mes', 'spread_senior_aa', 'rentab_subordinada_12m_pct_cdi',
    'taxa_desconto_aa', 'inad_90', 'pdd_carteira'] },
  { nome: 'Remuneração', cols: ['bt_faixa', 'pl', 'rem_senior_texto', 'rem_senior_alvo_aa', 'rem_senior_entregue_aa',
    'rem_senior_gap_aa', 'rem_senior_n', 'rentab_senior_12m_pct_cdi', 'rem_mez_texto', 'rem_mez_alvo_aa', 'rem_mez_entregue_aa',
    'rem_mez_gap_aa', 'rem_senior_doc', 'rem_senior_data', 'rem_confianca'] },
  { nome: 'Consultoria', cols: ['bt_faixa', 'pl', 'consultoria', 'consultoria_tipo', 'consultoria_n_fundos',
    'mono_consultoria_ligada', 'agente_cobranca', 'mono_cobranca_ligada', 'consultoria_relacionada', 'consultoria_taxa_txt', 'consultoria_taxa_aa', 'consultoria_taxa_min_mes',
    'consultoria_paga_por', 'mono_consultoria_atividade', 'mono_consultoria_abertura', 'mono_grupo', 'gestor'] },
  { nome: 'Regulamento', cols: ['bt_score', 'bt_ia_sub', 'bt_ia_sub_nome', 'bt_ia_coobrigacao', 'bt_ia_indicio',
    'bt_ia_justificativa', 'bt_ia_cedente'] },
  { nome: 'Cedente', cols: ['mono_grupo', 'mono_grupo_cnpjs', 'mono_conc_grupo', 'mono_conc_carteira', 'mono_cedentes_informados',
    'mono_grupo_cnae', 'mono_grupo_atividade', 'bt_nome_cedente', 'categoria_nome'] },
]

function Detalhe({ f, onFechar }: { f: Row; onFechar: () => void }) {
  const g = useApi<Row[]>(`/api/monocedentes/grupos/${f.cnpj}`)
  return (
    <div className="card stack">
      <div className="row"><h2 style={{ margin: 0 }}><Link to={`/fundo/${f.cnpj}`}>{f.nome}</Link></h2><div className="spacer" />
        <button className="ghost" onClick={onFechar}>Fechar</button></div>
      <div className="muted">
        {f.bt_alerta && <b style={{ color: 'var(--critical)' }}>⚠ {f.bt_alerta} · </b>}
        Score {f.bt_score} ({f.bt_faixa}) · estágio {f.bt_estagio ?? '–'} · {fmtValue(f.pl, 'brl')} · gestor {f.gestor ?? '–'}
        {f.bt_rotulo && <> · rótulo do time: <b>{f.bt_rotulo === 'beneficio_tributario' ? 'benefício tributário' : 'não é'}</b></>}
      </div>
      <div>
        <b>Sinais</b>
        <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
          {(f.bt_sinais ? String(f.bt_sinais).split(' | ') : ['nenhum sinal']).map((s: string) => (
            <li key={s} style={{ color: s.startsWith('-') ? 'var(--critical)' : undefined }}>{s}</li>
          ))}
        </ul>
      </div>
      {f.bt_ia_sub && (
        <div className="stack" style={{ gap: 4 }}>
          <b>Regulamento (leitura IA)</b>
          <div>Subordinada: <b>{String(f.bt_ia_sub).replaceAll('_', ' ')}</b>{f.bt_ia_sub_nome ? ` (${f.bt_ia_sub_nome})` : ''}
            {' · '}coobrigação do cedente: {f.bt_ia_coobrigacao ?? '–'} · indício: <b>{f.bt_ia_indicio}</b></div>
          {f.bt_ia_cedente && <div className="muted">Cedente: {f.bt_ia_cedente}</div>}
          {f.bt_ia_objetivo && <div className="muted">Objetivo: {f.bt_ia_objetivo}</div>}
          {f.bt_ia_justificativa && <div>{f.bt_ia_justificativa}</div>}
          {f.bt_ia_trecho && <blockquote className="muted" style={{ margin: 0, paddingLeft: 10, borderLeft: '3px solid var(--grid)' }}>
            “{f.bt_ia_trecho}”{f.bt_ia_pagina ? ` (p. ${f.bt_ia_pagina})` : ''}</blockquote>}
        </div>
      )}
      {(f.consultoria || f.agente_cobranca) && <div className="stack" style={{ gap: 4 }}>
        <b>Consultoria de crédito</b>
        <div>{f.consultoria ?? 'Consultoria não nomeada'}{f.consultoria_cnpj ? ` (${f.consultoria_cnpj})` : ''} · <b>{f.consultoria_tipo ?? '–'}</b>
          {f.consultoria_n_fundos ? ` · ${f.consultoria_n_fundos} FIDC(s) ativo(s)` : ''}
          {f.mono_consultoria_ligada && <> · <b style={{ color: 'var(--critical)' }}>{f.mono_consultoria_ligada}</b></>}</div>
        {f.agente_cobranca && <div className="muted">Agente de cobrança: {f.agente_cobranca}{f.mono_cobranca_ligada ? ` · ${f.mono_cobranca_ligada}` : ''}</div>}
        <div className="muted">Taxa: {f.consultoria_taxa_txt ?? 'não lida'}{f.consultoria_paga_por ? ` · paga por: ${String(f.consultoria_paga_por).replaceAll('_', ' ')}` : ''}
          {f.mono_consultoria_atividade ? ` · Receita: ${f.mono_consultoria_atividade}` : ''}
          {f.mono_consultoria_abertura ? ` · aberta em ${f.mono_consultoria_abertura}` : ''}</div>
      </div>}
      <div className="stack" style={{ gap: 4 }}>
        <b>Remuneração prometida (documentos do FNET)</b>
        <RemuneracaoPrometida cnpj={f.cnpj} />
      </div>
      <Loading q={g} />
      {g.data && <DataGrid title="Cedentes por grupo econômico" rows={g.data} id="mono-grupos" pinned={0}
        cols={['ordem', 'grupo', 'atividade', 'cnae', 'n_cnpjs', 'pct_carteira', 'pct_informados', 'cnpjs']} />}
    </div>
  )
}

export default function Monocedentes() {
  const [sp, setSp] = useSearchParams()
  const aba = (sp.get('aba') ?? 'bt') as Aba
  const sel = sp.get('fundo')
  const q = useApi<Row[]>('/api/monocedentes?todos=true')
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }

  const dados = q.data ?? []
  const universo = useMemo(() => dados.filter((r) => r.monocedente), [dados])
  const bt = useMemo(() => universo.filter((r) => r.bt_faixa === 'provável' || r.bt_faixa === 'possível'), [universo])
  const grandes = useMemo(() => universo.filter((r) => r.bt_faixa === 'excluído (grande empresa)'), [universo])
  const financ = useMemo(() => universo.filter((r) => ['excluído (cedente financeiro)', 'excluído (cedente público)', 'excluído (tipo de crédito)'].includes(r.bt_faixa)), [universo])
  const calib = useMemo(() => dados.filter((r) => r.bt_rotulo), [dados])
  const rem = useMemo(() => universo.filter((r) => !String(r.bt_faixa ?? '').startsWith('excluído')), [universo])
  const comMeta = rem.filter((r) => r.rem_senior_texto || r.rem_mez_texto)
  const linhas = aba === 'universo' ? dados : aba === 'calibracao' ? calib : aba === 'remuneracao' ? rem : bt
  const soma = (rs: Row[]) => rs.reduce((a, r) => a + (r.pl ?? 0), 0)
  const est = (n: number) => bt.filter((r) => r.bt_estagio === n).length
  const atual = dados.find((r) => r.cnpj === sel)
  const acertos = calib.filter((r) => (r.bt_rotulo === 'beneficio_tributario') === (!!r.monocedente && (r.bt_faixa === 'provável' || r.bt_faixa === 'possível'))).length

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Monocedentes e benefício tributário</h1>
          <div className="sub">
            Monocedente = o maior <b>grupo</b> de cedentes (CNPJs com mesma raiz, sócios em comum ou mesmo nome na Receita)
            soma ≥ 80% dos cedentes informados no informe CVM e ≥ 50% da carteira. Inclui fundos de outras categorias.
            O score de benefício tributário soma indícios — histórico só com subordinada e poucos cotistas, cotistas hoje,
            taxa de gestão, remuneração da sênior, concentração no grupo, nome do fundo no cedente, exclusividade —
            e cada fundo mostra os pontos que recebeu. É triagem, não conclusão: confirme no regulamento.
          </div>
        </div>
      </div>
      <Loading q={q} />
      {q.data && (
        <div className="kpis">
          <div className="kpi"><div className="l">Universo monocedente</div><div className="v">{universo.length}</div>
            <div className="c">{fmtValue(soma(universo), 'brl')}</div></div>
          <div className="kpi"><div className="l">Benefício tributário provável</div>
            <div className="v">{universo.filter((r) => r.bt_faixa === 'provável').length}</div>
            <div className="c">{fmtValue(soma(universo.filter((r) => r.bt_faixa === 'provável')), 'brl')}</div></div>
          <div className="kpi"><div className="l">Possível</div>
            <div className="v">{universo.filter((r) => r.bt_faixa === 'possível').length}</div>
            <div className="c">{fmtValue(soma(universo.filter((r) => r.bt_faixa === 'possível')), 'brl')}</div></div>
          <div className="kpi"><div className="l">Estágios (prov. + poss.)</div>
            <div className="v">{est(1)} · {est(2)} · {est(3)}</div><div className="c">1 só sub · 2 sênior+sub · 3 distribuído</div></div>
          <div className="kpi"><div className="l">Excluídos: financeiro, público e tipo de crédito</div><div className="v">{financ.length}</div>
            <div className="c">banco, SCD/bancarizadora, IP, securitizadora, meios de pagamento, ente público, consignado, MCMS, veículos</div></div>
          <div className="kpi"><div className="l">Excluídos: cedente grande empresa</div><div className="v">{grandes.length}</div>
            <div className="c">S.A. aberta ou capital ≥ R$ 1 bi (cativo, fornecedores...)</div></div>
          <div className="kpi"><div className="l">Remuneração prometida lida</div>
            <div className="v">{comMeta.length}/{rem.length}</div>
            <div className="c">com meta numérica · {rem.filter((r) => r.rem_lida).length} lidos</div></div>
          <div className="kpi"><div className="l">Calibração</div><div className="v">{acertos}/{calib.length}</div>
            <div className="c">exemplos do time classificados certo</div></div>
        </div>
      )}
      <Tabs value={aba} onChange={(a) => set('aba', a === 'bt' ? null : a)}
        options={[['bt', `Benefício tributário (${bt.length})`], ['remuneracao', `Prometido × entregue (${rem.length})`], ['universo', `Universo + categoria monocedente (${dados.length})`],
                  ['calibracao', `Calibração (${calib.length})`]]} />
      {q.data && (
        <div className="card">
          <DataGrid rows={linhas} id={`mono-${aba}`} height={600} visoes={VISOES} exportUrl="/api/monocedentes?todos=true"
            cols={(aba === 'remuneracao' ? COLS_REM : COLS).map((c) => c === 'nome' ? {
              field: 'nome', minWidth: 300, cellRenderer: (p: any) => (
                <span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                  <button className="ghost" style={{ padding: '0 6px', minHeight: 24, fontSize: 12 }} title="Ver sinais, leitura do regulamento e cedentes"
                    onClick={() => set('fundo', p.data.cnpj)}>sinais</button>
                  <Link to={`/fundo/${p.data.cnpj}`} title="Abrir o fundo">{p.value}</Link>
                </span>),
            } : c === 'bt_rotulo' ? {
              field: 'bt_rotulo', width: 120, valueFormatter: (p: any) =>
                p.value === 'beneficio_tributario' ? 'benefício' : p.value === 'nao_beneficio' ? 'não é' : '',
            } : c)} />
          {aba === 'calibracao' && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Exemplos passados pelo time. "Certo" = benefício tributário que é monocedente com faixa provável/possível, ou
            não-benefício fora disso. Na Oriz, só o MDR II é "não é" (fundo de recebíveis de cartão); Mundial e JPA Agro são benefício tributário.
            Em 15/10 entraram como "não é": Latache (indício de fraude), Moto Honda II (veículos), Alpe (MCMS), Nexus,
            Arcesp Consignado e TM4 (cedente instituição de pagamento).
          </div>}
        </div>
      )}
      {atual && <Detalhe f={atual} onFechar={() => set('fundo', null)} />}
    </div>
  )
}
