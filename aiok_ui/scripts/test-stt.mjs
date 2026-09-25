// Run after npm run build: node scripts/test-stt.mjs [chromium-path]
// Uses a temporary browser profile and a stub chat API with a valid WAV file.
import { createServer } from 'node:http'
import { readFile, mkdtemp, rm } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join, extname } from 'node:path'
import assert from 'node:assert/strict'

const dist = new URL('../dist/', import.meta.url)
let mode = 'text'
let uploads = 0
const server = createServer(async (req, res) => {
  if (req.url === '/api/stt') {
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    const audio = Buffer.concat(chunks)
    assert.equal(audio.toString('ascii', 0, 4), 'RIFF')
    assert.equal(audio.readUInt16LE(22), 1)
    assert.equal(audio.readUInt16LE(34), 16)
    assert.ok(audio.length > 44)
    uploads++
    res.setHeader('Content-Type', 'application/json')
    if (mode === 'delay') await new Promise(resolve => setTimeout(resolve, 500))
    res.statusCode = mode === 'error' ? 503 : 200
    res.end(JSON.stringify(mode === 'error' ? { error: 'Voice input is unavailable.' } : { text: mode === 'empty' ? '' : 'recognized question' }))
    return
  }
  try {
    const path = req.url === '/' ? 'index.html' : req.url.slice(1)
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }[extname(path)] || 'application/octet-stream')
    res.end(await readFile(new URL(path, dist)))
  } catch { res.writeHead(404).end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const profile = await mkdtemp(join(tmpdir(), 'aiok-audio-test-'))
const browser = spawn(process.argv[2] || 'chromium', ['--headless', '--no-sandbox', '--disable-gpu', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--remote-debugging-port=0', '--autoplay-policy=no-user-gesture-required', `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] })
let socket
const timeout = setTimeout(() => { console.error('Browser test timed out'); browser.kill(); process.exitCode = 1 }, 30000)
try {
  const endpoint = await new Promise((resolve, reject) => {
    let output = ''
    browser.on('error', reject)
    browser.on('exit', code => reject(new Error(`Chromium exited: ${code}`)))
    browser.stderr.on('data', chunk => { output += chunk; const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) resolve(match[1]) })
  })
  const targets = await (await fetch(`http://${new URL(endpoint).host}/json`)).json()
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  let id = 0
  const pending = new Map()
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id) }
  })
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    pending.set(++id, message => message.error ? reject(message.error) : resolve(message.result))
    socket.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
    return result.result.value
  }
  const waitFor = async expression => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return
      await new Promise(resolve => setTimeout(resolve, 50))
    }
    throw new Error(`Condition failed: ${expression}`)
  }
  await call('Page.navigate', { url: `http://127.0.0.1:${server.address().port}` })
  await waitFor('!!document.querySelector(".suggestion")')
  const clickMic = () => evaluate(`document.querySelector('.composer .icon-button').click()`)
  const record = async () => {
    await clickMic()
    await waitFor(`document.querySelector('.listening') !== null`)
    await new Promise(resolve => setTimeout(resolve, 250))
    await clickMic()
    await waitFor(`document.querySelector('[aria-label="Use microphone"]') !== null`)
  }
  await evaluate('document.querySelector(".suggestion").click()')
  await record()
  assert.equal(await evaluate('document.querySelector("textarea").value'), 'What are the requirements for graduation? recognized question')
  assert.equal(uploads, 1)
  await evaluate('document.querySelector(".new-chat").click()')
  await clickMic()
  await waitFor(`document.querySelector('.listening') !== null`)
  await evaluate('document.querySelector(".new-chat").click()')
  assert.equal(await evaluate('document.querySelector("textarea").value'), '')
  assert.equal(uploads, 1)
  for (const value of ['empty', 'error']) {
    mode = value
    await record()
    const expected = value === 'empty' ? 'No speech recognized' : 'Voice input is unavailable'
    await waitFor(`document.body.textContent.includes(${JSON.stringify(expected)})`)
    assert.equal(await evaluate('document.querySelector("textarea").value'), '')
  }
  mode = 'delay'
  await clickMic()
  await waitFor(`document.querySelector('.listening') !== null`)
  await new Promise(resolve => setTimeout(resolve, 250))
  await clickMic()
  await waitFor(`document.body.textContent.includes('Transcribing')`)
  await evaluate('document.querySelector(".new-chat").click()')
  await new Promise(resolve => setTimeout(resolve, 750))
  assert.equal(await evaluate('document.querySelector("textarea").value'), '')
  await evaluate(`navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('Denied', 'NotAllowedError'))`)
  await clickMic()
  await waitFor(`document.body.textContent.includes('Microphone access was denied')`)
  console.log('PASS: microphone toggle, WAV upload, draft preservation, cancellation, silence, backend errors, permission denial')

} finally {
  clearTimeout(timeout)
  socket?.close()
  browser.kill()
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once('exit', resolve))
  await new Promise(resolve => server.close(resolve))
  await rm(profile, { recursive: true, force: true })
}
