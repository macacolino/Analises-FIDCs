import { useState } from 'react'
import { useApi, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'
import { Loading } from '../components/ui'
import { fmtValue } from '../fmt'

const CURVA = ['curva_a_vencer', 'curva_in_30', 'curva_in_60', 'curva_in_90', 'curva_in_120', 'curva_in_150', 'curva_in_180', 'curva_in_mais180']
const REGUA = [null, 0.01, 0.03, 0.10, 0.30, 0.50, 0.70, 1.0]
export const METODO: Record<string, string> = {
  faixa_atraso: 'Faixa de atraso', rating_2682: 'Rating (2.682)', perda_esperada_estagios: 'Perda esperada (estágios)',
  mista: 'Mista', sem_provisao: 'Não provisiona', nao_descrito: 'Não descrito',
}
const metodoCol = { field: 'metodo', valueFormatter: (p: any) => METODO[p.value] ?? p.value ?? '' }
const ROT = ['A vencer', '1-30 d', '31-60 d', '61-90 d', '91-120 d', '121-150 d', '151-180 d', '> 180 d']

export default function Pdd() {
  const adm = useApi<Row[]>('/api/pdd/administradores')
  const [sel, setSel] = useState<string | null>(null)
  const fundos = useApi<Row[]>(sel ? `/api/pdd/fundos?admin=${encodeURIComponent(sel)}` : null)
  const a = adm.data?.find((x) => x.admin === sel)

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>PDD por administrador</h1>
          <div className="sub">
            Quanto cada administrador provisiona na prática, pelo informe mensal da CVM: PDD declarada comparada à régua da
            Res. CMN 2.682 aplicada às parcelas vencidas (1% de 1 a 30 dias, 3%, 10%, 30%, 50%, 70% e 100% acima de 180 dias) e a
            curva implícita (% por faixa de atraso que melhor explica a PDD dos fundos dele em 12 meses). A régua é um piso:
            com efeito vagão e provisão na compra, a PDD costuma ficar acima dela. A política escrita vem da nota de PDD das
            demonstrações financeiras no FNET, lida por IA (método e régua mais frequentes entre os fundos lidos).
          </div>
        </div>
      </div>
      <Loading q={adm} />
      {adm.data && (
        <div className="card">
          <DataGrid title="Administradores" rows={adm.data} height={520} exportUrl="/api/pdd/administradores"
            cols={[
              { field: 'admin', headerName: 'Administrador', minWidth: 300, cellRenderer: (p: any) => (
                <a href="#" onClick={(e) => { e.preventDefault(); setSel(p.value) }}>{p.value}</a>) },
              'fundos', 'pl', 'fundos_com_vencido', 'pdd_carteira_mediana', 'pdd_regua_mediana', 'pct_abaixo_regua',
              'pdd_vencido90_mediana', ...CURVA, 'curva_r2',
              { field: 'metodo_predominante', valueFormatter: (p: any) => METODO[p.value] ?? p.value ?? '' }, 'regua_escrita_tipica', 'fundos_com_politica',
            ]} />
        </div>
      )}
      {a && (
        <div className="card stack">
          <div className="row"><h2 style={{ margin: 0 }}>{a.admin}</h2><div className="spacer" />
            <button className="ghost" onClick={() => setSel(null)}>Fechar</button></div>
          <div>
            <h3>Curva implícita vs. régua 2.682</h3>
            {a.curva_r2 != null ? (
              <table className="simple" style={{ maxWidth: 900 }}>
                <thead><tr><th>Faixa</th>{ROT.map((r) => <th key={r} className="r">{r}</th>)}</tr></thead>
                <tbody>
                  <tr><td>Praticada (estimativa)</td>{CURVA.map((c) => <td key={c} className="r num"><b>{fmtValue(a[c], 'pct')}</b></td>)}</tr>
                  <tr><td className="muted">Régua 2.682</td>{REGUA.map((r, i) => <td key={i} className="r num muted">{r == null ? '–' : fmtValue(r, 'pct')}</td>)}</tr>
                </tbody>
              </table>
            ) : <p className="muted">Fundos com atraso insuficientes para estimar a curva (mínimo 3 fundos e 24 fundo-meses com vencido).</p>}
            {a.curva_r2 != null && <div className="muted" style={{ marginTop: 6 }}>R² {fmtValue(a.curva_r2, 'num')} sobre {a.curva_n} fundo-meses.
              R² baixo = fundos do administrador provisionam de formas diferentes entre si.</div>}
          </div>
          {a.fundos_com_politica ? (
            <div>
              <h3>Política escrita (demonstrações financeiras)</h3>
              <div className="muted">
                {fmtValue(a.fundos_com_politica, 'int')} fundo(s) com a nota de PDD lida. Método mais frequente:{' '}
                <b>{METODO[a.metodo_predominante] ?? a.metodo_predominante}</b>
                {a.regua_escrita_tipica && <> · régua mais frequente: <b>{a.regua_escrita_tipica}</b></>}
              </div>
            </div>
          ) : <p className="muted">Nenhuma demonstração financeira deste administrador lida ainda.</p>}
          <Loading q={fundos} />
          {fundos.data && (
            <DataGrid title="Fundos" rows={fundos.data} height={460} exportUrl={`/api/pdd/fundos?admin=${encodeURIComponent(a.admin)}`}
              cols={['nome', 'categoria_nome', 'pl', 'carteira', 'pdd', 'pdd_carteira', 'vencido', 'vencido_90', 'regua_2682', 'pdd_regua',
                     'pdd_vencido90', metodoCol, 'faixas_txt', 'efeito_vagao', 'provisao_inicial', 'data_df']} />
          )}
        </div>
      )}
    </div>
  )
}
