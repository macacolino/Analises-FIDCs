import { useEffect, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, Line, LineChart, XAxis, YAxis } from 'recharts'
import { useApi, type Row } from '../api'
import { fmtCnpj, fmtDate, fmtValue, mesAno } from '../fmt'
import type { MensalResp } from './FundoTabs'
import './lamina.css'

/* Lâmina do fundo para impressão em A4 (Salvar como PDF no navegador). Identidade Ouribank: Poppins, navy + teal,
   vermelho só para alerta, sem linhas de grade nos gráficos. */

const C = { dark: '#15252D', dark2: '#23363D', teal: '#76D2D7', tealL: '#96DFE5', tealD: '#428087', muted: '#5B6E78',
  grid: '#DCE2E6', red: '#C25450', amber: '#C99A2E', green: '#428087' }

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
const TIPO_COR: Record<string, string> = { senior: C.tealD, mezanino: C.tealL, subordinada: C.dark, cdi: C.muted }
const tick = { fontSize: 8, fill: C.muted, fontFamily: 'Poppins' }
const p = (v: any) => fmtValue(v, 'pct')
const pAx = (v: number) => `${(v * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
const mi = (v: number) => `${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`

function nivelRF(f: Row): 'vermelho' | 'amarelo' | 'verde' | 'sem_dado' {
  if (f.nivel >= 2) return 'vermelho'
  if (f.nivel === 1) return 'amarelo'
  return /n\/d|nenhum cedente|sem dado/i.test(f.detalhe ?? '') ? 'sem_dado' : 'verde'
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
        <span>Fonte: CVM (informe mensal e cadastro), FNET/B3 (regulamento) e BCB (CDI). Dados declarados pelo
          administrador, sem auditoria. Uso interno Ouribank.</span>
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
      {hint && <div className="h">{hint}</div>}
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

export default function LaminaPdf() {
  const { cnpj = '' } = useParams()
  const [sp] = useSearchParams()
  const lam = useApi<any>(`/api/fundos/${cnpj}`)
  const hist = useApi<Row[]>(`/api/fundos/${cnpj}/historico?meses=24`)
  const men = useApi<MensalResp>(`/api/fundos/${cnpj}/mensal?meses=24`)
  const comp = useApi<any>(`/api/comparar/${cnpj}?modo=categoria&ignorar_sem_vencido=true`)
  const ext = useApi<Extra>(`/api/fundos/${cnpj}/lamina-extra`)
  const pronto = !!(lam.data && hist.data && men.data && comp.data && ext.data)
  const erro = lam.error || hist.error || men.error || comp.error || ext.error

  useEffect(() => {
    if (!lam.data) return
    const h = lam.data.cabecalho
    const curto = String(h.nome).split(/ FUNDO| FIDC| -/i)[0].trim()
    document.title = `Lamina ${curto} ${mesAno(h.ultimo_informe).replace('/', '-')}`
  }, [lam.data])
  useEffect(() => {
    if (pronto && sp.get('print') === '1') {
      const t = setTimeout(() => window.print(), 1200)
      return () => clearTimeout(t)
    }
  }, [pronto, sp])

  const d = useMemo(() => (pronto ? montar(lam.data, hist.data!, men.data!, comp.data, ext.data!) : null),
    [pronto, lam.data, hist.data, men.data, comp.data, ext.data])

  if (erro) return <div className="lam-wait">Não foi possível carregar os dados do fundo.</div>
  if (!d) return <div className="lam-wait">Montando a lâmina…</div>
  const { h, k, dt } = d
  const total = 3
  const nomeCurto = String(h.nome).replace(/FUNDO DE INVESTIMENTO EM DIREITOS CREDIT[ÓO]RIOS/i, 'FIDC')
    .replace(/ ?-? ?RESPONSABILIDADE LIMITADA/i, '').replace(/ DE RESP(\.|ONSABILIDADE)? LIMITADA/i, '').trim()

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
          <Kpi v={fmtValue(k.pl, 'brl')} label="Patrimônio líquido" hint={d.plVar12 != null ? <>{p(d.plVar12)} em 12 meses</> : undefined} />
          <Kpi v={p(k.subordinacao)} label="Subordinação (Mz+Jr)/PL"
            hint={d.par.sub_min_senior ? <>mínimo regulamento {p(d.par.sub_min_senior.valor_num)}</> : 'mínimo não identificado'}
            alerta={d.par.sub_min_senior?.valor_num != null && k.subordinacao < d.par.sub_min_senior.valor_num} />
          <Kpi v={p(k.subordinacao_junior)} label="Subordinada júnior / PL"
            hint={d.par.jr_min_pl ? <>mínimo regulamento {p(d.par.jr_min_pl.valor_num)}</> : undefined}
            alerta={d.par.jr_min_pl?.valor_num != null && k.subordinacao_junior < d.par.jr_min_pl.valor_num} />
          <Kpi v={p(k.inad_90)} label="Inadimplência > 90 dias" hint={d.med.inad_90 != null ? <>mediana categoria {p(d.med.inad_90)}</> : undefined} />
          <Kpi v={p(k.pdd_carteira)} label="PDD / carteira" hint={d.med.pdd_carteira != null ? <>mediana categoria {p(d.med.pdd_carteira)}</> : undefined} />
          <Kpi v={fmtValue(k.cobertura_pdd_90, 'x')} label="Cobertura PDD / vencido > 90d" />
          <Kpi v={d.senior12 ? p(d.senior12.pct_cdi_12m) : '–'} label="Sênior · 12m em % do CDI"
            hint={d.senior12 ? <>{d.senior12.rotulo}: {p(d.senior12.cota_12m)} em 12m</> : 'série sem 12 meses'} />
          <Kpi v={d.sub12 ? p(d.sub12.cota_12m) : '–'} label="Subordinada · retorno 12m"
            hint={d.sub12 ? <>{p(d.sub12.pct_cdi_12m)} do CDI</> : 'série sem 12 meses'} alerta={d.sub12 && d.sub12.cota_12m < 0} />
        </div>

        <div className="lam-cols">
          <div>
            <Bloco titulo="Características">
              <table className="lam-ficha"><tbody>
                {[
                  ['Gestor', h.gestor], ['Administrador', h.admin], ['Custodiante', h.custodiante], ['Auditor', h.auditor],
                  ['Início', fmtDate(h.data_inicio)], ['Condomínio', `${h.condominio ?? '–'}${h.exclusivo === 'S' ? ' · exclusivo' : ''}`],
                  ['Categoria (interna)', h.categoria_nome], ['Segmento CVM principal', d.segPrincipal],
                  ['Cotistas', fmtValue(k.nr_cotistas, 'int')], ['Prazo médio da carteira', fmtValue(k.prazo_medio_dias, 'dias')],
                ].map(([a, b]) => <tr key={a}><th>{a}</th><td>{b ?? '–'}</td></tr>)}
              </tbody></table>
            </Bloco>
            <Bloco titulo="Regulamento">
              <table className="lam-ficha"><tbody>
                {d.parLinhas.map((x) => <tr key={x.label}><th>{x.label}</th><td>{x.valor}{x.fonte && <span className="fonte">{x.fonte}</span>}</td></tr>)}
              </tbody></table>
              {d.regData && <div className="nota">Regulamento vigente no FNET entregue em {d.regData}. Itens sem valor não foram localizados na leitura automática.</div>}
            </Bloco>
          </div>
          <div>
            <Bloco titulo="Tese e lastro">
              {d.ia ? (
                <>
                  <div className="tese">{TESE[d.ia.tese] ?? d.ia.tese}{d.ia.consignado && d.ia.consignado !== 'nao_e_consignado' ? ` · ${String(d.ia.consignado).replace(/_/g, ' ')}` : ''}
                    {d.ia.foco_precatorio && d.ia.foco_precatorio !== 'nao_se_aplica' ? ` · foco ${d.ia.foco_precatorio}` : ''}</div>
                  <p>{d.ia.lastro}</p>
                  <div className="nota">Leitura do regulamento por IA · confiança {d.ia.confianca}.</div>
                </>
              ) : <p className="nota">Regulamento ainda não lido pela IA.</p>}
              {d.segs.length > 0 && (
                <div className="segs">
                  {d.segs.slice(0, 5).map((s) => (
                    <div key={s.segmento} className="seg"><span>{s.segmento}</span>
                      <div className="bar"><i style={{ width: `${Math.max(2, s.pct * 100)}%` }} /></div><b>{p(s.pct)}</b></div>))}
                  <div className="nota">Carteira por segmento (Tab. II do informe).</div>
                </div>
              )}
            </Bloco>
            <Bloco titulo="Red flags">
              {d.rfAlerta.length === 0 && <p className="ok">Nenhuma red flag em amarelo ou vermelho na data-base.</p>}
              {d.rfAlerta.map((f) => (
                <div key={f.id} className={`rf ${nivelRF(f)}`}>
                  <div className="rf-h"><span className="chip">{nivelRF(f) === 'vermelho' ? 'Vermelho' : 'Amarelo'}</span>
                    <b>{f.codigo} · {f.nome}</b></div>
                  <div className="rf-d">{f.detalhe}</div>
                  <div className="rf-r">{f.regra}</div>
                </div>
              ))}
              {d.rfVerde.length > 0 && (
                <div className="rf-verde"><span className="chip verde">Verde</span>{d.rfVerde.map((f) => `${f.codigo} ${f.nome}`).join(' · ')}</div>
              )}
              {d.rfSemDado.length > 0 && <div className="nota">Sem dado para avaliar: {d.rfSemDado.map((f) => f.codigo).join(', ')}.</div>}
            </Bloco>
          </div>
        </div>
      </Pagina>

      {/* ------------------------------------------------ página 2: rentabilidade */}
      <Pagina n={2} total={total} dt={dt} nome={nomeCurto}>
        <h2 className="lam-titulo">Rentabilidade por classe de cota vs. CDI</h2>
        <div className="lam-cols">
          <Bloco titulo="Retorno acumulado em 24 meses">
            {d.acum.length > 1 ? (
              <>
                <LineChart width={340} height={190} data={d.acum} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                  <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} interval="preserveStartEnd" minTickGap={24} />
                  <YAxis tickFormatter={pAx} tick={tick} tickLine={false} axisLine={false} width={38} />
                  {d.tiposAcum.map((t) => <Line key={t} dataKey={t} stroke={TIPO_COR[t]} strokeWidth={t === 'cdi' ? 1.2 : 2}
                    strokeDasharray={t === 'cdi' ? '4 3' : undefined} dot={false} isAnimationActive={false} connectNulls />)}
                </LineChart>
                <div className="leg">{d.tiposAcum.map((t) => <span key={t}><i style={{ background: TIPO_COR[t] }} />{d.rotAcum[t]}</span>)}</div>
              </>
            ) : <p className="nota">Histórico insuficiente.</p>}
          </Bloco>
          <Bloco titulo="Rentabilidade acumulada por série">
            <table className="lam-tab">
              <thead><tr><th>Série</th><th className="r">3m</th><th className="r">6m</th><th className="r">12m</th><th className="r">Início*</th></tr></thead>
              <tbody>{d.janelas.map((j) => (
                <tr key={j.serie} title={j.serie}><td>{j.rotulo}</td>
                  {['3m', '6m', '12m', 'inicio'].map((x) => (
                    <td key={x} className="r">{p(j[`cota_${x}`])}<span className="sub">{j[`pct_cdi_${x}`] != null ? `${p(j[`pct_cdi_${x}`])} CDI` : ''}</span></td>))}
                </tr>))}</tbody>
            </table>
            <div className="nota">* desde o 1º mês da série no informe ({d.janelas[0]?.desde ? mesAno(d.janelas[0].desde) : '–'} na primeira série).</div>
          </Bloco>
        </div>
        <Bloco titulo="Retorno mensal vs. CDI · últimos 12 meses">
          <table className="lam-tab mensal">
            <thead><tr><th>Série</th><th />{d.ult12.map((m) => <th key={m.dt} className="r">{mesAno(m.dt).replace('/20', '/')}</th>)}</tr></thead>
            <tbody>
              {d.seriesAtivas.map((s) => (
                <>
                  <tr key={s.key + 'c'} className="cota"><td rowSpan={2}>{s.rotulo}</td><td className="muted">cota</td>
                    {d.ult12.map((m) => <td key={m.dt} className={`r${(m[`${s.key}_rentab`] ?? 0) < 0 ? ' neg' : ''}`}>{p(m[`${s.key}_rentab`])}</td>)}</tr>
                  <tr key={s.key + 'p'} className="pcdi"><td className="muted">% CDI</td>
                    {d.ult12.map((m) => <td key={m.dt} className="r muted">{p(m[`${s.key}_pct_cdi`])}</td>)}</tr>
                </>
              ))}
              <tr className="cdi"><td>CDI</td><td />{d.ult12.map((m) => <td key={m.dt} className="r">{p(m.cdi_mes)}</td>)}</tr>
            </tbody>
          </table>
          <div className="nota">Rentabilidade informada pelo administrador (Tab. X.3). Quando ela não considera a amortização do mês,
            usamos a variação da cota somada à amortização por cota estimada (Tab. X.4) — estimativa, pode diferir da lâmina do gestor.</div>
        </Bloco>
        <div className="lam-cols">
          <Bloco titulo="Patrimônio por classe de cota (R$ mi)">
            <AreaChart width={340} height={170} data={d.plTipo} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={24} />
              <YAxis tickFormatter={mi} tick={tick} tickLine={false} axisLine={false} width={34} />
              <Area dataKey="pl_subordinada" stackId="1" stroke={C.dark} fill={C.dark} isAnimationActive={false} />
              <Area dataKey="pl_mezanino" stackId="1" stroke={C.tealL} fill={C.tealL} isAnimationActive={false} />
              <Area dataKey="pl_senior" stackId="1" stroke={C.tealD} fill={C.tealD} isAnimationActive={false} />
            </AreaChart>
            <div className="leg"><span><i style={{ background: C.tealD }} />Sênior</span><span><i style={{ background: C.tealL }} />Mezanino</span>
              <span><i style={{ background: C.dark }} />Subordinada</span></div>
          </Bloco>
          <Bloco titulo="Subordinação vs. mínimo do regulamento">
            <LineChart width={340} height={170} data={d.histo} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={24} />
              <YAxis tickFormatter={pAx} tick={tick} tickLine={false} axisLine={false} width={38} domain={[0, 'auto']} />
              <Line dataKey="subordinacao" stroke={C.tealD} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="setor_subordinacao" stroke={C.muted} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              {d.par.sub_min_senior?.valor_num != null && <Line dataKey="sub_min" stroke={C.red} strokeWidth={1.2} dot={false} isAnimationActive={false} />}
            </LineChart>
            <div className="leg"><span><i style={{ background: C.tealD }} />Fundo</span><span><i style={{ background: C.muted }} />Mediana categoria</span>
              {d.par.sub_min_senior?.valor_num != null && <span><i style={{ background: C.red }} />Mínimo regulamento</span>}</div>
          </Bloco>
        </div>
      </Pagina>

      {/* ------------------------------------------------ página 3: estrutura, carteira e pares */}
      <Pagina n={3} total={total} dt={dt} nome={nomeCurto}>
        <h2 className="lam-titulo">Estrutura, carteira e posição vs. pares</h2>
        <Bloco titulo="Estrutura de cotas na data-base">
          <table className="lam-tab">
            <thead><tr><th>Série</th><th>Tipo</th><th className="r">PL</th><th className="r">% PL</th><th className="r">Valor da cota</th>
              <th className="r">Retorno 12m</th><th className="r">% CDI 12m</th><th className="r">Cotistas</th></tr></thead>
            <tbody>{d.estrutura.map((s) => (
              <tr key={s.serie}><td>{s.rotulo ?? s.serie}</td><td>{s.tipo}</td><td className="r">{fmtValue(s.pl_serie, 'brl')}</td>
                <td className="r">{p(s.pct_pl)}</td><td className="r">{fmtValue(s.valor_cota, 'num')}</td>
                <td className="r">{p(s.r12)}</td><td className="r">{p(s.c12)}</td><td className="r">{fmtValue(s.nr_cotistas, 'int')}</td></tr>))}
              <tr className="tot"><td>Total</td><td /><td className="r">{fmtValue(d.plSeries, 'brl')}</td><td className="r">100,00%</td><td colSpan={4} /></tr>
            </tbody>
          </table>
        </Bloco>
        <div className="lam-cols">
          <Bloco titulo="Inadimplência > 90d e PDD">
            <LineChart width={340} height={165} data={d.histo} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="dt" tickFormatter={mesAno} tick={tick} tickLine={false} axisLine={{ stroke: C.grid }} minTickGap={24} />
              <YAxis tickFormatter={pAx} tick={tick} tickLine={false} axisLine={false} width={38} />
              <Line dataKey="inad_90" stroke={C.red} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="pdd_carteira" stroke={C.tealD} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="setor_inad_90" stroke={C.muted} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            </LineChart>
            <div className="leg"><span><i style={{ background: C.red }} />Inad. &gt; 90d</span><span><i style={{ background: C.tealD }} />PDD / carteira</span>
              <span><i style={{ background: C.muted }} />Inad. &gt; 90d · mediana categoria</span></div>
          </Bloco>
          <Bloco titulo="Carteira por faixa (R$ mi)">
            <BarChart width={340} height={165} data={d.aging} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="faixa" tick={{ ...tick, fontSize: 6.5 }} tickLine={false} axisLine={{ stroke: C.grid }} interval={0} />
              <YAxis tickFormatter={mi} tick={tick} tickLine={false} axisLine={false} width={34} />
              <Bar dataKey="a_vencer" fill={C.tealD} isAnimationActive={false} />
              <Bar dataKey="vencido" fill={C.red} isAnimationActive={false} />
            </BarChart>
            <div className="leg"><span><i style={{ background: C.tealD }} />A vencer (por prazo)</span><span><i style={{ background: C.red }} />Vencido (por atraso)</span></div>
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
          <Bloco titulo="Maiores cedentes (Tab. I)">
            {d.cedentes.length ? (
              <table className="lam-tab">
                <thead><tr><th>#</th><th>CPF/CNPJ</th><th className="r">% carteira</th></tr></thead>
                <tbody>{d.cedentes.map((c: Row) => <tr key={c.rank}><td>{c.rank}</td>
                  <td>{c.cedente_doc?.length === 14 ? fmtCnpj(c.cedente_doc) : c.cedente_doc}</td><td className="r">{fmtValue(c.pct, 'pct100')}</td></tr>)}</tbody>
              </table>
            ) : <p className="nota">O fundo não informou cedentes no informe.</p>}
            {d.alertas.length > 0 && (
              <>
                <h4>Alertas do mês</h4>
                <ul className="alertas">{d.alertas.slice(0, 6).map((a: Row) => <li key={a.id} className={a.severidade}>{a.descricao}{a.detalhe ? ` — ${a.detalhe}` : ''}</li>)}</ul>
              </>
            )}
          </Bloco>
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

function montar(lam: any, hist: Row[], men: MensalResp, comp: any, ext: Extra) {
  const h = lam.cabecalho, k = lam.kpis, dt = k.dt ?? h.ultimo_informe
  const par = Object.fromEntries(ext.parametros.map((x) => [x.chave, x]))
  const parLinhas = PAR_ORDEM.map(([kk, label]) => {
    const x = par[kk]
    let valor = '–'
    if (x) {
      if (x.valor_num != null) valor = kk === 'prazo_resgate_dias' ? `${x.valor_num} dias` : fmtValue(x.valor_num, x.fmt === 'pct' ? 'pct' : x.fmt)
      if (x.valor_txt && x.valor_txt.length > 1) valor = x.valor_num != null ? `${valor} · ${x.valor_txt}` : x.valor_txt
      else if (x.valor_txt === 'S') valor = 'Sim'
      else if (x.valor_txt === 'N') valor = kk === 'responsabilidade_limitada' ? 'Não' : 'Não há'
    }
    const fonte = x ? (x.manual ? 'informado pela equipe' : (x.fonte ?? '').replace('regulamento ', '').replace(/[()]/g, '')) : ''
    return { label, valor: valor.length > 90 ? valor.slice(0, 88) + '…' : valor, fonte }
  })
  const hs = [...hist].sort((a, b) => String(a.dt).localeCompare(String(b.dt)))
  const base12 = hs.length && String(hs[0].dt) <= addMeses(dt, -12) ? lastBefore(hs, addMeses(dt, -12)) : null
  const plVar12 = base12?.pl ? k.pl / base12.pl - 1 : null
  const subMin = par.sub_min_senior?.valor_num ?? null
  const histo = hs.map((r) => ({ ...r, sub_min: subMin }))
  const med = Object.fromEntries((lam.comparativo as Row[]).map((c) => [c.metrica, c.mediana]))

  // rentabilidade: série principal (maior PL) de cada tipo, encadeada nos últimos 24 meses
  const meses = [...men.meses].sort((a, b) => String(a.dt).localeCompare(String(b.dt)))
  const ult = men.meses[0] ?? {}
  const principal: Record<string, { key: string; rotulo: string }> = {}
  for (const s of men.series) {
    const pl = ult[`${s.key}_pl`] ?? 0
    const atual = principal[s.tipo]
    if (pl > 0 && (!atual || pl > (ult[`${atual.key}_pl`] ?? 0))) principal[s.tipo] = { key: s.key, rotulo: s.rotulo }
  }
  const tiposAcum = [...['senior', 'mezanino', 'subordinada'].filter((t) => principal[t]), 'cdi']
  const rotAcum: Record<string, string> = { cdi: 'CDI' }
  for (const t of tiposAcum) if (principal[t]) rotAcum[t] = principal[t].rotulo
  const acc: Record<string, number | null> = {}
  const acum = meses.map((m) => {
    const o: Row = { dt: m.dt }
    for (const t of tiposAcum) {
      const r = t === 'cdi' ? m.cdi_mes : m[`${principal[t].key}_rentab`]
      if (r == null) { o[t] = acc[t] ?? null; continue }
      acc[t] = (1 + (acc[t] ?? 0)) * (1 + r) - 1
      o[t] = acc[t]
    }
    return o
  })
  const janelas = men.janelas.filter((j) => j.cota_3m != null || j.cota_inicio != null)
    .filter((j) => (ult[`${men.series.find((s) => s.serie === j.serie)?.key}_pl`] ?? 0) > 0)
  const porRot = Object.fromEntries(men.janelas.map((j) => [j.serie, j]))
  const senior12 = principal.senior ? porRot[men.series.find((s) => s.key === principal.senior.key)!.serie] : null
  const sub12 = principal.subordinada ? porRot[men.series.find((s) => s.key === principal.subordinada.key)!.serie] : null
  const ult12 = men.meses.slice(0, 12).reverse()
  const seriesAtivas = men.series.filter((s) => (ult[`${s.key}_pl`] ?? 0) > 0)

  const plSeries = (lam.series as Row[]).reduce((a, s) => a + (s.pl_serie ?? 0), 0)
  const rotPorSerie = Object.fromEntries(men.series.map((s) => [s.serie, s.rotulo]))
  const estrutura: Row[] = (lam.series as Row[]).filter((s) => (s.pl_serie ?? 0) > 0).map((s) => ({
    ...s, rotulo: rotPorSerie[s.serie], pct_pl: plSeries ? s.pl_serie / plSeries : null,
    tipo: ({ senior: 'Sênior', mezanino: 'Mezanino', subordinada: 'Subordinada' } as Record<string, string>)[s.tipo] ?? s.tipo,
    r12: porRot[s.serie]?.cota_12m, c12: porRot[s.serie]?.pct_cdi_12m,
  }))

  const rfs = (comp.red_flags as Row[])
  const rfAlerta = rfs.filter((f) => f.nivel > 0).sort((a, b) => b.nivel - a.nivel)
  const rfVerde = rfs.filter((f) => nivelRF(f) === 'verde')
  const rfSemDado = rfs.filter((f) => nivelRF(f) === 'sem_dado')

  const pares = (comp.metricas as Row[]).filter((m) => m.valor != null && m.mediana != null)
    .sort((a, b) => BLOCOS.indexOf(a.bloco) - BLOCOS.indexOf(b.bloco)).slice(0, 14)

  return {
    h, k, dt, par, parLinhas, plVar12, med, histo, acum, tiposAcum, rotAcum, janelas, senior12, sub12, ult12, seriesAtivas,
    estrutura, plSeries, rfAlerta, rfVerde, rfSemDado, pares, paresDesc: comp.pares?.descricao ?? 'categoria',
    cedentes: (lam.cedentes as Row[]).slice(0, 8), alertas: lam.alertas as Row[], aging: lam.aging as Row[],
    plTipo: hs.map((r) => ({ dt: r.dt, pl_senior: r.pl_senior ?? null, pl_mezanino: r.pl_mezanino ?? null, pl_subordinada: r.pl_subordinada ?? null }))
      .map((r) => r.pl_senior == null ? { ...r, ...plDoMensal(meses, String(r.dt)) } : r),
    ia: ext.ia, segs: ext.segmentos,
    segPrincipal: h.segmento_principal ? `${SEG[h.segmento_principal] ?? h.segmento_principal} (${p(h.segmento_principal_pct)})` : '–',
    regData: ext.regulamento?.data_entrega ? String(ext.regulamento.data_entrega).slice(0, 10) : null,
  }
}

function plDoMensal(meses: Row[], dt: string) {
  const m = meses.find((x) => String(x.dt) === dt)
  return { pl_senior: m?.pl_senior ?? null, pl_mezanino: m?.pl_mezanino ?? null, pl_subordinada: m?.pl_subordinada ?? null }
}
function addMeses(dt: string, n: number) {
  const d = new Date(String(dt).slice(0, 10) + 'T00:00:00')
  d.setMonth(d.getMonth() + n)
  return d.toISOString().slice(0, 10)
}
function lastBefore(hs: Row[], dt: string) {
  return [...hs].reverse().find((r) => String(r.dt) <= dt) ?? hs[0]
}
