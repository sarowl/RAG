import { useEffect, useRef, useState } from 'react'

import { adminRequest } from './adminApi'
import ConfirmDialog from './ConfirmDialog'

const HISTORY_PAGE_SIZE = 15
const LEGACY_HISTORY_LIMIT = 1000
const VISIBLE_PAGE_COUNT = 8

async function requestHistoryPage(token, { page, through }, signal) {
  const query = new URLSearchParams({ limit: HISTORY_PAGE_SIZE, page })
  if (through !== null) query.set('through', through)
  const data = await adminRequest(`history?${query}`, token, { signal })
  if (Object.hasOwn(data, 'page_count')) return data

  // Older admin servers return only the latest records.
  const { records } = data.records.length >= HISTORY_PAGE_SIZE
    ? await adminRequest(`history?limit=${LEGACY_HISTORY_LIMIT}`, token, { signal })
    : data
  const snapshot = through ?? records[0]?.id ?? 0
  const matching = records.filter(record => record.id <= snapshot)
  const pageCount = Math.max(1, Math.ceil(matching.length / HISTORY_PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const offset = (currentPage - 1) * HISTORY_PAGE_SIZE
  return {
    records: matching.slice(offset, offset + HISTORY_PAGE_SIZE),
    page: currentPage,
    page_count: pageCount,
    through: snapshot,
  }
}

export function AdminAccess({ onAuthorize }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function login(event) {
    event.preventDefault()
    if (busy || !pin) return
    setBusy(true); setError('')
    try {
      const result = await adminRequest('login', null, { method: 'POST', body: JSON.stringify({ pin }) })
      setPin(''); onAuthorize(result.token)
    } catch (cause) { setError(cause.message) }
    finally { setBusy(false) }
  }
  function changePin(value) {
    setPin(value.slice(0, 128))
    setError('')
  }
  return <form className="admin-access" onSubmit={login} aria-busy={busy}>
    <p id="admin-pin-help">Enter your PIN to manage the knowledge base.</p>
    <label htmlFor="admin-pin">Administrator PIN</label>
    <input id="admin-pin" type="password" inputMode="numeric" autoComplete="off" placeholder="Enter PIN" aria-describedby="admin-pin-help" aria-invalid={Boolean(error)} value={pin} onChange={event => changePin(event.target.value)} disabled={busy} required maxLength={128} />
    <div className="admin-numpad" role="group" aria-label="PIN keypad">
      {['7', '8', '9', '4', '5', '6', '1', '2', '3'].map(digit => <button type="button" className="secondary-button" key={digit} disabled={busy || pin.length >= 128} onClick={() => changePin(pin + digit)}>{digit}</button>)}
      <button type="button" className="secondary-button numpad-action" disabled={busy || !pin} onClick={() => changePin('')}>Clear</button>
      <button type="button" className="secondary-button" disabled={busy || pin.length >= 128} onClick={() => changePin(pin + '0')}>0</button>
      <button type="button" className="secondary-button numpad-action" aria-label="Delete last digit" disabled={busy || !pin} onClick={() => changePin(pin.slice(0, -1))}>Delete</button>
    </div>
    {error && <p className="request-error" role="alert">{error}</p>}
    <button className="primary-button admin-unlock" type="submit" disabled={busy || !pin}>{busy ? 'Unlocking…' : 'Unlock administration'}</button>
  </form>
}

export default function Admin({ token, onExit }) {
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [expired, setExpired] = useState(false)
  const [tab, setTab] = useState('documents')
  const [history, setHistory] = useState(null)
  const [historyLocation, setHistoryLocation] = useState({ page: 1, through: null })
  const [historyError, setHistoryError] = useState('')
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const heading = useRef(null)
  const historyHeading = useRef(null)
  const currentPage = history?.page ?? historyLocation.page
  const pageCount = history?.page_count
  const firstVisiblePage = Math.max(1, Math.min(currentPage - 3, (pageCount ?? 1) - VISIBLE_PAGE_COUNT + 1))
  const visiblePages = Array.from(
    { length: Math.min(pageCount ?? 0, VISIBLE_PAGE_COUNT) },
    (_, index) => firstVisiblePage + index,
  )
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => {
    if (expired) return
    const controller = new AbortController()
    const { signal } = controller
    let timer
    async function refresh() {
      try {
        const data = await adminRequest('files', token, { signal })
        if (!signal.aborted) { setSnapshot(data); setLoadError('') }
      } catch (cause) {
        if (!signal.aborted) { setLoadError(cause.message); if (cause.status === 401) setExpired(true) }
      } finally {
        if (!signal.aborted) timer = setTimeout(refresh, 2000)
      }
    }
    refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [token, expired])
  useEffect(() => {
    if (tab !== 'history' || expired) return
    const controller = new AbortController()
    const { signal } = controller
    let timer
    async function refreshHistory() {
      try {
        const data = await requestHistoryPage(token, historyLocation, signal)
        if (!signal.aborted) { setHistory(data); setHistoryError('') }
      } catch (cause) {
        if (!signal.aborted) { setHistoryError(cause.message); if (cause.status === 401) setExpired(true) }
      } finally {
        if (!signal.aborted) timer = setTimeout(refreshHistory, 5000)
      }
    }
    refreshHistory()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [tab, token, expired, historyRefresh, historyLocation])

  function changeHistoryPage(page) {
    if (!Number.isInteger(page) || page < 1 || !pageCount || page > pageCount || page === currentPage) return
    setHistory({ ...history, page, records: null })
    setHistoryError('')
    setHistoryLocation({ page, through: page === 1 ? null : history.through })
    historyHeading.current?.focus({ preventScroll: true })
    historyHeading.current?.scrollIntoView({ block: 'start' })
  }
  const jobState = loadError ? 'unavailable' : snapshot?.job.state || 'loading'
  const jobLabel = { unavailable: 'Unavailable', loading: 'Loading', idle: 'Ready', running: 'In progress', succeeded: 'Complete', failed: 'Failed' }[jobState] || 'Status'
  const disabled = busy || expired || Boolean(loadError) || !snapshot || snapshot.job.state === 'running'
  async function act(action, name) {
    setBusy(true); setError(''); setNotice(''); setConfirm(null)
    try {
      await adminRequest(action, token, { method: 'POST', body: JSON.stringify({ name }) })
      setSnapshot(await adminRequest('files', token))
    } catch (cause) { setError(cause.message); if (cause.status === 401) setExpired(true) }
    finally { setBusy(false) }
  }
  async function upload(event) {
    const files = Array.from(event.target.files)
    event.target.value = ''
    if (!files.length) return
    setNotice('')
    const invalid = files.find(file => !file.size || file.size > 25 * 1024 * 1024)
    if (invalid) {
      setError(`${invalid.name}: file must be between 1 byte and 25 MB.`)
      return
    }
    setBusy(true); setError('')
    let uploaded = 0
    try {
      for (const file of files) {
        await adminRequest(`upload?name=${encodeURIComponent(file.name)}`, token, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file })
        uploaded++
      }
      setSnapshot(await adminRequest('files', token))
    } catch (cause) { setError(cause.message); if (cause.status === 401) setExpired(true) }
    finally {
      setBusy(false)
      if (uploaded) setNotice(`${uploaded} ${uploaded === 1 ? 'file' : 'files'} uploaded. Run ingestion to update search.`)
    }
  }
  async function exit() {
    try { await adminRequest('logout', token, { method: 'POST', body: '{}' }) } catch { /* Local credentials are cleared even if the backend is offline. */ }
    onExit()
  }
  return <div className="app"><header className="topbar"><span className="brand">AIOK</span><nav aria-label="Administration controls"><button className="secondary-button" onClick={exit}>{expired ? 'Return to chat' : 'Lock and return to chat'}</button></nav></header>
    <main className="admin-page"><h1 ref={heading} tabIndex={-1}>Administration</h1><p>Manage the university documents and review student chat records.</p>
      {expired ? <p className="request-error" role="alert">Your administrator session expired. Return to chat and unlock administration again.</p> : <>
      <nav className="admin-tabs" aria-label="Administration sections">
        <button className="secondary-button" aria-pressed={tab === 'documents'} onClick={() => setTab('documents')}>Knowledge base</button>
        <button className="secondary-button" aria-pressed={tab === 'history'} onClick={() => setTab('history')}>Chat history</button>
      </nav>
      {tab === 'history' ? <section className="admin-panel" aria-labelledby="history-title">
        <div className="history-heading"><div><h2 id="history-title" ref={historyHeading} tabIndex={-1}>Student conversations</h2><p>TPS is tokens per second. TTFT is seconds to first token.</p></div><button className="secondary-button" onClick={() => setHistoryRefresh(count => count + 1)}>Refresh</button></div>
        {historyError && <p className="request-error" role="alert">{historyError}</p>}
        {history?.records == null ? (!historyError && <p role="status">Loading chat history…</p>) : history.records.length === 0 ? <p>No completed chat records yet.</p> :
          <div className="history-list">{history.records.map(record => <details className="history-record" key={record.id}>
            <summary>
              <span>
                <span className="history-question">{record.user_query}</span>
                <span className="history-meta"><time dateTime={record.created_at}>{new Date(record.created_at).toLocaleString()}</time> · {record.feedback === 'like' ? 'Liked' : record.feedback === 'dislike' ? 'Disliked' : 'No feedback'}</span>
              </span>
              <span className="history-metrics">
                <span>TPS</span><span>{record.tps == null ? '—' : Number(record.tps).toFixed(2)}</span>
                <span>TTFT</span><span>{record.ttft == null ? '—' : `${Number(record.ttft).toFixed(3)} s`}</span>
              </span>
            </summary>
            <div className="history-answer">
              <h3>AI response</h3><p>{record.llm_answer}</p>
            </div>
          </details>)}</div>}
        <nav className="history-pagination" aria-label="Chat history pagination">
          <button className="secondary-button" disabled={currentPage <= 1}
            onClick={() => changeHistoryPage(currentPage - 1)}>Previous</button>
          {visiblePages.map(page => <button
            key={page} type="button" className="secondary-button history-page-number"
            aria-label={`Page ${page} of ${pageCount}`}
            aria-current={page === currentPage ? 'page' : undefined}
            onClick={() => changeHistoryPage(page)}>{page}</button>)}
          <button className="secondary-button" disabled={!pageCount || currentPage >= pageCount}
            onClick={() => changeHistoryPage(currentPage + 1)}>Next</button>
        </nav>
      </section> : <>
      {error && <p className="request-error" role="alert">{error}</p>}
      {loadError && <p className="request-error" role="alert">Could not load the knowledge base. {loadError} Retrying automatically…</p>}
      {notice && <p role="status">{notice}</p>}
      <section className="admin-panel"><h2>Add documents</h2><p id="upload-help">PDF, DOCX, PPTX, or HTML · Up to 25 MB per file. Uploads become searchable after ingestion.</p><input className="admin-upload" aria-label="Upload knowledge-base files" aria-describedby="upload-help" type="file" accept=".pdf,.docx,.pptx,.html" multiple disabled={disabled} onChange={upload} />{busy && <p role="status">Working on your request…</p>}</section>
      <section className="admin-panel"><h2>Search index</h2><p>Ingest new or changed documents, or rebuild the entire index from the current files. Chat pauses while changes are applied.</p><div className="admin-actions"><button className="primary-button" disabled={disabled} onClick={() => act('ingest')}>Run ingestion</button><button className="secondary-button" disabled={disabled} onClick={() => setConfirm({ action: 'reset' })}>Reset & reingest</button></div><div className="admin-job-status" role="status"><strong>Search index status · {jobLabel}</strong>{!loadError && <p>{snapshot?.job.message || 'Loading knowledge base…'}</p>}</div></section>
      {confirm && <ConfirmDialog
        title={confirm.action === 'reset' ? 'Rebuild the search index?' : `Remove ${confirm.name}?`}
        action={confirm.action === 'reset' ? 'Reset & reingest' : 'Remove document'}
        disabled={disabled} onConfirm={() => act(confirm.action, confirm.name)} onCancel={() => setConfirm(null)}>
        {confirm.action === 'reset' ? 'This clears all indexed content and reingests the current documents. Source files are kept.' : 'This permanently deletes the source file and its indexed content.'}
      </ConfirmDialog>}
      <section className="admin-panel"><h2>Documents {snapshot && `(${snapshot.files.length})`}</h2>{!snapshot ? <p>{loadError ? 'Documents are unavailable.' : 'Loading documents…'}</p> : snapshot.files.length === 0 ? <p>No documents yet. Add files above to get started.</p> : <div className="table-wrap"><table><thead><tr><th scope="col">Filename</th><th scope="col">Size</th><th scope="col">Action</th></tr></thead><tbody>{snapshot.files.map(file => <tr key={file.name}><td>{file.name}</td><td>{Math.max(1, Math.round(file.size / 1024))} KB</td><td><button className="secondary-button" disabled={disabled} aria-label={`Remove ${file.name}`} onClick={() => setConfirm({ action: 'remove', name: file.name })}>Remove</button></td></tr>)}</tbody></table></div>}</section>
      </>}
      </>}
    </main></div>
}
