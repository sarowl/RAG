import { useEffect, useRef, useState } from 'react'

export default function AnswerAudio({ src, players }) {
  const player = useRef(null)
  const [status, setStatus] = useState('')
  useEffect(() => {
    const audio = player.current
    const active = players.current
    active.add(audio)
    let disposed = false
    audio.play().catch(error => {
      if (!disposed) setStatus(error.name === 'NotAllowedError'
        ? 'Automatic playback was blocked. Press play to hear this answer.'
        : 'Audio could not start. Try pressing play.')
    })
    return () => { disposed = true; audio.pause(); active.delete(audio) }
  }, [src, players])

  return <div className="answer-audio">
    <audio ref={player} src={src} controls aria-label="Spoken answer"
      onPlay={() => {
        players.current.forEach(audio => { if (audio !== player.current) audio.pause() })
        setStatus('')
      }}
      onError={() => setStatus('The browser could not load this audio. Try asking again.')} />
    {status && <p role="status">{status}</p>}
  </div>
}
