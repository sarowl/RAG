// Run after npm run build: node scripts/test-audio.mjs [chromium-path]
// Uses a temporary browser profile and a stub chat API with a valid WAV file.
import { createServer } from 'node:http'
import { readFile, mkdtemp, rm } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join, extname } from 'node:path'
import assert from 'node:assert/strict'

const dist = new URL('../dist/', import.meta.url)
const wav = Buffer.alloc(44 + 22050 * 2)
wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8)
wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22)
wav.writeUInt32LE(22050, 24); wav.writeUInt32LE(44100, 28)
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34)
wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40)
for (let i = 0; i < 22050; i++) wav.writeInt16LE(Math.round(1000 * Math.sin(i * 440 * 2 * Math.PI / 22050)), 44 + i * 2)
let mode = 'audio'
const server = createServer(async (req, res) => {
  if (req.url === '/api/chat') {
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify({ answer: 'Audio test answer.', saved: true, tts_enabled: mode !== 'off',
      ...(mode === 'audio' ? { audio: `data:audio/wav;base64,${wav.toString('base64')}` } : {}),
      ...(mode === 'error' ? { audio_error: 'Speech is unavailable. You can still read the answer.' } : {}),
    }))
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
const browser = spawn(process.argv[2] || 'chromium', ['--headless', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0', '--autoplay-policy=no-user-gesture-required', `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] })
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
  const send = async () => {
    await evaluate('document.querySelector(".suggestion").click()')
    await evaluate('document.querySelector("form").requestSubmit()')
    await waitFor('!!document.querySelector(".assistant")')
  }
  await send()
  await waitFor('document.querySelector("audio")?.currentTime > 0')
  assert.equal(await evaluate('document.querySelector("audio").error'), null)
  await evaluate('document.querySelector(".new-chat").click()')
  assert.equal(await evaluate('document.querySelectorAll("audio").length'), 0)
  await evaluate(`window.originalPlay = HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play = function () { return Promise.reject(new DOMException('Blocked', 'NotAllowedError')) }`)
  await send()
  await waitFor('document.body.textContent.includes("Automatic playback was blocked")')
  await evaluate('HTMLMediaElement.prototype.play = window.originalPlay; document.querySelector("audio").play()')
  await waitFor('document.querySelector("audio")?.currentTime > 0')
  for (const value of ['off', 'error']) {
    mode = value
    await evaluate('document.querySelector(".new-chat").click()')
    await send()
    const expected = value === 'off' ? 'Spoken answers are off.' : 'Speech is unavailable.'
    await waitFor(`document.body.textContent.includes(${JSON.stringify(expected)})`)
    assert.equal(await evaluate('document.querySelectorAll("audio").length'), 0)
  }
  console.log('PASS: WAV playback, blocked autoplay recovery, new-chat cleanup, TTS off, synthesis error')
} finally {
  clearTimeout(timeout)
  socket?.close()
  browser.kill()
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once('exit', resolve))
  await new Promise(resolve => server.close(resolve))
  await rm(profile, { recursive: true, force: true })
}
