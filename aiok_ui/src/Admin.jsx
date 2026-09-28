import { useEffect, useState } from 'react'

import { adminRequest } from './adminApi'

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
      {['7', '8', '9', '4', '5', '6', '1', '2', '3'].map(digit => <button type="button" key={digit} disabled={busy || pin.length >= 128} onClick={() => changePin(pin + digit)}>{digit}</button>)}
      <button type="button" className="numpad-action" disabled={busy || !pin} onClick={() => changePin('')}>Clear</button>
      <button type="button" disabled={busy || pin.length >= 128} onClick={() => changePin(pin + '0')}>0</button>
      <button type="button" className="numpad-action" aria-label="Delete last digit" disabled={busy || !pin} onClick={() => changePin(pin.slice(0, -1))}>Delete</button>
    </div>
    {error && <p className="request-error" role="alert">{error}</p>}
    <button className="admin-unlock" type="submit" disabled={busy || !pin}>{busy ? 'Unlocking…' : 'Unlock administration'}</button>
  </form>
}

export default function Admin({ token, onExit }) {
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [expired, setExpired] = useState(false)
  useEffect(() => {
    let stopped = false
    async function refresh() {
      try {
        const data = await adminRequest('files', token)
        if (!stopped) { setSnapshot(data); setError('') }
      } catch (cause) {
        if (!stopped) { setError(cause.message); if (cause.status === 401) setExpired(true) }
      }
    }
    refresh()
    const timer = setInterval(refresh, 2000)
    return () => { stopped = true; clearInterval(timer) }
  }, [token])
  const disabled = busy || expired || !snapshot || snapshot.job.state === 'running'
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
    setBusy(true); setError(''); setNotice('')
    let uploaded = 0
    try {
      for (const file of files) {
        if (!file.size || file.size > 25 * 1024 * 1024) throw new Error(`${file.name}: file must be between 1 byte and 25 MB.`)
        await adminRequest(`upload?name=${encodeURIComponent(file.name)}`, token, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file })
        uploaded++
      }
      setSnapshot(await adminRequest('files', token))
    } catch (cause) { setError(cause.message); if (cause.status === 401) setExpired(true) }
    finally { setBusy(false); if (uploaded) setNotice(`${uploaded} file(s) uploaded. Run ingestion to make them searchable.`) }
  }
  async function exit() {
    try { await adminRequest('logout', token, { method: 'POST', body: '{}' }) } catch { /* Local credentials are cleared even if the backend is offline. */ }
    onExit()
  }
  return <div className="app"><header className="topbar"><strong>AIOK · Administration</strong><nav><button className="new-chat" onClick={exit}>Lock admin & return to chat</button></nav></header>
    <main className="admin-page"><h1>Knowledge base</h1><p>Manage the university documents used by the assistant.</p>
      {error && <p className="request-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <section className="admin-panel"><h2>Add documents</h2><p>PDF, DOCX, PPTX, or HTML · Up to 25 MB per file. Uploads become searchable after ingestion.</p><label className="admin-upload">Choose files<input aria-label="Upload knowledge-base files" type="file" accept=".pdf,.docx,.pptx,.html" multiple disabled={disabled} onChange={upload} /></label></section>
      <section className="admin-panel"><h2>Search index</h2><p>Ingest new or changed documents, or rebuild the entire index from the current files. Chat pauses while changes are applied.</p><div className="admin-actions"><button disabled={disabled} onClick={() => act('ingest')}>Run ingestion</button><button disabled={disabled} onClick={() => setConfirm({ action: 'reset' })}>Reset & reingest</button></div><p role="status">{snapshot?.job.message || 'Loading knowledge base…'}</p></section>
      {confirm && <section className="admin-panel" role="alert"><h2>{confirm.action === 'reset' ? 'Rebuild the search index?' : `Remove ${confirm.name}?`}</h2><p>{confirm.action === 'reset' ? 'This clears all indexed content and reingests the current documents. Source files are kept.' : 'This permanently deletes the source file and its indexed content.'}</p><div className="admin-actions"><button disabled={disabled} onClick={() => act(confirm.action, confirm.name)}>Confirm {confirm.action === 'reset' ? 'reset & reingest' : 'removal'}</button><button onClick={() => setConfirm(null)}>Cancel</button></div></section>}
      <section className="admin-panel"><h2>Documents {snapshot && `(${snapshot.files.length})`}</h2>{snapshot?.files.length === 0 ? <p>No documents yet. Add files above to get started.</p> : <div className="table-wrap"><table><thead><tr><th>Filename</th><th>Size</th><th>Action</th></tr></thead><tbody>{snapshot?.files.map(file => <tr key={file.name}><td>{file.name}</td><td>{Math.max(1, Math.round(file.size / 1024))} KB</td><td><button disabled={disabled} aria-label={`Remove ${file.name}`} onClick={() => setConfirm({ action: 'remove', name: file.name })}>Remove</button></td></tr>)}</tbody></table></div>}</section>
    </main></div>
}
