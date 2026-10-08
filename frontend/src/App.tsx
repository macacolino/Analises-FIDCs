import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useMeta } from './api'
import { fmtDate, mesAno } from './fmt'
import Comparar from './pages/Comparar'
import Fundo from './pages/Fundo'
import Glossario from './pages/Glossario'
import Grupos from './pages/Grupos'
import Qualidade from './pages/Qualidade'
import LaminaPdf from './pages/LaminaPdf'
import Lista from './pages/Lista'
import Mercado from './pages/Mercado'
import Oportunidades from './pages/Oportunidades'
import Pesquisa from './pages/Pesquisa'
import Setor from './pages/Setor'

export default function App() {
  const meta = useMeta()
  const loc = useLocation()
  if (loc.pathname.startsWith('/lamina/')) {
    return <Routes><Route path="/lamina/:cnpj" element={<LaminaPdf />} /></Routes>
  }
  return (
    <>
      <header className="topbar">
        <span className="logo">Analisador de FIDCs</span>
        <nav>
          <NavLink to="/" end>Mercado</NavLink>
          <NavLink to="/oportunidades">Oportunidades</NavLink>
          <NavLink to="/setores">Setores</NavLink>
          <NavLink to="/pesquisa">Pesquisa</NavLink>
          <NavLink to="/comparar">Comparar</NavLink>
          <NavLink to="/carteira">Carteira</NavLink>
          <NavLink to="/watchlist">Watchlist</NavLink>
          <NavLink to="/grupos">Grupos de pares</NavLink>
          <NavLink to="/qualidade">Qualidade</NavLink>
          <NavLink to="/glossario">Glossário</NavLink>
        </nav>
        {meta.data && (
          <span className="meta" title={`Último mês com dados parciais: ${mesAno(meta.data.ultimo_mes)}`}>
            Referência {mesAno(meta.data.mes_referencia)} · base de {fmtDate(meta.data.atualizado_em)}
          </span>
        )}
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Mercado />} />
          <Route path="/oportunidades" element={<Oportunidades />} />
          <Route path="/setores" element={<Setor />} />
          <Route path="/setores/:categoria" element={<Setor />} />
          <Route path="/pesquisa" element={<Pesquisa />} />
          <Route path="/comparar" element={<Comparar />} />
          <Route path="/grupos" element={<Grupos />} />
          <Route path="/qualidade" element={<Qualidade />} />
          <Route path="/glossario" element={<Glossario />} />
          <Route path="/fundo/:cnpj" element={<Fundo />} />
          <Route path="/carteira" element={<Lista tipo="carteira" />} />
          <Route path="/watchlist" element={<Lista tipo="watchlist" />} />
          <Route path="*" element={<div className="card">Página não encontrada.</div>} />
        </Routes>
      </main>
    </>
  )
}
