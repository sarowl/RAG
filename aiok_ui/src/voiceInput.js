function wavBlob(chunks, sampleRate) {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0)
  const buffer = new ArrayBuffer(44 + length * 2)
  const view = new DataView(buffer)
  const text = (offset, value) => [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)))
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true)
  text(8, 'WAVE'); text(12, 'fmt '); view.setUint32(16, 16, true)
  view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  text(36, 'data'); view.setUint32(40, length * 2, true)
  let offset = 44
  for (const chunk of chunks) for (const value of chunk) {
    const sample = Math.max(-1, Math.min(1, value))
    view.setInt16(offset, Math.round(sample * (sample < 0 ? 32768 : 32767)), true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

export function createVoiceInput({ onState, onText, onError }) {
  let cancelled = false, finishing = false, stream, context, source, node
  const chunks = []
  const controller = new AbortController()
  function release() {
    stream?.getTracks().forEach(track => track.stop())
    source?.disconnect()
    if (node) { node.port.onmessage = null; node.disconnect() }
    context?.close().catch(() => {})
  }
  function fail(error) {
    if (cancelled) return
    cancelled = true
    release()
    onState('idle')
    onError(error.name === 'NotAllowedError'
      ? 'Microphone access was denied. Allow microphone access and try again.'
      : error.message || 'Microphone unavailable. Check your browser permissions.')
  }
  async function finish() {
    if (cancelled || finishing) return
    finishing = true
    const rate = context.sampleRate
    release()
    onState('transcribing')
    try {
      if (!chunks.length) throw new Error('No audio recorded. Please try again.')
      const response = await fetch('/api/stt', {
        method: 'POST', headers: { 'Content-Type': 'audio/wav' },
        body: wavBlob(chunks, rate), signal: controller.signal,
      })
      const result = await response.json().catch(() => { throw new Error('Voice input is unavailable. Check that the backend is running.') })
      if (!response.ok) throw new Error(result.error || 'Unable to transcribe audio.')
      if (typeof result.text !== 'string') throw new Error('The backend returned an invalid transcript.')
      if (cancelled) return
      cancelled = true
      onState('idle')
      if (result.text.trim()) onText(result.text.trim())
      else onError('No speech recognized. Please try again.')
    } catch (error) { fail(error) }
  }
  return {
    async start() {
      onState('starting')
      try {
        if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
          throw new Error('Microphone recording requires a supported browser on localhost or HTTPS.')
        }
        context = new window.AudioContext()
        // Resume during the click gesture, before waiting for microphone permission.
        await context.resume()
        if (cancelled) return
        stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
        if (cancelled) { release(); return }
        await context.audioWorklet.addModule('/pcm-recorder.js')
        if (cancelled) return
        node = new AudioWorkletNode(context, 'pcm-recorder')
        node.port.onmessage = ({ data }) => {
          if (cancelled) return
          if (data.samples) chunks.push(data.samples)
          if (data.done) finish()
        }
        node.onprocessorerror = () => fail(new Error('Microphone recording failed. Please try again.'))
        stream.getAudioTracks().forEach(track => { track.onended = () => fail(new Error('Microphone disconnected. Please try again.')) })
        source = context.createMediaStreamSource(stream)
        source.connect(node)
        // The processor outputs silence; connecting keeps capture running without feedback.
        node.connect(context.destination)
        onState('recording')
      } catch (error) { fail(error) }
    },
    stop() { if (!cancelled && !finishing) node?.port.postMessage('stop') },
    cancel() { cancelled = true; controller.abort(); release() },
  }
}
