/* global AudioWorkletProcessor, registerProcessor, sampleRate */
class PCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super()
    this.remaining = sampleRate * 30
    this.stopped = false
    this.port.onmessage = () => {
      this.stopped = true
      this.port.postMessage({ done: true })
    }
  }

  process(inputs) {
    if (this.stopped) return false
    const channel = inputs[0]?.[0]
    if (channel) {
      const samples = channel.slice(0, this.remaining)
      this.port.postMessage({ samples }, [samples.buffer])
      this.remaining -= samples.length
      if (this.remaining <= 0) {
        this.stopped = true
        this.port.postMessage({ done: true })
        return false
      }
    }
    return true
  }
}
registerProcessor('pcm-recorder', PCMRecorder)
