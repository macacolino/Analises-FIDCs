import { Fragment, useEffect, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { useApi, type Row } from '../api'
import { fmtCnpj, fmtDate, fmtValue, mesAno } from '../fmt'
import type { MensalResp } from './FundoTabs'
import './lamina.css'

/* Lâmina do fundo para impressão em A4 (Salvar como PDF no navegador). Identidade Ouribank: Poppins, navy + teal,
   vermelho só para alerta, sem linhas de grade nos gráficos. Só dados públicos (CVM, FNET, BCB). */

const C = { dark: '#15252D', dark2: '#23363D', teal: '#76D2D7', tealL: '#96DFE5', tealD: '#428087', muted: '#5B6E78',
  mutedL: '#A8B5BC', grid: '#DCE2E6', red: '#C25450', amber: '#C99A2E' }

type Extra = {
  parametros: { chave: string; label: string; fmt: string; valor_num: number | null; valor_txt: string | null; fonte: string; manual: boolean }[]
  segmentos: { segmento: string; pct: number }[]
  ia: Row | null
  regulamento: Row | null
}

const TESE: Record<string, string> = {
  consignado: 'Consignado', fgts: 'Antecipação FGTS', credito_pessoal: 'Crédito pessoal', cartao: 'Cartão',
  veiculos: 'Veículos', imobiliario: 'Imobiliário', agro: 'Agronegócio', precatorios: 'Precatórios',
  judicial: 'Ativos judiciais', setor_publico_outros: 'Setor público', multicedente_multissacado: 'Multicedente / multissacado',
  monocedente_comercial: 'Monocedente comercial', risco_sacado: 'Risco sacado', corporativo: 'Crédito corporativo',
  npl: 'NPL', fic_fidc: 'FIC de FIDC', outra: 'Outra',
}
const CONSIG: Record<string, string> = {
  inss: 'INSS', servidor_publico: 'servidor público', publico_misto: 'INSS e servidores', privado_clt: 'privado (CLT)',
  misto_publico_privado: 'público e privado',
}
const TIPO_COR: Record<string, string> = { senior: C.tealD, mezanino: C.tealL, subordinada: C.dark, cdi: C.mutedL }
const tick = { fontSize: 8, fill: C.muted, fontFamily: 'Poppins' }
const MARGEM = { top: 4, right: 4, bottom: 0, left: 0 }
/** rótulo do eixo Y encostado na margem esquerda do quadro (alinha com o título) */
const tickY = (f: (v: number) => string) => (pr: any) => (
  <text x={0} y={pr.y} dy={3} fontSize={8} fill={C.muted} fontFamily="Poppins" textAnchor="start">{f(pr.payload.value)}</text>)
const p = (v: any) => fmtValue(v, 'pct')
const p1 = (v: any) => (v == null || !Number.isFinite(v) ? '–' : `${(v * 100).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`)
const cdiMais = (v: any) => (v == null || !Number.isFinite(v) ? '–' : `CDI ${v >= 0 ? '+' : '−'} ${p1(Math.abs(v))}`)
const pAx = (v: number) => `${(v * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
const mi = (v: number) => `${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
const OUTROS = /outros/i
const ALT = 150   // altura única dos gráficos

/** eixo Y com 3 a 5 marcas redondas (passo 1, 2, 2,5 ou 5 × 10^k), começando em zero */
function eixo(rows: Row[], keys: string[], empilhado = false) {
  let max = 0
  for (const r of rows) {
    const vs = keys.map((k) => Number(r[k]) || 0)
    max = Math.max(max, empilhado ? vs.reduce((a, b) => a + Math.max(b, 0), 0) : Math.max(...vs))
  }
  if (max <= 0) return {}
  const bruto = max / 4, ex = Math.pow(10, Math.floor(Math.log10(bruto)))
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * ex).find((x) => x >= bruto) ?? 10 * ex
  const n = Math.max(1, Math.ceil(max / passo - 1e-9))
  const ticks = Array.from({ length: n + 1 }, (_, i) => +(i * passo).toPrecision(10))
  return { domain: [0, ticks[n]] as [number, number], ticks }
}

function Pagina({ n, total, dt, nome, children }: { n: number; total: number; dt: string; nome: string; children: React.ReactNode }) {
  return (
    <section className="lam-page">
      {n === 1 ? null : (
        <header className="lam-mini">
          <img src="/ouribank_teal_dark.png" alt="Ouribank" />
          <span>{nome}</span><span className="sp" /><span>Lâmina · data-base {mesAno(dt)}</span>
        </header>
      )}
      <div className="lam-body">{children}</div>
      <footer className="lam-foot">
        <span>Lâmina construída só com dados públicos: CVM (informe mensal e cadastro), FNET/B3 (regulamento) e BCB (CDI).
          Pode diferir do material do gestor. Dados declarados pelo administrador, sem auditoria. Uso interno Ouribank.</span>
        <span className="pg">{String(n).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
      </footer>
    </section>
  )
}

function Kpi({ v, label, hint, alerta }: { v: string; label: string; hint?: React.ReactNode; alerta?: boolean }) {
  return (
    <div className={`lam-kpi${alerta ? ' alerta' : ''}`}>
      <div className="v">{v}</div>
      <div className="l">{label}</div>
      <div className="h">{hint ?? ' '}</div>
    </div>
  )
}

function Bloco({ titulo, children, className }: { titulo: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`lam-bloco ${className ?? ''}`}>
      <h3><i />{titulo}</h3>
      {children}
    </div>
  )
}

function Legenda({ itens }: { itens: [string, string, boolean?][] }) {
  return <div className="leg">{itens.map(([cor, txt, tracejado]) => (
    <span key={txt}><i className={tracejado ? 'tr' : ''} style={tracejado ? { borderColor: cor } : { background: cor }} />{txt}</span>))}</div>
}

export default function LaminaPdf() {
  const { cnpj = '' } = useParams()
  const [sp] = useSearchParams()
  const lam = useApi<any>(`/api/fundos/${cnpj}`)
  const hist = useApi<Row[]>(`/api/fundos/${cnpj}/historico?meses=24`)
  const men = useApi<MensalResp>(`/api/fundos/${cnpj}/mensal?meses=24`)
  const comp = useApi<any>(`/api/comparar/${cnpj}?modo=categoria&ignorar_sem_vencido=true`)
  const ext = useApi<Extra>(`/api/fundos/${cnpj}/lamina-extra`)
  // medianas dos pares no tempo: mesma base do quadro de pares (categoria, sem dado com erro e, para atraso,
  // sem os fundos que declaram zero vencido)
  const sOver = useApi<Row[]>(`/api/comparar/${cnpj}/serie?metrica=over90_carteira&meses=24`)
  const sPdd = useApi<Row[]>(`/api/comparar/${cnpj}/serie?metrica=pdd_carteira&meses=24`)
  const pronto = !!(lam.data && hist.data && men.data && comp.data && ext.data && sOver.data && sPdd.data)
  const erro = lam.error || hist.error || men.error || comp.error || ext.error || sOver.error || sPdd.error

  useEffect(() => {
    if (!lam.data) return
    const h = lam.data.cabecalho
    const curto = String(h.nome).split(/ FUNDO| FIDC| -/i)[0].trim()
    document.title = `Lamina ${curto} ${mesAno(h.ultimo_informe).replace('/', '-')}`
  }, [lam.data])
  useEffect(() => {
    if (pronto && sp.get('print') === '1') {
      const t = setTimeout(() => window.print(), 1500)
      return () => clearTimeout(t)
    }
  }, [pronto, sp])

  const d = useMemo(() => (pronto ? montar(lam.data, hist.data!, men.data!, comp.data, ext.data!, sOver.data!, sPdd.data!) : null),
    [pronto, lam.data, hist.data, men.data, comp.data, ext.data, sOver.data, sPdd.data])

  if (erro) return <div className="lam-wait">Não foi possível carregar os dados do fundo.</div>
  if (!d) return <div className="lam-wait">Montando a lâmina…</div>
  const { h, k, dt } = d
  const total = 3
  const nomeCurto = String(h.nome).replace(/FUNDO DE INVESTIMENTO EM DIREITOS CREDIT[ÓO]RIOS/i, 'FIDC')
    .replace(/ ?-? ?RESPONSABILIDADE LIMITADA/i, '').replace(/ DE RESP(\.|ONSABILIDADE)? LIMITADA/i, '').trim()
  const nota12 = d.notaResidual ? '*' : ''

  return (
    <div className="lam">
      <div className="lam-toolbar">
        <button onClick={() => window.print()}>Salvar como PDF</button>
        <span>No diálogo de impressão: destino "Salvar como PDF", papel A4, margens "Nenhuma", com "Gráficos de plano de fundo" marcado.</span>
      </div>

      {/* ------------------------------------------------ página 1: visão geral */}
      <Pagina n={1} total={total} dt={dt} nome={nomeCurto}>
        <div className="lam-capa">
          <div>
            <img src="/ouribank_white.png" alt="Ouribank" className="logo" />
            <div className="kick">LÂMINA DE FIDC · DATA-BASE {mesAno(dt)}</div>
            <h1>{nomeCurto}</h1>
            <div className="sub">CNPJ {fmtCnpj(h.cnpj)} · {h.categoria_nome} · gestão {h.gestor ?? '–'}</div>
          </div>
          <div className="arc a1" /><div className="arc a2" /><div className="dotc" />
        </div>

        <div className="lam-kpis">
          <Kpi v={fmtValue(k.pl, 'brl')} label="Patrimônio líquido" hint={d.plVar12 != null ? <>{d.plVar12 >= 0 ? '+' : ''}{p1(d.plVar12)} em 12 meses</> : undefined} />
          <Kpi v={p1(k.subordinacao)} label="Subordinação (Mz + Jr) / PL"
            hint={d.par.sub_min_senior?.valor_num != null ? <>mínimo do regulamento {p1(d.par.sub_min_senior.valor_num)}</> : 'mínimo não localizado no regulamento'}
            alerta={d.par.sub_min_senior?.valor_num != null && k.subordinacao < d.par.sub_min_senior.valor_num} />
          <Kpi v={p1(k.subordinacao_junior)} label="Subordinada júnior / PL"
            hint={d.par.jr_min_pl?.valor_num != null ? <>mínimo do regulamento {p1(d.par.jr_min_pl.valor_num)}</> : 'mínimo não localizado no regulamento'}
            alerta={d.par.jr_min_pl?.valor_num != null && k.subordinacao_junior < d.par.jr_min_pl.valor_num} />
          <Kpi v={p(k.inad_90)} label="Inadimplência > 90 dias (Over 90)" hint={d.med.inad_90 != null ? <>mediana da categoria {p(d.med.inad_90)}</> : undefined} />
          <Kpi v={p(k.pdd_carteira)} label="PDD / carteira" hint={d.med.pdd_carteira != null ? <>mediana da categoria {p(d.med.pdd_carteira)}</> : undefined} />
          <Kpi v={fmtValue(k.cobertura_pdd_90, 'x')} label="PDD / vencido > 90 dias" hint={d.med.cobertura_pdd_90 != null ? <>mediana da categoria {fmtValue(d.med.cobertura_pdd_90, 'x')}</> : undefined} />
          <Kpi v={d.senior12 ? p1(d.senior12.cota_12m) : '–'} label="Sênior · retorno 12 meses"
            hint={d.senior12 ? <>{cdiMais(d.senior12.spread_aa_12m)} a.a. · {p1(d.senior12.pct_cdi_12m)} do CDI</> : 'série sem 12 meses de histórico'} />
          <Kpi v={d.sub12 ? `${p1(d.sub12.cota_12m)}${nota12}` : '–'} label="Subordinada · retorno 12 meses"
            hint={d.sub12 ? <>{cdiMais(d.sub12.spread_aa_12m)} a.a. · {p1(d.sub12.pct_cdi_12m)} do CDI</> : 'série sem 12 meses de histórico'}
            alerta={d.sub12 && d.sub12.cota_12m < 0} />
        </div>
        {d.notaResidual && <div className="lam-aviso">* {d.notaResidual}</div>}

        <div className="lam-cols">
          <div>
            <Bloco titulo="Características">
              <table className="lam-ficha"><tbody>
                {d.ficha.map(([a, b]) => <tr key={a}><th>{a}</th><td>{b ?? '–'}</td></tr>)}
              </tbody></table>
            </Bloco>
            <Bloco titulo="Regulamento">
              <table className="lam-ficha"><tbody>
                {d.parLinhas.map((x) => <tr key={x.label}><th>{x.label}</th><td>{x.valor}{x.fonte && <span className="fonte">{x.fonte}</span>}</td></tr>)}
              </tbody></table>
              {d.regData && <div className="nota">Regulamento vigente no FNET, entregue em {d.regData}. "–" = não localizado na leitura automática.</div>}
            </Bloco>
          </div>
          <div>
            <Bloco titulo="Tese e lastro">
              {d.ia ? (
                <>
                  <div className="tese">{d.teseTitulo}</div>
                  <p>{d.lastro}</p>
                </>
              ) : <p className="nota">Regulamento ainda não lido.</p>}
            </Bloco>
            <Bloco titulo="Posição vs. pares">
              <p className="resumo">{d.paresResumo.frase}</p>
              {d.paresResumo.pos && <p className="dest dest-pos"><b>Pontos fortes:</b> {d.paresResumo.pos}</p>}
              {d.paresResumo.neg && <p className="dest dest-neg"><b>Pontos de atenção:</b> {d.paresResumo.neg}</p>}
            </Bloco>
            <Bloco titulo="Red flags">
              {d.rfAlerta.length === 0 && <p className="ok">Nenhuma red flag em amarelo ou vermelho na data-base.</p>}
              {d.rfAlerta.map((f) => (
                <div key={f.id} className={`rf ${f.nivel >= 2 ? 'vermelho' : 'amarelo'}`}>
                  <div className="rf-h"><span className="chip">{f.nivel >= 2 ? 'Vermelho' : 'Amarelo'}</span><b>{f.nome}</b></div>
                  <div className="rf-d">{cap(f.detalhe)}</div>
                  <div className="rf-r">{f.regra}</div>
                </div>
              ))}
            </Bloco>
          </div>
        </div>
      </Pagina>

      {/* ------------------------------------------------ página 2: rentabilidade */}
      <Pagina n={2} total={total} dt={dt} nome={nomeCurto}>
        <h2 className="lam-titulo">Rentabilidade por classe de cota vs. CDI</h2>
        <div className="lam-cols">
          <Bloco titulo="Retorno acumulado em 24 meses" className="graf">
            {d.acum.length > 1 ? (
              <>
                <ResponsiveContainer width="100%" height={ALT + 70}>
                  <LineChart data={d.acum} margin={MARGEM}>
                    <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={28} height={18} />
                    <YAxis tickFormatter={pAx} tick={tickY(pAx)} tickLine={false} axisLine={false} width={34} {...eixo(d.acum, d.tiposAcum)} />
                    {d.tiposAcum.map((t) => <Line key={t} dataKey={t} stroke={TIPO_COR[t]} strokeWidth={t === 'cdi' ? 1.4 : 2}
                      strokeDasharray={t === 'cdi' ? '4 3' : undefined} dot={false} isAnimationActive={false} connectNulls />)}
                  </LineChart>
                </ResponsiveContainer>
                <Legenda itens={d.tiposAcum.map((t) => [TIPO_COR[t], d.rotAcum[t], t === 'cdi'])} />
              </>
            ) : <p className="nota">Histórico insuficiente.</p>}
          </Bloco>
          <Bloco titulo="Rentabilidade acumulada por série">
            <table className="lam-tab janelas mensal">
              <colgroup><col className="c-serie" /><col className="c-tipo" /><col /><col /><col /><col /></colgroup>
              <thead><tr><th>Série</th><th /><th className="r">3 meses</th><th className="r">6 meses</th><th className="r">12 meses</th><th className="r">Início</th></tr></thead>
              <tbody>{d.janelas.map((j) => (
                <Fragment key={j.serie}>
                  <tr className="cota"><td rowSpan={3}>{j.rotulo}{j.meses_residual ? '*' : ''}</td><td className="muted">cota</td>
                    {['3m', '6m', '12m', 'inicio'].map((x) => <td key={x} className="r">{p(j[`cota_${x}`])}</td>)}</tr>
                  <tr><td className="muted">% CDI</td>
                    {['3m', '6m', '12m', 'inicio'].map((x) => <td key={x} className="r muted">{p1(j[`pct_cdi_${x}`])}</td>)}</tr>
                  <tr className="ult"><td className="muted">CDI +</td>
                    {['3m', '6m', '12m', 'inicio'].map((x) => <td key={x} className="r muted">{p1(j[`spread_aa_${x}`])}</td>)}</tr>
                </Fragment>))}</tbody>
            </table>
            <div className="nota">CDI + = spread anualizado sobre o CDI. Início = 1º mês da série no informe.</div>
          </Bloco>
        </div>
        <Bloco titulo="Retorno mensal vs. CDI · últimos 12 meses">
          <table className="lam-tab mensal">
            <colgroup><col className="c-serie" /><col className="c-tipo" />{d.ult12.map((m) => <col key={m.dt} />)}<col className="c-12m" /></colgroup>
            <thead><tr><th>Série</th><th />{d.ult12.map((m) => <th key={m.dt} className="r">{mesAno(m.dt).replace('/20', '/')}</th>)}<th className="r tot12">12M</th></tr></thead>
            <tbody>
              {d.seriesAtivas.map((s) => {
                const j = d.porSerie[s.serie]
                return (
                  <Fragment key={s.key}>
                    <tr className="cota"><td rowSpan={3}>{s.rotulo}{j?.meses_residual ? '*' : ''}</td><td className="muted">cota</td>
                      {d.ult12.map((m) => <td key={m.dt} className={`r${(m[`${s.key}_rentab`] ?? 0) < 0 ? ' neg' : ''}`}>{p(m[`${s.key}_rentab`])}</td>)}
                      <td className="r tot12">{p(j?.cota_12m)}</td></tr>
                    <tr><td className="muted">% CDI</td>
                      {d.ult12.map((m) => <td key={m.dt} className="r muted">{p1(m[`${s.key}_pct_cdi`])}</td>)}
                      <td className="r tot12 muted">{p1(j?.pct_cdi_12m)}</td></tr>
                    <tr className="ult"><td className="muted">CDI +</td>
                      {d.ult12.map((m) => <td key={m.dt} className="r muted">{p1(m[`${s.key}_spread_aa`])}</td>)}
                      <td className="r tot12 muted">{p1(j?.spread_aa_12m)}</td></tr>
                  </Fragment>
                )
              })}
              <tr className="cdi"><td>CDI</td><td />{d.ult12.map((m) => <td key={m.dt} className="r">{p(m.cdi_mes)}</td>)}
                <td className="r tot12">{p(d.cdi12)}</td></tr>
            </tbody>
          </table>
        </Bloco>
        <div className="lam-cols">
          <Bloco titulo="Patrimônio por classe de cota (R$ mi)" className="graf">
            <ResponsiveContainer width="100%" height={ALT}>
              <AreaChart data={d.plTipo} margin={MARGEM}>
                <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={28} height={18} />
                <YAxis tickFormatter={mi} tick={tickY(mi)} tickLine={false} axisLine={false} width={34} {...eixo(d.plTipo, ['pl_senior', 'pl_mezanino', 'pl_subordinada'], true)} />
                <Area dataKey="pl_subordinada" stackId="1" stroke="none" fill={C.dark} fillOpacity={1} isAnimationActive={false} />
                <Area dataKey="pl_mezanino" stackId="1" stroke="none" fill={C.tealL} fillOpacity={1} isAnimationActive={false} />
                <Area dataKey="pl_senior" stackId="1" stroke="none" fill={C.tealD} fillOpacity={1} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
            <Legenda itens={[[C.tealD, 'Sênior'], [C.tealL, 'Mezanino'], [C.dark, 'Subordinada']]} />
          </Bloco>
          <Bloco titulo="Subordinação vs. mínimo do regulamento" className="graf">
            <ResponsiveContainer width="100%" height={ALT}>
              <LineChart data={d.histo} margin={MARGEM}>
                <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={28} height={18} />
                <YAxis tickFormatter={pAx} tick={tickY(pAx)} tickLine={false} axisLine={false} width={34} {...eixo(d.histo, ['subordinacao', 'setor_subordinacao', 'sub_min'])} />
                <Line dataKey="subordinacao" stroke={C.tealD} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line dataKey="setor_subordinacao" stroke={C.mutedL} strokeWidth={1.4} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                {d.subMin != null && <Line dataKey="sub_min" stroke={C.red} strokeWidth={1.2} dot={false} isAnimationActive={false} />}
              </LineChart>
            </ResponsiveContainer>
            <Legenda itens={[[C.tealD, 'Fundo'], [C.mutedL, 'Mediana categoria', true],
              ...(d.subMin != null ? [[C.red, 'Mínimo do regulamento'] as [string, string]] : [])]} />
          </Bloco>
        </div>
      </Pagina>

      {/* ------------------------------------------------ página 3: estrutura, carteira e pares */}
      <Pagina n={3} total={total} dt={dt} nome={nomeCurto}>
        <h2 className="lam-titulo">Estrutura, carteira e posição vs. pares</h2>
        <Bloco titulo="Estrutura de cotas na data-base">
          <table className="lam-tab">
            <thead><tr><th>Série</th><th>Tipo</th><th className="r">PL</th><th className="r">% do PL</th><th className="r">Valor da cota</th>
              <th className="r">Retorno 12m</th><th className="r">CDI + (12m)</th><th className="r">Cotistas</th></tr></thead>
            <tbody>{d.estrutura.map((s) => (
              <tr key={s.serie}><td>{s.rotulo ?? s.serie}</td><td>{s.tipo}</td><td className="r">{fmtValue(s.pl_serie, 'brl')}</td>
                <td className="r">{p(s.pct_pl)}</td><td className="r">{fmtValue(s.valor_cota, 'num')}</td>
                <td className="r">{p(s.r12)}</td><td className="r">{p1(s.s12)}</td><td className="r">{fmtValue(s.nr_cotistas, 'int')}</td></tr>))}
              <tr className="tot"><td>Total</td><td /><td className="r">{fmtValue(d.plSeries, 'brl')}</td><td className="r">100,00%</td><td colSpan={4} /></tr>
            </tbody>
          </table>
        </Bloco>
        <div className="lam-cols">
          <Bloco titulo="Inadimplência > 90 dias (Over 90) e PDD" className="graf">
            <ResponsiveContainer width="100%" height={ALT}>
              <LineChart data={d.histo} margin={MARGEM}>
                <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={28} height={18} />
                <YAxis tickFormatter={pAx} tick={tickY(pAx)} tickLine={false} axisLine={false} width={34} {...eixo(d.histo, ['inad_90', 'pdd_carteira', 'med_over90', 'med_pdd'])} />
                <Line dataKey="inad_90" stroke={C.red} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line dataKey="pdd_carteira" stroke={C.tealD} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line dataKey="med_over90" stroke={C.red} strokeOpacity={0.55} strokeWidth={1.3} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                <Line dataKey="med_pdd" stroke={C.tealD} strokeOpacity={0.55} strokeWidth={1.3} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
            <Legenda itens={[[C.red, 'Over 90 / carteira'], [C.tealD, 'PDD / carteira'], [C.red, 'Over 90 · mediana', true], [C.tealD, 'PDD · mediana', true]]} />
          </Bloco>
          <Bloco titulo="Carteira por prazo e por atraso (R$ mi)" className="graf">
            <ResponsiveContainer width="100%" height={ALT}>
              <BarChart data={d.aging} margin={MARGEM} barGap={1}>
                <XAxis dataKey="faixa" tick={{ ...tick, fontSize: 6.8 }} tickLine={false} axisLine={{ stroke: C.grid }} interval={0} height={18} />
                <YAxis tickFormatter={mi} tick={tickY(mi)} tickLine={false} axisLine={false} width={34} {...eixo(d.aging, ['a_vencer', 'vencido'])} />
                <Bar dataKey="a_vencer" fill={C.tealD} isAnimationActive={false} />
                <Bar dataKey="vencido" fill={C.red} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
            <Legenda itens={[[C.tealD, 'A vencer (dias até vencer)'], [C.red, 'Vencido (dias de atraso)']]} />
          </Bloco>
        </div>
        <div className="lam-cols">
          <Bloco titulo={`Posição vs. pares · ${d.paresDesc}`}>
            <table className="lam-tab pares">
              <thead><tr><th>Indicador</th><th className="r">Fundo</th><th className="r">Mediana</th><th className="r">P25 – P75</th><th /></tr></thead>
              <tbody>{d.pares.map((m) => (
                <tr key={m.metrica} title={m.definicao}><td>{m.label}</td><td className="r b">{fmtValue(m.valor, m.fmt)}</td>
                  <td className="r">{fmtValue(m.mediana, m.fmt)}</td><td className="r muted">{fmtValue(m.p25, m.fmt)} – {fmtValue(m.p75, m.fmt)}</td>
                  <td><span className={`pos ${m.posicao}`} /></td></tr>))}</tbody>
            </table>
            <div className="nota"><span className="pos favoravel" /> favorável · <span className="pos neutro" /> neutro · <span className="pos desfavoravel" /> desfavorável (quartis da categoria).</div>
          </Bloco>
          <div>
            <Bloco titulo="O que chamou atenção no mês">
              {d.alertas.length ? <ul className="alertas">{d.alertas.map((a, i) => <li key={i} className={a.sev}>{a.texto}</li>)}</ul>
                : <p className="ok">Nenhum alerta automático no mês.</p>}
            </Bloco>
            <Bloco titulo="Maiores cedentes (Tab. I)">
              {d.cedentes.length ? (
                <table className="lam-tab">
                  <thead><tr><th>#</th><th>CPF/CNPJ</th><th className="r">% carteira</th></tr></thead>
                  <tbody>{d.cedentes.map((c: Row) => <tr key={c.rank}><td>{c.rank}</td>
                    <td>{c.cedente_doc?.length === 14 ? fmtCnpj(c.cedente_doc) : c.cedente_doc}</td><td className="r">{fmtValue(c.pct, 'pct100')}</td></tr>)}</tbody>
                </table>
              ) : <p className="nota">O fundo não informou cedentes no informe.</p>}
            </Bloco>
            <Bloco titulo="Captações e saídas · últimos 12 meses (R$ mi)" className="graf">
              <ResponsiveContainer width="100%" height={ALT - 10}>
                <BarChart data={d.fluxo} margin={MARGEM} barGap={1}>
                  <XAxis dataKey="dt" tickFormatter={(v) => mesAno(v).replace('/20', '/')} tick={{ ...tick, fontSize: 6.8 }} tickLine={false}
                    axisLine={{ stroke: C.grid }} interval={0} height={18} />
                  <YAxis tickFormatter={mi} tick={tickY(mi)} tickLine={false} axisLine={false} width={34} {...eixo(d.fluxo, ['captacoes', 'saidas'])} />
                  <Bar dataKey="captacoes" fill={C.tealD} isAnimationActive={false} />
                  <Bar dataKey="saidas" fill={C.dark} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
              <Legenda itens={[[C.tealD, 'Captações (todas as classes)'], [C.dark, 'Amortizações + resgates']]} />
            </Bloco>
            {d.segs.length > 0 && (
              <Bloco titulo="Carteira por segmento (Tab. II)">
                <div className="segs">{d.segs.slice(0, 6).map((sg) => (
                  <div key={sg.segmento} className="seg"><span>{sg.segmento}</span>
                    <div className="bar"><i style={{ width: `${Math.max(2, sg.pct * 100)}%` }} /></div><b>{p1(sg.pct)}</b></div>))}</div>
              </Bloco>
            )}
          </div>
        </div>
      </Pagina>
    </div>
  )
}

/* ---------------------------------------------------------------- dados */
const SEG: Record<string, string> = {
  A: 'Industrial', B: 'Imobiliário', C1: 'Comercial', C2: 'Varejo', C3: 'Arrendamento', D1: 'Serviços',
  D2: 'Serviços públicos', D3: 'Educação', D4: 'Entretenimento', E: 'Agronegócio', F1: 'Crédito pessoal',
  F2: 'Consignado', F3: 'Corporativo', F4: 'Middle market', F5: 'Veículos', F6: 'Imob. empresarial',
  F7: 'Imob. residencial', F8: 'Financeiro - outros', G: 'Cartão de crédito', H1: 'Factoring PF',
  H2: 'Factoring PJ', I1: 'Precatórios', I2: 'Tributário', I3: 'Royalties', I4: 'Setor público - outros',
  J: 'Ações judiciais', K: 'Marcas/PI',
}
const PAR_ORDEM: [string, string][] = [
  ['taxa_administracao', 'Taxa de administração'], ['taxa_gestao', 'Taxa de gestão'], ['taxa_performance', 'Taxa de performance'],
  ['sub_min_senior', 'Subordinação mínima (sênior)'], ['mz_min_pl', 'Mezanino mínimo / PL'], ['jr_min_pl', 'Júnior mínima / PL'],
  ['benchmark_senior', 'Benchmark da sênior'], ['taxa_minima_cessao', 'Taxa mínima de cessão'],
  ['limite_maior_cedente', 'Limite por cedente'], ['limite_maior_sacado', 'Limite por sacado'],
  ['prazo_resgate_dias', 'Prazo de resgate'], ['responsabilidade_limitada', 'Responsabilidade limitada'],
]
const BLOCOS = ['Colchão e estrutura', 'Perdas e carteira', 'Retorno e spread', 'Concentração e lastro', 'Operação e liquidez']
const cap = (t: string) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t)

