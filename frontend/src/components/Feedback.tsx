import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { send } from '../api'

function lerNome() {
  try { return localStorage.getItem('fidc_nome') ?? '' } catch { return '' }
}

/** Botão fixo para o time comentar a tela atual; vai para a planilha de feedback (FIDC_FEEDBACK_URL). */
export default function Feedback() {
  const loc = useLocation()
  const [aberto, setAberto] = useState(false)
  const [nome, setNome] = useState(lerNome)
  const [texto, setTexto] = useState('')
  const [estado, setEstado] = useState<'' | 'enviando' | 'ok' | 'erro'>('')

  async function enviar() {
    setEstado('enviando')
    try {
      try { localStorage.setItem('fidc_nome', nome) } catch { /* sem storage */ }
      const cnpj = loc.pathname.match(/^\/fundo\/(\d+)/)?.[1]
      await send('POST', '/api/feedback', { texto, nome, pagina: loc.pathname + loc.search, cnpj })
      setEstado('ok')
      setTexto('')
      setTimeout(() => { setAberto(false); setEstado('') }, 1500)
    } catch {
      setEstado('erro')
    }
  }

  return (
    <div className="feedback">
      {aberto && (
        <div className="card feedback-box stack" style={{ gap: 8 }}>
          <div className="row"><b>Feedback desta tela</b><div className="spacer" />
            <button className="ghost" onClick={() => setAberto(false)} aria-label="Fechar">✕</button></div>
          <input type="text" placeholder="Seu nome" value={nome} onChange={(e) => setNome(e.target.value)} />
          <textarea placeholder="O que está errado, confuso ou faltando? Pode citar o número que não bate." value={texto}
            onChange={(e) => setTexto(e.target.value)} rows={5} autoFocus />
          <div className="row">
            <span className="muted" style={{ fontSize: 12 }}>
              {estado === 'ok' ? 'Enviado, obrigado!' : estado === 'erro' ? 'Não foi. Tente de novo.' : `Tela: ${loc.pathname}`}
            </span>
            <div className="spacer" />
            <button className="primary" disabled={!texto.trim() || estado === 'enviando'} onClick={enviar}>
              {estado === 'enviando' ? 'Enviando…' : 'Enviar'}</button>
          </div>
        </div>
      )}
      {!aberto && <button className="primary feedback-btn" onClick={() => setAberto(true)}>Feedback</button>}
    </div>
  )
}
