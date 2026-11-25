import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import Admin, { AdminAccess } from './Admin'
import AnswerAudio from './AnswerAudio'
import ConfirmDialog from './ConfirmDialog'
import TouchKeyboard from './TouchKeyboard'
import { createVoiceInput } from './voiceInput'
import './App.css'

const paths = {
  keyboard: 'M2 6h20v12H2ZM6 10h1m4 0h1m4 0h1M7 14h10',
  plus: 'M12 5v14M5 12h14', arrow: 'M12 19V5m-6 6 6-6 6 6',
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
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  check: 'm5 12 4 4L19 6', stop: 'M6 6h12v12H6Z',
}
function SchoolLogo({ size = 20 }) {
  return <img src={`${import.meta.env.BASE_URL}cebu-institute-of-technology-cebu-city-logo-21A3C50219-seeklogo.com-1717624782.png`} width={size} height={size} style={{ objectFit: 'contain' }} alt="Cebu Institute of Technology logo" />
}
function Icon({ name, size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.book} /></svg>
}
const suggestions = [
  { icon: 'book', prompt: 'What are the requirements for graduation?' },
  { icon: 'file', prompt: 'Where can I find information about student insurance?' },
  { icon: 'file', prompt: 'What are the university guidelines for merchandise selling?' },
  { icon: 'bulb', prompt: 'Which university office should I contact for my concern?' },
]
function inline(text) { return text.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => part.startsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : part.startsWith('`') ? <code key={i}>{part.slice(1, -1)}</code> : part) }
function renderMarkdownBlocks(text, keyPrefix) {
  const lines = text.split('\n')
  const blocks = []
  let paragraph = []
  const flushParagraph = () => {
    if (paragraph.length) blocks.push(<p key={`${keyPrefix}-p-${blocks.length}`}>{inline(paragraph.join(' '))}</p>)
    paragraph = []
  }
  for (let i = 0; i < lines.length;) {
    const line = lines[i]
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/)
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      flushParagraph()
      const isOrdered = Boolean(ordered)
      const items = []
      while (i < lines.length) {
        const match = lines[i].match(isOrdered ? /^\s*(\d+)[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/)
        if (!match) break
        items.push({ number: isOrdered ? Number(match[1]) : null, text: isOrdered ? match[2] : match[1] })
        i++
      }
      const List = isOrdered ? 'ol' : 'ul'
      blocks.push(<List key={`${keyPrefix}-list-${blocks.length}`} start={isOrdered ? items[0]?.number : undefined}>{items.map((item, n) => <li key={n}>{inline(item.text)}</li>)}</List>)
      continue
    }
    if (!line.trim()) { flushParagraph(); i++; continue }
    if (/^#{1,3}\s/.test(line)) {
      flushParagraph()
      const depth = Math.min(line.match(/^#+/)[0].length, 3)
      const Heading = `h${depth}`
      blocks.push(<Heading key={`${keyPrefix}-h-${blocks.length}`}>{inline(line.replace(/^#{1,3}\s+/, ''))}</Heading>)
      i++; continue
    }
    paragraph.push(line.trim())
    i++
  }
  flushParagraph()
  return blocks
}
function Markdown({ text, onCopy }) {
  return text.split(/(```[\s\S]*?```)/g).map((block, i) => {
    if (block.startsWith('```')) {
      const [language, ...lines] = block.slice(3, -3).trim().split('\n')
      return <div className="code-block" key={i}><div><span>{language}</span><button onClick={() => onCopy(lines.join('\n'))}><Icon name="copy" size={14} /> Copy code</button></div><pre><code>{lines.join('\n')}</code></pre></div>
    }
    return block.split('\n\n').filter(Boolean).flatMap((part, j) => {
      if (part.startsWith('|')) return <div className="table-wrap" key={`${i}-${j}`}><table><tbody>{part.split('\n').filter(row => !/^\|[\s:|-]+\|$/.test(row)).map((row, k) => <tr key={k}>{row.split('|').slice(1, -1).map((cell, n) => k === 0 ? <th key={n}>{inline(cell.trim())}</th> : <td key={n}>{inline(cell.trim())}</td>)}</tr>)}</tbody></table></div>
      return renderMarkdownBlocks(part, `${i}-${j}`)
    })
  })
}
function App() {
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [keyboardOpen, setKeyboardOpen] = useState(false)
  const pendingCaret = useRef(null)
  const [generating, setGenerating] = useState(false)
  const [adminToken, setAdminToken] = useState(null)
  const [settings, setSettings] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [notice, setNotice] = useState('')
  const [voiceState, setVoiceState] = useState('idle')
  const listening = voiceState === 'recording'
  const voiceBusy = voiceState !== 'idle'
  const [error, setError] = useState('')
  const audioPlayers = useRef(new Set())
  const audioUrls = useRef(new Set())
  const input = useRef(null), latestMessage = useRef(null)
  const request = useRef(null), recognition = useRef(null), dialog = useRef(null), settingsButton = useRef(null)
  const nextMessageId = useRef(0)
  const followConversation = useRef(true)
  const speechRequest = useRef(null)
  const latestMessageId = messages.at(-1)?.id
  const hasCustomDraft = Boolean(draft.trim()) && !suggestions.some(item => item.prompt === draft)
  useLayoutEffect(() => {
    if (followConversation.current) latestMessage.current?.scrollIntoView({ block: 'start' })
  }, [latestMessageId])
  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(''), 3500); return () => clearTimeout(id) }, [notice])
  useEffect(() => () => {
    request.current?.abort()
    speechRequest.current?.abort()
    recognition.current?.cancel()
    audioUrls.current.forEach(url => URL.revokeObjectURL(url))
  }, [])
  useEffect(() => { if (settings) dialog.current?.showModal(); else dialog.current?.close() }, [settings])
  useLayoutEffect(() => {
    const field = input.current
    if (!field) return
    field.style.height = 'auto'
    field.style.height = `${field.scrollHeight}px`
    if (pendingCaret.current !== null) {
      field.setSelectionRange(pendingCaret.current, pendingCaret.current)
      pendingCaret.current = null
    }
  }, [draft, keyboardOpen])
  function typeKey(key) {
    const field = input.current
    if (!field) return
    let start = field.selectionStart
    const end = field.selectionEnd
    if (key === 'Backspace' && start === end) {
      // Remove a whole Unicode character when deleting before the caret.
      start -= Array.from(draft.slice(0, start)).at(-1)?.length || 0
    }
    const insertion = key === 'Backspace' ? '' : key
    const next = draft.slice(0, start) + insertion + draft.slice(end)
    const caret = start + insertion.length
    if (next === draft) field.setSelectionRange(caret, caret)
    else {
      pendingCaret.current = caret
      setDraft(next)
    }
  }
  function hideKeyboard() {
    setKeyboardOpen(false)
    input.current?.focus({ preventScroll: true })
  }
  function stopAudio() {
    audioPlayers.current.forEach(audio => audio.pause())
    speechRequest.current?.abort()
    speechRequest.current = null
  }
  function stop() { stopAudio(); request.current?.abort(); request.current = null; setGenerating(false) }
  async function speak(messageId, text) {
    const controller = new AbortController()
    speechRequest.current = controller
    try {
      const response = await fetch('/api/tts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }), signal: controller.signal,
      })
      if (!response.ok) {
        const result = await response.json().catch(() => ({}))
        throw new Error(result.error || 'Speech is unavailable. You can still read the answer.')
      }
      if (!response.headers.get('content-type')?.includes('audio/wav')) {
        throw new Error('The speech service returned an invalid audio file.')
      }
      const url = URL.createObjectURL(await response.blob())
      if (speechRequest.current !== controller || controller.signal.aborted) {
        URL.revokeObjectURL(url)
        return
      }
      audioUrls.current.add(url)
      setMessages(current => current.map(message => message.id === messageId
        ? { ...message, audio: url, audioError: null } : message))
    } catch (cause) {
      if (cause.name !== 'AbortError' && speechRequest.current === controller) {
        setMessages(current => current.map(message => message.id === messageId
          ? { ...message, audioError: cause.message || 'Speech is unavailable. You can still read the answer.' } : message))
      }
    } finally {
      if (speechRequest.current === controller) speechRequest.current = null
    }
  }
  async function generate(history) {
    if (request.current) return
    stopAudio()
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
      const answer = {
        id: ++nextMessageId.current, role: 'assistant', text: result.answer, sources: result.sources || [],
        messageId: Number.isInteger(result.message_id) ? result.message_id : null,
        vote: null, audio: null, audioError: null,
      }
      setMessages([...history, answer])
      if (result.saved === false) setNotice('Answer received, but chat history could not be saved.')
      speak(answer.id, answer.text)
    } catch (cause) {
      if (cause.name !== 'AbortError' && request.current === controller) setError(cause.message || 'Unable to connect to the backend.')
    } finally {
      if (request.current === controller) { request.current = null; setGenerating(false) }
    }
  }
  function send(event) {
    event?.preventDefault()
    if (request.current || voiceBusy || !draft.trim()) return
    const next = [...messages, { id: ++nextMessageId.current, role: 'user', text: draft.trim() }]
    followConversation.current = true
    setKeyboardOpen(false)
    input.current?.focus({ preventScroll: true })
    setMessages(next); setDraft(''); generate(next)
  }
  async function copy(text) { try { await navigator.clipboard.writeText(text); setNotice('Copied to clipboard') } catch { setNotice('Clipboard access is unavailable in this browser.') } }
  async function vote(message, vote) {
    const feedback = message.vote === vote ? null : vote
    if (!message.messageId) { setNotice('This response was not saved, so feedback could not be recorded.'); return }
    try {
      const response = await fetch('/api/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: message.messageId, feedback }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || 'Could not save feedback.')
      setMessages(current => current.map(item => item.id === message.id ? { ...item, vote: feedback } : item))
      setNotice(feedback ? 'Feedback saved' : 'Feedback cleared')
    } catch (cause) { setNotice(cause.message || 'Could not save feedback.') }
  }
  function voteResponse(message, selectedVote) { vote(message, selectedVote) }
  function cancelVoice() {
    recognition.current?.cancel()
    recognition.current = null
    setVoiceState('idle')
  }
  function newChat() {
    // Invalidate pending work before clearing the history used as model context.
    stop()
    cancelVoice()
    audioUrls.current.forEach(url => URL.revokeObjectURL(url))
    audioUrls.current.clear()
    setMessages([])
    setDraft('')
    setError('')
    setNotice('')
    setKeyboardOpen(false)
    followConversation.current = true
    if (confirmReset) {
      setConfirmReset(false)
      // Let the native dialog restore focus before moving it to the composer.
      requestAnimationFrame(() => input.current?.focus({ preventScroll: true }))
    } else input.current?.focus({ preventScroll: true })
  }
  function requestNewChat() {
    if (messages.length || draft || voiceBusy) setConfirmReset(true)
    else newChat()
  }
  function toggleKeyboard() {
    setKeyboardOpen(open => !open)
    input.current?.focus({ preventScroll: true })
  }
  function clearDraft() {
    pendingCaret.current = null
    setDraft('')
    input.current?.focus({ preventScroll: true })
  }
  function voice() {
    if (recognition.current) {
      if (listening) recognition.current.stop()
      else cancelVoice()
      return
    }
    stopAudio()
    const session = createVoiceInput({
      onState: state => {
        if (recognition.current !== session) return
        setVoiceState(state)
        if (state === 'idle') recognition.current = null
      },
      onText: text => {
        setDraft(current => `${current}${current && !/\s$/.test(current) ? ' ' : ''}${text}`)
        input.current?.focus()
      },
      onError: setNotice,
    })
    recognition.current = session
    session.start()
  }
  if (adminToken) return <Admin token={adminToken} onExit={() => {
    setAdminToken(null)
    requestAnimationFrame(() => settingsButton.current?.focus())
  }} />
  return <div className={`app${keyboardOpen ? ' keyboard-open' : ''}`}>
    <header className="topbar">
      <span className="brand">AIOK</span>
      <nav aria-label="Chat controls">
        <button className="new-chat secondary-button" onClick={requestNewChat}><Icon name="plus" size={17} />New chat</button>
        <button className="icon-button" aria-label="Administrator access" title="Administrator access" ref={settingsButton} onClick={() => setSettings(true)}><Icon name="settings" /></button>
      </nav>
    </header>
    <main className="conversation" aria-label="Conversation" tabIndex={0} onScroll={event => {
      const { scrollHeight, scrollTop, clientHeight } = event.currentTarget
      followConversation.current = scrollHeight - scrollTop - clientHeight < 48
    }}>
      {!messages.length ? <section className="welcome">

        <h1>University assistant</h1>
        <p className="welcome-copy">Ask about requirements, policies, and campus services.</p>
        <div className="suggestions" role="group" aria-label="Suggested questions">{suggestions.map(item =>
          <button className="suggestion" key={item.prompt} disabled={hasCustomDraft} onClick={() => {
            setDraft(item.prompt)
            input.current?.focus({ preventScroll: true })
          }}><Icon name={item.icon} size={18} /><span>{item.prompt}</span></button>
        )}</div>
      </section> : <div className="message-list" role="log" aria-label="Chat messages" aria-relevant="additions">{messages.map((message, index) => <article className={`message ${message.role}`} key={message.id} ref={index === messages.length - 1 ? latestMessage : undefined}>
        <div className="message-label">{message.role === 'assistant' && <span className="mini-mark"><SchoolLogo size={24} /></span>}{message.role === 'user' ? 'You' : 'AIOK'}</div>
        <div className="message-body">{message.role === 'assistant' ? <Markdown text={message.text} onCopy={copy} /> : message.text}</div>
        {message.audio && <AnswerAudio src={message.audio} players={audioPlayers} />}
        {message.audioError && <p role="status">{message.audioError}</p>}
        {message.sources?.length > 0 && <details className="sources"><summary>Sources ({message.sources.length})</summary><ul>{message.sources.map((source, i) => <li key={i}>{source.source || 'Unknown source'}{source.page != null && source.page >= 0 ? ` · page ${source.page}` : ''}{source.headings ? ` · ${source.headings}` : ''}</li>)}</ul></details>}
        {message.role === 'assistant' && <div className="message-actions"><button aria-label="Copy response" title="Copy response" onClick={() => copy(message.text)}><Icon name="copy" size={16} /></button>{['like', 'dislike'].map(vote => <button key={vote} aria-label={vote === 'like' ? 'Like response' : 'Dislike response'} title={vote === 'like' ? 'Like response' : 'Dislike response'} aria-pressed={message.vote === vote} className={vote === 'dislike' ? 'dislike' : ''} onClick={() => voteResponse(message, vote)}><Icon name="like" size={16} /></button>)}{index === messages.length - 1 && <button disabled={generating || voiceBusy} aria-label="Regenerate response" title="Regenerate response" onClick={() => generate(messages.slice(0, -1))}><Icon name="retry" size={16} /></button>}</div>}
      </article>)}</div>}
    </main>
    <footer className="composer-footer"><div className="composer-container">
      {error && <p className="request-error" role="alert">{error}</p>}
      {!generating && messages.at(-1)?.role === 'user' && <button className="retry-request secondary-button" disabled={voiceBusy} onClick={() => generate(messages)}>Retry last question</button>}
      <div className="composer-status" role="status">{generating ? 'Preparing an answer…' : listening ? 'Listening… Select the microphone to stop (30 seconds maximum).' : voiceState === 'starting' ? 'Opening microphone…' : voiceBusy ? 'Transcribing…' : ''}</div>
      <form className="composer" onSubmit={send}>
        <textarea ref={input} value={draft} rows={1} inputMode="none" placeholder="Ask a university question…" aria-label="Your question"
          onClick={() => setKeyboardOpen(true)}
          onChange={event => setDraft(event.target.value)} onKeyDown={event => {
            if (event.key === 'Escape' && keyboardOpen) hideKeyboard()
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send() }
          }} />
        <div className="composer-toolbar">
          <span className="enter-hint">Enter to send · Shift+Enter for a new line</span>
          <div className="composer-right">
            <button type="button" className="secondary-button clear-draft" aria-label="Clear question" disabled={!draft} onClick={clearDraft}>Clear</button>
            <button type="button" className={`icon-button ${listening ? 'listening' : ''}`} aria-label={listening ? 'Stop recording' : voiceBusy ? 'Cancel voice input' : 'Use microphone'} aria-pressed={voiceBusy} title={listening ? 'Stop recording' : voiceBusy ? 'Cancel voice input' : 'Start recording'} disabled={generating} onClick={voice}><Icon name="mic" /></button>
            <button type="button" className="icon-button keyboard-toggle" aria-label="On-screen keyboard" title="On-screen keyboard" aria-expanded={keyboardOpen} aria-controls={keyboardOpen ? 'touch-keyboard' : undefined} onClick={toggleKeyboard}><Icon name="keyboard" /></button>
            <button className="primary-button send-button" type={generating ? 'button' : 'submit'} disabled={!generating && (voiceBusy || !draft.trim())} onClick={generating ? () => { stop(); setNotice('Answer stopped') } : undefined} aria-label={generating ? 'Stop generating' : 'Send message'}><Icon name={generating ? 'stop' : 'arrow'} size={18} />{generating ? 'Stop' : 'Send'}</button>
          </div>
        </div>
      </form><p className="disclaimer">AI can make mistakes. Confirm important details with the relevant university office.</p>
    </div></footer>
    {keyboardOpen && <TouchKeyboard onKey={typeKey} onHide={hideKeyboard} />}
    {confirmReset && <ConfirmDialog title="Start a new chat?" action="Start new chat" onConfirm={newChat} onCancel={() => setConfirmReset(false)}>
      This clears the current conversation and any unfinished question from this screen.
    </ConfirmDialog>}
    <dialog className="settings-dialog" aria-labelledby="settings-title" ref={dialog} onCancel={() => setSettings(false)} onClose={() => { setSettings(false); settingsButton.current?.focus() }} onClick={event => { if (event.target === dialog.current) setSettings(false) }}>
      <div className="settings-heading"><h2 id="settings-title">Administrator access</h2><button className="icon-button" aria-label="Close settings" onClick={() => setSettings(false)}><Icon name="close" /></button></div>
      {settings && <AdminAccess onAuthorize={token => { stop(); cancelVoice(); setKeyboardOpen(false); setSettings(false); setAdminToken(token) }} />}
    </dialog>
      {notice && <div className="toast" role="status">{notice}</div>}
  </div>
}
export default App