/** remove o óbvio ("adquiridos de cedentes") da frase de lastro lida no regulamento */
function limparLastro(t: string) {
  return String(t ?? '')
    .replace(/,?\s*(adquirid|cedid|originad)[oa]s?\s+(de|por|junto a|pel[oa]s?)\s+(seus\s+|diversos\s+|terceiros\s+|um\s+ou\s+mais\s+)?cedentes?(\s+elegíveis)?/gi, '')
    .replace(/\s+([;.,])/g, '$1').replace(/,\s*;/g, ';').trim()
}

/** resumo do quadro de pares (mesmos indicadores e marcações verde/vermelho da página 3) */
function resumoPares(ms: Row[], nPares?: number) {
  const fav = ms.filter((m) => m.posicao === 'favoravel'), desf = ms.filter((m) => m.posicao === 'desfavoravel')
  const saldo = fav.length - desf.length
  const perfil = saldo >= 3 ? 'melhor que a categoria' : saldo <= -3 ? 'pior que a categoria' : 'em linha com a categoria'
  const desc = (m: Row) => `${m.label}: ${fmtValue(m.valor, m.fmt)} (mediana ${fmtValue(m.mediana, m.fmt)})`
  const n = (x: number, um: string, varios: string) => `${x} ${x === 1 ? um : varios}`
  return {
    frase: `Perfil ${perfil}. Nos ${ms.length} indicadores do quadro de pares (página 3), comparado a ${nPares ?? 'outros'} ` +
      `fundos da categoria, o fundo está entre os 25% melhores em ${n(fav.length, 'indicador', 'indicadores')} e entre os ` +
      `25% piores em ${n(desf.length, 'indicador', 'indicadores')}; nos demais, fica perto da mediana.`,
    pos: fav.length ? fav.map(desc).join('; ') + '.' : null,
    neg: desf.length ? desf.map(desc).join('; ') + '.' : null,
  }
}

