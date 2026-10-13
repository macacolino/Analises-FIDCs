import { useSearchParams } from 'react-router-dom'
import { useApi, type Row } from '../api'
import { DataGrid } from '../components/DataGrid'
import { Loading } from '../components/ui'
import { fmtValue } from '../fmt'

export default function Consultorias() {
  const [params, setParams] = useSearchParams()
  const sel = params.get('c')
  const lista = useApi<Row[]>('/api/consultorias')
  const fundos = useApi<Row[]>(sel ? `/api/consultorias/fundos?chave=${encodeURIComponent(sel)}` : null)
  const c = lista.data?.find((x) => x.consultoria_chave === sel)
  const abrir = (k: string | null) => setParams(k ? { c: k } : {})

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Consultorias de crédito</h1>
          <div className="sub">
            Consultora especializada (quem analisa e seleciona os direitos creditórios para o gestor) nomeada no regulamento
            mais recente de cada FIDC no FNET, e os fundos ativos que ela atende, com os indicadores do último informe.
            Fonte: definição explícita no regulamento (regras) e leitura por IA; o regulamento pode estar desatualizado se a
            consultoria foi trocada sem nova versão no FNET.
          </div>
        </div>
      </div>
      <Loading q={lista} />
      {lista.data && (
        <div className="card">
          <DataGrid title="Consultorias" rows={lista.data} height={520} exportUrl="/api/consultorias"
            cols={[
              { field: 'consultoria', headerName: 'Consultoria', minWidth: 320, cellRenderer: (p: any) => (
                <a href="#" onClick={(e) => { e.preventDefault(); abrir(p.data.consultoria_chave) }}>{p.value}</a>) },
              'consultoria_cnpj', 'fundos', 'pl', 'inad_90_mediana', 'pdd_carteira_mediana', 'subordinacao_mediana',
              'fundos_com_red_flag', 'fundos_parte_relacionada', 'administradores', 'gestores',
            ]} />
        </div>
      )}
      {sel && (
        <div className="card stack">
          <div className="row"><h2 style={{ margin: 0 }}>{c?.consultoria ?? 'Consultoria'}</h2>
            {c?.consultoria_cnpj && <span className="muted">CNPJ {c.consultoria_cnpj}</span>}
            <div className="spacer" /><button className="ghost" onClick={() => abrir(null)}>Fechar</button></div>
          {c && <div className="muted">
            {fmtValue(c.fundos, 'int')} fundo(s) ativo(s) · PL somado {fmtValue(c.pl, 'brl')} · inadimplência &gt;90d mediana{' '}
            {fmtValue(c.inad_90_mediana, 'pct')} · {fmtValue(c.fundos_com_red_flag, 'int')} com red flag vermelha
          </div>}
          <Loading q={fundos} />
          {fundos.data && (
            <DataGrid title="Fundos" rows={fundos.data} height={460}
              exportUrl={`/api/consultorias/fundos?chave=${encodeURIComponent(sel)}`}
              cols={['nome', 'categoria_nome', 'admin', 'gestor', 'pl', 'inad_90', 'pdd_carteira', 'subordinacao',
                     'consultoria_relacionada', 'consultoria_relacionada_com', 'agente_cobranca', 'consultoria_origem',
                     'consultoria_confianca']} />
          )}
        </div>
      )}
    </div>
  )
}
