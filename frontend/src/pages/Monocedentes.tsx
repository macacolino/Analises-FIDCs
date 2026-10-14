import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi, type Row } from '../api'
import { DataGrid, type Visao } from '../components/DataGrid'
import { Loading, Tabs } from '../components/ui'
import { fmtValue } from '../fmt'

type Aba = 'bt' | 'universo' | 'calibracao'

const COLS = ['nome', 'bt_score', 'bt_faixa', 'bt_estagio', 'bt_meses_estagio1', 'mono_grupo', 'mono_conc_grupo',
  'mono_grupo_cnpjs', 'pl', 'nr_cotistas', 'estrutura', 'taxa_gestao', 'spread_senior_aa', 'rentab_subordinada_12m_pct_cdi',
  'bt_ia_sub', 'bt_ia_indicio', 'gestor', 'admin', 'categoria_nome', 'bt_rotulo', 'bt_sinais']
const VISOES: Visao[] = [
  { nome: 'Triagem', cols: ['bt_score', 'bt_faixa', 'bt_estagio', 'mono_grupo', 'pl', 'nr_cotistas', 'taxa_gestao', 'gestor', 'bt_sinais'] },
  { nome: 'Estrutura', cols: ['bt_estagio', 'bt_meses_estagio1', 'bt_inicio', 'estrutura', 'nr_cotistas', 'cotistas_senior',
    'cotistas_subordinada', 'subordinacao', 'pl'] },
  { nome: 'Economia', cols: ['bt_score', 'taxa_gestao', 'taxa_administracao', 'spread_senior_aa', 'rentab_subordinada_12m_pct_cdi',
    'taxa_desconto_aa', 'inad_90', 'pdd_carteira'] },
  { nome: 'Regulamento', cols: ['bt_score', 'bt_ia_sub', 'bt_ia_sub_nome', 'bt_ia_coobrigacao', 'bt_ia_indicio',
    'bt_ia_justificativa', 'bt_ia_cedente'] },
  { nome: 'Cedente', cols: ['mono_grupo', 'mono_grupo_cnpjs', 'mono_conc_grupo', 'mono_conc_carteira', 'mono_cedentes_informados',
    'bt_nome_cedente', 'categoria_nome'] },
]

function Detalhe({ f, onFechar }: { f: Row; onFechar: () => void }) {
  const g = useApi<Row[]>(`/api/monocedentes/grupos/${f.cnpj}`)
  return (
    <div className="card stack">
      <div className="row"><h2 style={{ margin: 0 }}><Link to={`/fundo/${f.cnpj}`}>{f.nome}</Link></h2><div className="spacer" />
        <button className="ghost" onClick={onFechar}>Fechar</button></div>
      <div className="muted">
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
      <Loading q={g} />
      {g.data && <DataGrid title="Cedentes por grupo econômico" rows={g.data} id="mono-grupos" pinned={0}
        cols={['ordem', 'grupo', 'n_cnpjs', 'pct_carteira', 'pct_informados', 'cnpjs']} />}
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
  const grandes = useMemo(() => universo.filter((r) => String(r.bt_faixa).startsWith('excluído')), [universo])
  const calib = useMemo(() => dados.filter((r) => r.bt_rotulo), [dados])
  const linhas = aba === 'universo' ? dados : aba === 'calibracao' ? calib : bt
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
          <div className="kpi"><div className="l">Excluídos: cedente grande empresa</div><div className="v">{grandes.length}</div>
            <div className="c">S.A. aberta ou capital ≥ R$ 1 bi (cativo, fornecedores...)</div></div>
          <div className="kpi"><div className="l">Calibração</div><div className="v">{acertos}/{calib.length}</div>
            <div className="c">exemplos do time classificados certo</div></div>
        </div>
      )}
      <Tabs value={aba} onChange={(a) => set('aba', a === 'bt' ? null : a)}
        options={[['bt', `Benefício tributário (${bt.length})`], ['universo', `Universo + categoria monocedente (${dados.length})`],
                  ['calibracao', `Calibração (${calib.length})`]]} />
      {q.data && (
        <div className="card">
          <DataGrid rows={linhas} id={`mono-${aba}`} height={600} visoes={VISOES} exportUrl="/api/monocedentes?todos=true"
            cols={COLS.map((c) => c === 'nome' ? {
              field: 'nome', minWidth: 300, cellRenderer: (p: any) => (
                <a href="#" onClick={(e) => { e.preventDefault(); set('fundo', p.data.cnpj) }} title="Ver sinais e cedentes">{p.value}</a>),
            } : c === 'bt_rotulo' ? {
              field: 'bt_rotulo', width: 120, valueFormatter: (p: any) =>
                p.value === 'beneficio_tributario' ? 'benefício' : p.value === 'nao_beneficio' ? 'não é' : '',
            } : c)} />
          {aba === 'calibracao' && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Exemplos passados pelo time. "Certo" = benefício tributário que é monocedente com faixa provável/possível, ou
            não-benefício fora disso. Os fundos da Oriz entraram todos como "não é" (gestora inteira) — confirmar os que pontuam alto.
          </div>}
        </div>
      )}
      {atual && <Detalhe f={atual} onFechar={() => set('fundo', null)} />}
    </div>
  )
}
