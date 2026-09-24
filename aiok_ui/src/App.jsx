import { useEffect, useRef, useState } from 'react'
import './App.css'

const paths = {
  plus: 'M12 5v14M5 12h14', arrow: 'M12 19V5m-6 6 6-6 6 6',
  spark: 'm12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6Z',
  code: 'm8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16',
  bulb: 'M9 18h6m-5 3h4M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 2H9s0-1-1-2',
  file: 'M14 3H5v18h14V8Zm0 0v5h5M8 12h8m-8 4h6',
  book: 'M12 5v16M12 5C8 2 3 3 3 3v16s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2',
  mic: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0Zm-4 6v1a7 7 0 0 0 14 0v-1M12 19v3m-4 0h8',
  settings: 'M4 7h16M4 17h16M8 4v6m8 4v6',
  down: 'm8 10 4 4 4-4', close: 'm6 6 12 12M6 18 18 6',
  copy: 'M9 9h11v12H9ZM15 9V3H3v12h6',
  retry: 'M20 7v5h-5M20 12a8 8 0 1 0-2 6',
  like: 'M7 10v11H3V10Zm0 0 5-8c3 0 2 5 2 7h6l-2 12H7',
  moon: 'M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  check: 'm5 12 4 4L19 6', stop: 'M6 6h12v12H6Z',
}
function Icon({ name, size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.spark} /></svg>
}
const suggestions = [
  { icon: 'book', title: 'Graduation requirements', text: 'Prepare for your next step', prompt: 'What are the requirements for graduation?', color: 'sage' },
  { icon: 'file', title: 'Student insurance', text: 'Find coverage information', prompt: 'Where can I find information about student insurance?', color: 'blue' },
  { icon: 'file', title: 'Campus guidelines', text: 'Understand university policies', prompt: 'What are the university guidelines for merchandise selling?', color: 'amber' },
  { icon: 'bulb', title: 'Find the right office', text: 'Get help with your concern', prompt: 'Which university office should I contact for my concern?', color: 'purple' },
]
function inline(text) { return text.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => part.startsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : part.startsWith('`') ? <code key={i}>{part.slice(1, -1)}</code> : part) }
function Markdown({ text, onCopy }) {
  return text.split(/(```[\s\S]*?```)/g).map((block, i) => {
    if (block.startsWith('```')) {
      const [language, ...lines] = block.slice(3, -3).trim().split('\n')
      return <div className="code-block" key={i}><div><span>{language}</span><button onClick={() => onCopy(lines.join('\n'))}><Icon name="copy" size={14} /> Copy code</button></div><pre><code>{lines.join('\n')}</code></pre></div>
    }
    return block.split('\n\n').filter(Boolean).map((part, j) => {
      if (part.startsWith('|')) return <div className="table-wrap" key={`${i}-${j}`}><table><tbody>{part.split('\n').filter(row => !/^\|[\s:|-]+\|$/.test(row)).map((row, k) => <tr key={k}>{row.split('|').slice(1, -1).map((cell, n) => k === 0 ? <th key={n}>{inline(cell.trim())}</th> : <td key={n}>{inline(cell.trim())}</td>)}</tr>)}</tbody></table></div>
      if (part.startsWith('### ')) return <h3 key={`${i}-${j}`}>{part.slice(4)}</h3>
      if (part.startsWith('- ')) return <ul key={`${i}-${j}`}>{part.split('\n').map((line, k) => <li key={k}>{inline(line.replace(/^- /, ''))}</li>)}</ul>
      return <p key={`${i}-${j}`}>{inline(part)}</p>
    })
  })
}
function App() {
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('aiok-theme') || 'light' } catch { return 'light' } })
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [generating, setGenerating] = useState(false)
  const [settings, setSettings] = useState(false)
  const [notice, setNotice] = useState('')
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const input = useRef(null), bottom = useRef(null), request = useRef(null), recognition = useRef(null), dialog = useRef(null), settingsButton = useRef(null)
  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem('aiok-theme', theme) } catch { /* Storage may be disabled. */ } }, [theme])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, generating])
  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(''), 3500); return () => clearTimeout(id) }, [notice])
  useEffect(() => () => { request.current?.abort(); recognition.current?.abort() }, [])
  useEffect(() => { if (settings) dialog.current?.showModal(); else dialog.current?.close() }, [settings])
  function stop() { request.current?.abort(); request.current = null; setGenerating(false) }
  async function generate(history) {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setGenerating(true); setError('')
    const exchanges = []
    for (let i = 1; i < history.length - 1; i++) {
      if (history[i].role === 'assistant' && history[i - 1].role === 'user') {
        exchanges.push([history[i - 1].text, history[i].text])
      }
    }
    try {
      const response = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: history.at(-1).text, history: exchanges.slice(-5) }),
        signal: controller.signal,
      })
      const result = await response.json().catch(() => { throw new Error('The chat API is unavailable. Check that the backend is running.') })
      if (!response.ok) throw new Error(result.error || 'Unable to get an answer. Please retry.')
      if (typeof result.answer !== 'string') throw new Error('The backend returned an invalid answer.')
      if (request.current !== controller) return
      setMessages([...history, { id: crypto.randomUUID(), role: 'assistant', text: result.answer, sources: result.sources || [] }])
      if (result.saved === false) setNotice('Answer received, but chat history could not be saved.')
    } catch (cause) {
      if (cause.name !== 'AbortError' && request.current === controller) setError(cause.message || 'Unable to connect to the backend.')
    } finally {
      if (request.current === controller) { request.current = null; setGenerating(false) }
    }
  }
  function send(event) {
    event?.preventDefault()
    if (generating || !draft.trim()) return
    const next = [...messages, { id: crypto.randomUUID(), role: 'user', text: draft.trim() }]
    setMessages(next); setDraft(''); generate(next)
    if (input.current) input.current.style.height = 'auto'
  }
  async function copy(text) { try { await navigator.clipboard.writeText(text); setNotice('Copied to clipboard') } catch { setNotice('Clipboard access is unavailable in this browser.') } }
  function voice() {
    if (listening) { recognition.current?.stop(); return }
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!Speech) { setNotice('Voice input is not supported in this browser. Try Chrome.'); return }
    const speech = new Speech(); recognition.current = speech; speech.lang = 'en-US'
    speech.onresult = event => setDraft(current => `${current} ${event.results[0][0].transcript}`.trim())
    speech.onend = () => setListening(false)
    speech.onerror = () => { setListening(false); setNotice('Microphone unavailable. Check your browser permissions.') }
    try { speech.start(); setListening(true) } catch { setNotice('Unable to start voice input.') }
  }
  function exportChat() {
    const blob = new Blob([messages.map(m => `## ${m.role === 'user' ? 'You' : 'AIOK'}\n\n${m.text}`).join('\n\n')], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'aiok-conversation.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <div className="app">
    <header className="topbar">
      <a className="brand" href="./" aria-label="AIOK home"><span>aiok</span></a>
      <nav aria-label="Chat controls"><button className="new-chat" onClick={() => { stop(); recognition.current?.abort(); setMessages([]); setDraft(''); setError(''); input.current?.focus() }}><Icon name="plus" size={17} /><span>New chat</span></button><span className="nav-divider" /><button className="icon-button" aria-label="Settings" ref={settingsButton} onClick={() => setSettings(true)}><Icon name="settings" /></button><span className="avatar" aria-label="Guest user">Y</span></nav>
    </header>
    <main className="conversation" aria-label="Conversation">
      {!messages.length ? <section className="welcome">

        <h1>Your university.<br /><span>A little easier to navigate.</span></h1>
        <p className="welcome-copy">Hi, what can I help you find today?<br /><span>Your guide to university requirements, policies, and services.</span></p>
        <div className="suggestions">{suggestions.map(item => <button className="suggestion" key={item.title} onClick={() => { setDraft(item.prompt); input.current?.focus() }}><span className={`suggestion-icon ${item.color}`}><Icon name={item.icon} /></span><strong>{item.title}</strong><span>{item.text}</span><span className="card-arrow">↗</span></button>)}</div>
        <p className="welcome-hint">Designed to answer from the university’s locally saved knowledge base.</p>
      </section> : <div className="message-list">{messages.map((message, index) => <article className={`message ${message.role}`} key={message.id}>
        <div className="message-label">{message.role === 'assistant' && <span className="mini-mark"><Icon name="spark" size={16} /></span>}{message.role === 'user' ? 'You' : 'AIOK'}</div>
        <div className="message-body">{message.role === 'assistant' ? <Markdown text={message.text} onCopy={copy} /> : message.text}</div>
        {message.sources?.length > 0 && <details className="sources"><summary>Sources ({message.sources.length})</summary><ul>{message.sources.map((source, i) => <li key={i}>{source.source || 'Unknown source'}{source.page != null && source.page >= 0 ? ` · page ${source.page}` : ''}{source.headings ? ` · ${source.headings}` : ''}</li>)}</ul></details>}
        {message.role === 'assistant' && <div className="message-actions"><button aria-label="Copy response" title="Copy response" onClick={() => copy(message.text)}><Icon name="copy" size={16} /></button>{['up', 'down'].map(vote => <button key={vote} aria-label={vote === 'up' ? 'Like response' : 'Dislike response'} aria-pressed={message.vote === vote} className={vote === 'down' ? 'dislike' : ''} onClick={() => setMessages(current => current.map(m => m.id === message.id ? { ...m, vote: m.vote === vote ? null : vote } : m))}><Icon name="like" size={16} /></button>)}{index === messages.length - 1 && <button disabled={generating} aria-label="Regenerate response" title="Regenerate response" onClick={() => { const history = messages.slice(0, -1); setMessages(history); generate(history) }}><Icon name="retry" size={16} /></button>}</div>}
      </article>)}{generating && <div className="loading" role="status"><span className="mini-mark"><Icon name="spark" size={16} /></span><span className="dots"><i /><i /><i /></span><span>Thinking it through</span></div>}<div ref={bottom} /></div>}
    </main>
    <footer className="composer-footer"><div className="composer-container">
      {error && <p className="request-error" role="alert">{error}</p>}
      {!generating && messages.at(-1)?.role === 'user' && <button className="retry-request" onClick={() => generate(messages)}>Retry last question</button>}
      <form className="composer" onSubmit={send}>
        <textarea ref={input} value={draft} rows={1} placeholder="Ask about university information..." aria-label="Ask about university information" onChange={event => { setDraft(event.target.value); event.target.style.height = 'auto'; event.target.style.height = `${Math.min(event.target.scrollHeight, 160)}px` }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send() } }} />
        <div className="composer-toolbar"><div className="composer-left"><span className="preview-mode"><span />Local knowledge base</span></div><div className="composer-right"><span className="enter-hint">Enter to send</span><button type="button" className={`icon-button ${listening ? 'listening' : ''}`} aria-label={listening ? 'Stop recording' : 'Use microphone'} onClick={voice}><Icon name="mic" /></button><button className="send-button" type={generating ? 'button' : 'submit'} disabled={!generating && !draft.trim()} onClick={generating ? stop : undefined} aria-label={generating ? 'Stop generating' : 'Send message'}><Icon name={generating ? 'stop' : 'arrow'} size={20} /></button></div></div>
      </form><p className="disclaimer">AI can make mistakes. Confirm important details with the relevant university office.</p><div className="footer-note"></div>
    </div></footer>
    <dialog ref={dialog} onCancel={() => setSettings(false)} onClose={() => { setSettings(false); settingsButton.current?.focus() }} onClick={event => { if (event.target === dialog.current) setSettings(false) }}><div className="settings-heading"><h2>Assistant settings</h2><button className="icon-button" aria-label="Close settings" onClick={() => setSettings(false)}><Icon name="close" /></button></div><p>Choose how you use your university assistant.</p><div className="setting-row"><span><Icon name="moon" />Appearance</span><select aria-label="Color theme" value={theme} onChange={event => setTheme(event.target.value)}><option value="light">Light</option><option value="dark">Dark</option></select></div><button className="export-button" onClick={exportChat} disabled={!messages.length}><Icon name="download" size={18} />Export conversation</button><div className="settings-note"><strong>Connected to your local RAG pipeline</strong><p>Answers use the indexed university documents. Completed exchanges are saved on the backend. New chat resets the conversation context. Voice input uses your browser’s speech service. Feedback is kept for this session.</p></div></dialog>
    {notice && <div className="toast" role="status">{notice}</div>}
  </div>
}
export default App