function montar(lam: any, hist: Row[], men: MensalResp, comp: any, ext: Extra, sOver: Row[], sPdd: Row[]) {
  const h = lam.cabecalho, k = lam.kpis, dt = k.dt ?? h.ultimo_informe
  const par = Object.fromEntries(ext.parametros.map((x) => [x.chave, x]))
  const parLinhas = PAR_ORDEM.map(([kk, label]) => {
    const x = par[kk]
    let valor = '–'
    if (x) {
      if (x.valor_num != null) valor = kk === 'prazo_resgate_dias' ? `${x.valor_num} dias` : fmtValue(x.valor_num, x.fmt === 'pct' ? 'pct' : x.fmt)
      const pct = x.valor_num != null ? fmtValue(x.valor_num, 'pct').replace(/,?0+%$/, '').replace(/,$/, '') : ''
      if (x.valor_txt && x.valor_txt.length > 1) {
        // o texto lido já costuma trazer o número ("0,18% a.a. sobre o PL..."): não repete
        valor = x.valor_num != null && !x.valor_txt.includes(pct) ? `${valor} · ${x.valor_txt}` : cap(x.valor_txt)
      }
      else if (x.valor_txt === 'S') valor = 'Sim'
      else if (x.valor_txt === 'N') valor = kk === 'responsabilidade_limitada' ? 'Não' : 'Não há'
    }
    const fonte = x ? (x.manual ? 'informado pela equipe' : (x.fonte ?? '').replace('regulamento ', '').replace(/[()]/g, '')) : ''
    return { label, valor: valor.length > 90 ? valor.slice(0, 88) + '…' : valor, fonte }
  })

  // séries mensais: começa no 1º mês com estrutura sênior + subordinada (o 1º mês costuma ter só a subordinada)
  const hs0 = [...hist].sort((a, b) => String(a.dt).localeCompare(String(b.dt)))
  const meses = [...men.meses].sort((a, b) => String(a.dt).localeCompare(String(b.dt)))
  const mPorDt = Object.fromEntries(meses.map((m) => [String(m.dt), m]))
  const i0 = Math.max(0, hs0.findIndex((r) => (mPorDt[String(r.dt)]?.pl_senior ?? 0) > 0 && r.subordinacao != null && r.subordinacao < 0.95))
  const hs = hs0.slice(i0)
  const base12 = hs0.length && String(hs0[0].dt) <= addMeses(dt, -12) ? lastBefore(hs0, addMeses(dt, -12)) : null
  const plVar12 = base12?.pl ? k.pl / base12.pl - 1 : null
  const subMin = par.sub_min_senior?.valor_num ?? null
  const medOver = Object.fromEntries(sOver.map((r) => [String(r.dt), r.mediana]))
  const medPdd = Object.fromEntries(sPdd.map((r) => [String(r.dt), r.mediana]))
  const histo = hs.map((r) => ({ ...r, sub_min: subMin, med_over90: medOver[String(r.dt)] ?? null, med_pdd: medPdd[String(r.dt)] ?? null }))
  const plTipo = hs.map((r) => {
    const m = mPorDt[String(r.dt)]
    return { dt: r.dt, pl_senior: m?.pl_senior ?? null, pl_mezanino: m?.pl_mezanino ?? null, pl_subordinada: m?.pl_subordinada ?? null }
  })
  // medianas dos cards = as do quadro de pares (página 3)
  const mp = Object.fromEntries((comp.metricas as Row[]).map((m) => [m.metrica, m.mediana]))
  const med = { inad_90: mp.over90_carteira, pdd_carteira: mp.pdd_carteira, cobertura_pdd_90: mp.pdd_over90 }
  const fluxo = men.meses.slice(0, 12).reverse().map((m) => ({
    dt: m.dt, captacoes: m.captacoes ?? 0, saidas: (m.amortizacoes ?? 0) + (m.resgates ?? 0) }))

  // rentabilidade: série principal (maior PL) de cada tipo, encadeada
  const ult = men.meses[0] ?? {}
  const principal: Record<string, { key: string; rotulo: string; serie: string }> = {}
  for (const s of men.series) {
    const pl = ult[`${s.key}_pl`] ?? 0
    const atual = principal[s.tipo]
    if (pl > 0 && (!atual || pl > (ult[`${atual.key}_pl`] ?? 0))) principal[s.tipo] = { key: s.key, rotulo: s.rotulo, serie: s.serie }
  }
  const tiposAcum = [...['senior', 'mezanino', 'subordinada'].filter((t) => principal[t]), 'cdi']
  const rotAcum: Record<string, string> = { cdi: 'CDI' }
  for (const t of tiposAcum) if (principal[t]) rotAcum[t] = principal[t].rotulo
  const acc: Record<string, number | null> = {}
  const mesesAcum = meses.filter((m) => String(m.dt) >= String(hs[0]?.dt ?? ''))
  const acum = mesesAcum.map((m) => {
    const o: Row = { dt: m.dt }
    for (const t of tiposAcum) {
      const r = t === 'cdi' ? m.cdi_mes : m[`${principal[t].key}_rentab`]
      if (r == null) { o[t] = acc[t] ?? null; continue }
      acc[t] = (1 + (acc[t] ?? 0)) * (1 + r) - 1
      o[t] = acc[t]
    }
    return o
  })
  const porSerie = Object.fromEntries(men.janelas.map((j) => [j.serie, j]))
  const ativa = (serie: string) => (ult[`${men.series.find((s) => s.serie === serie)?.key}_pl`] ?? 0) > 0
  const janelas = men.janelas.filter((j) => (j.cota_3m != null || j.cota_inicio != null) && ativa(j.serie))
  const senior12 = principal.senior ? porSerie[principal.senior.serie] : null
  const sub12 = principal.subordinada ? porSerie[principal.subordinada.serie] : null
  const ult12 = men.meses.slice(0, 12).reverse()
  const cdi12 = ult12.length === 12 ? ult12.reduce((a, m) => a * (1 + (m.cdi_mes ?? 0)), 1) - 1 : null
  const seriesAtivas = men.series.filter((s) => (ult[`${s.key}_pl`] ?? 0) > 0)
  const residuais = men.meses.filter((m) => m.sub_residual).map((m) => mesAno(m.dt))
  const notaResidual = residuais.length
    ? `Subordinada recalculada como PL − sênior − mezanino em ${residuais.slice(0, 4).join(', ')}: nesses meses a soma das séries ` +
      'informadas não fecha com o PL do fundo. Retorno da subordinada nesses meses é estimativa.'
    : null

  const plSeries = (lam.series as Row[]).reduce((a, s) => a + (s.tipo === 'subordinada' && (ult.sub_residual) ? 0 : (s.pl_serie ?? 0)), 0)
    + (ult.sub_residual ? (ult.pl_subordinada ?? 0) : 0)
  const rotPorSerie = Object.fromEntries(men.series.map((s) => [s.serie, s.rotulo]))
  const estrutura: Row[] = (lam.series as Row[]).filter((s) => (s.pl_serie ?? 0) > 0).map((s) => {
    const pl = s.tipo === 'subordinada' && ult.sub_residual ? ult.pl_subordinada : s.pl_serie
    return {
      ...s, pl_serie: pl, rotulo: rotPorSerie[s.serie], pct_pl: plSeries ? pl / plSeries : null,
      tipo: ({ senior: 'Sênior', mezanino: 'Mezanino', subordinada: 'Subordinada' } as Record<string, string>)[s.tipo] ?? s.tipo,
      r12: porSerie[s.serie]?.cota_12m, s12: porSerie[s.serie]?.spread_aa_12m,
    }
  })

  const rfAlerta = (comp.red_flags as Row[]).filter((f) => f.nivel > 0).sort((a, b) => b.nivel - a.nivel)
  const pares = (comp.metricas as Row[]).filter((m) => m.valor != null && m.mediana != null)
    .sort((a, b) => BLOCOS.indexOf(a.bloco) - BLOCOS.indexOf(b.bloco)).slice(0, 14)

  // alertas: frase do backend; a "sênior negativa" que some com o ajuste de amortização vira explicação
  const sr = principal.senior ? ult[`${principal.senior.key}_rentab`] : null
  const alertas = (lam.alertas as Row[]).map((a) => {
    if (a.id === 'rentab_senior_neg' && sr != null && sr > 0) {
      return { sev: 'info', texto: `A rentabilidade da sênior informada à CVM saiu negativa no mês por causa da amortização; ` +
        `ajustada pela amortização, a ${principal.senior.rotulo} rendeu ${p(sr)} (${p1(ult[`${principal.senior.key}_pct_cdi`])} do CDI).` }
    }
    if (a.id === 'inad_vs_setor' && med.inad_90) {   // mesma mediana do quadro de pares
      const x = k.inad_90 / med.inad_90
      return { sev: a.severidade, texto: `A inadimplência acima de 90 dias (${p(k.inad_90)} da carteira) está bem acima da ` +
        `mediana dos pares (${p(med.inad_90)}${x >= 1.5 ? `, ${x.toFixed(0)} vezes maior` : ''}).` }
    }
    return { sev: a.severidade, texto: a.texto || `${a.descricao}${a.detalhe ? ` (${a.detalhe})` : ''}` }
  })

  const segs = ext.segmentos.filter((s) => !OUTROS.test(s.segmento))
  const segPrincipal = h.segmento_principal && !OUTROS.test(SEG[h.segmento_principal] ?? '')
    ? `${SEG[h.segmento_principal] ?? h.segmento_principal} (${p1(h.segmento_principal_pct)})` : null
  const ficha: [string, any][] = [
    ['Gestor', h.gestor], ['Administrador', h.admin], ['Custodiante', h.custodiante], ['Auditor', h.auditor],
    ['Início', fmtDate(h.data_inicio)], ['Condomínio', `${cap(String(h.condominio ?? '–').toLowerCase())}${h.exclusivo === 'S' ? ' · exclusivo' : ''}`],
    ['Categoria (interna)', h.categoria_nome], ...(segPrincipal ? [['Segmento CVM principal', segPrincipal] as [string, any]] : []),
    ['Cotistas', fmtValue(k.nr_cotistas, 'int')], ['Prazo médio da carteira', fmtValue(k.prazo_medio_dias, 'dias')],
  ]
  const ia = ext.ia
  const teseTitulo = ia ? [TESE[ia.tese] ?? ia.tese, ia.consignado && ia.consignado !== 'nao_e_consignado' ? CONSIG[ia.consignado] ?? ia.consignado : null,
    ia.foco_precatorio && ia.foco_precatorio !== 'nao_se_aplica' ? `foco ${ia.foco_precatorio.replace('_', '/')}` : null].filter(Boolean).join(' · ') : ''

  return {
    h, k, dt, par, parLinhas, plVar12, med, histo, plTipo, subMin, acum, tiposAcum, rotAcum, janelas, porSerie, senior12, sub12,
    ult12, cdi12, seriesAtivas, notaResidual, estrutura, plSeries, rfAlerta, pares, fluxo, paresDesc: comp.pares?.descricao ?? 'categoria',
    paresResumo: resumoPares(pares, comp.pares?.n), cedentes: (lam.cedentes as Row[]).slice(0, 6), alertas,
    aging: (lam.aging as Row[]).map((a) => ({ ...a, faixa: String(a.faixa).replace('>1080', '> 1080') })),
    ia, lastro: ia ? limparLastro(ia.lastro) : '', teseTitulo, segs, ficha,
    regData: ext.regulamento?.data_entrega ? String(ext.regulamento.data_entrega).slice(0, 10) : null,
  }
}

function addMeses(dt: string, n: number) {
  const d = new Date(String(dt).slice(0, 10) + 'T00:00:00')
  d.setMonth(d.getMonth() + n)
  return d.toISOString().slice(0, 10)
}
function lastBefore(hs: Row[], dt: string) {
  return [...hs].reverse().find((r) => String(r.dt) <= dt) ?? hs[0]
}
