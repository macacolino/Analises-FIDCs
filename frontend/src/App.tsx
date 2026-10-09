import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useMeta } from './api'
import { fmtDate, mesAno } from './fmt'
import Feedback from './components/Feedback'
import FundPicker from './components/FundPicker'
import { Icone } from './components/Icones'
import Comparar from './pages/Comparar'
import Fundo from './pages/Fundo'
import Glossario from './pages/Glossario'
import Qualidade from './pages/Qualidade'
import LaminaPdf from './pages/LaminaPdf'
import Lista from './pages/Lista'
import Mercado from './pages/Mercado'
import Oportunidades from './pages/Oportunidades'
import Pdd from './pages/Pdd'
import Pesquisa from './pages/Pesquisa'
import Setor from './pages/Setor'

function Item({ to, icone, children }: { to: string; icone: keyof typeof Icone; children: React.ReactNode }) {
  const I = Icone[icone]
  return <NavLink to={to} end={to === '/'}><I />{children}</NavLink>
}

export default function App() {
  const meta = useMeta()
  const loc = useLocation()
  const ir = useNavigate()
  if (loc.pathname.startsWith('/lamina/')) {
    return <Routes><Route path="/lamina/:cnpj" element={<LaminaPdf />} /></Routes>
  }
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img src="/ouribank_white.png" alt="Ouribank" />
          <span>Analisador de FIDCs</span>
        </div>
        <nav>
          <div className="grp">Mercado</div>
          <Item to="/" icone="mercado">Visão geral</Item>
          <Item to="/oportunidades" icone="oportunidades">Oportunidades</Item>
          <Item to="/setores" icone="setores">Setores</Item>
          <div className="grp">Fundos</div>
          <Item to="/pesquisa" icone="pesquisa">Pesquisa</Item>
          <Item to="/comparar" icone="comparar">Comparar</Item>
          <div className="grp">Acompanhamento</div>
          <Item to="/carteira" icone="carteira">Carteira</Item>
          <Item to="/watchlist" icone="watchlist">Watchlist</Item>
          <div className="grp">Referência</div>
          <Item to="/pdd" icone="pdd">PDD por administrador</Item>
          <Item to="/qualidade" icone="qualidade">Qualidade do dado</Item>
          <Item to="/glossario" icone="glossario">Glossário</Item>
        </nav>
        {meta.data && (
          <div className="foot" title={`Último mês com dados parciais: ${mesAno(meta.data.ultimo_mes)}`}>
            Referência <b>{mesAno(meta.data.mes_referencia)}</b><br />Base atualizada em {fmtDate(meta.data.atualizado_em)}
          </div>
        )}
      </aside>
      <div className="content">
        <header className="topbar">
          <div className="busca"><FundPicker onPick={(r) => ir(`/fundo/${r.cnpj}`)} placeholder="Ir para um fundo: nome ou CNPJ…" /></div>
          {meta.data && <span className="badge pill">{meta.data.fundos_ativos?.toLocaleString('pt-BR')} fundos ativos · ref. {mesAno(meta.data.mes_referencia)}</span>}
        </header>
        <main>
        <Routes>
          <Route path="/" element={<Mercado />} />
          <Route path="/oportunidades" element={<Oportunidades />} />
          <Route path="/setores" element={<Setor />} />
          <Route path="/setores/:categoria" element={<Setor />} />
          <Route path="/pesquisa" element={<Pesquisa />} />
          <Route path="/comparar" element={<Comparar />} />
          <Route path="/qualidade" element={<Qualidade />} />
          <Route path="/pdd" element={<Pdd />} />
          <Route path="/glossario" element={<Glossario />} />
          <Route path="/fundo/:cnpj" element={<Fundo />} />
          <Route path="/carteira" element={<Lista tipo="carteira" />} />
          <Route path="/watchlist" element={<Lista tipo="watchlist" />} />
          <Route path="*" element={<div className="card">Página não encontrada.</div>} />
        </Routes>
      </main>
      </div>
      <Feedback />
    </div>
  )
}
