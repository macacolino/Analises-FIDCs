import { useSearchParams } from 'react-router-dom'
import { useApi, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'
import { Loading, Tabs } from '../components/ui'
import { fmtValue } from '../fmt'

type Tipo = 'gestor' | 'admin'
const NOME: Record<Tipo, [string, string]> = { gestor: ['Gestoras', 'Gestora'], admin: ['Administradoras', 'Administradora'] }

export default function Casas() {
  const [params, setParams] = useSearchParams()
  const tipo = (params.get('tipo') === 'admin' ? 'admin' : 'gestor') as Tipo
  const sel = params.get('casa')
  const lista = useApi<Row[]>(`/api/casas?tipo=${tipo}`)
  const fundos = useApi<Row[]>(sel ? `/api/casas/fundos?tipo=${tipo}&casa=${encodeURIComponent(sel)}` : null)
  const c = lista.data?.find((x) => x.casa === sel)
  const ir = (t: Tipo, casa?: string | null) => setParams(casa ? { tipo: t, casa } : { tipo: t })

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Gestoras e administradoras</h1>
          <div className="sub">
            AuM = PL somado dos fundos ativos no último informe da CVM. Remuneração sênior e mezanino: CDI + x% a.a.
            estimado pelo excesso mensal mediano sobre o CDI em 12 meses, só em fundos com mais de uma classe de cota
            (ignora meses de amortização e cota parada) — é a remuneração efetiva, não o benchmark do regulamento.
            Filtre qualquer coluna por valor (&gt;5, &lt;1, 2-4).
          </div>
        </div>
      </div>
      <Tabs value={tipo} onChange={(t) => ir(t)} options={[['gestor', 'Gestoras'], ['admin', 'Administradoras']]} />
      <Loading q={lista} />
      {lista.data && (
        <div className="card">
          <DataGrid title={`${NOME[tipo][0]} por AuM`} rows={lista.data} height={520} exportUrl={`/api/casas?tipo=${tipo}`}
            cols={[
              { field: 'casa', headerName: NOME[tipo][1], minWidth: 300, cellRenderer: (p: any) => (
                <a href="#" onClick={(e) => { e.preventDefault(); ir(tipo, p.value) }}>{p.value}</a>) },
              'pl', 'fundos', 'pl_mediano', 'categoria_principal', 'spread_senior_mediano', 'spread_senior_ponderado',
              'fundos_com_senior', 'spread_mezanino_mediano', 'fundos_com_mezanino', 'subordinacao_mediana',
              'inad_90_mediana', 'pdd_carteira_mediana', 'taxa_gestao_mediana', 'taxa_administracao_mediana',
              'taxa_desconto_mediana',
            ]} />
        </div>
      )}
      {sel && (
        <div className="card stack">
          <div className="row"><h2 style={{ margin: 0 }}>{sel}</h2><div className="spacer" />
            <button className="ghost" onClick={() => ir(tipo)}>Fechar</button></div>
          {c && <div className="muted">
            AuM {fmtValue(c.pl, 'brl')} em {fmtValue(c.fundos, 'int')} fundo(s) ativo(s) · remuneração sênior mediana{' '}
            {c.spread_senior_mediano != null ? `CDI + ${fmtValue(c.spread_senior_mediano, 'pct')} a.a.` : '–'} · mezanino{' '}
            {c.spread_mezanino_mediano != null ? `CDI + ${fmtValue(c.spread_mezanino_mediano, 'pct')} a.a.` : '–'}
          </div>}
          <Loading q={fundos} />
          {fundos.data && (
            <DataGrid title="Fundos" rows={fundos.data} height={460}
              exportUrl={`/api/casas/fundos?tipo=${tipo}&casa=${encodeURIComponent(sel)}`}
              cols={['nome', 'categoria_nome', tipo === 'gestor' ? 'admin' : 'gestor', 'pl', 'estrutura', 'subordinacao',
                     'sub_min_senior', 'spread_senior_aa', 'spread_mezanino_aa', 'inad_90', 'pdd_carteira', 'taxa_gestao',
                     'taxa_administracao', 'taxa_desconto_aa']} />
          )}
        </div>
      )}
    </div>
  )
}
