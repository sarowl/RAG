import { useState } from 'react'

const keysByMode = {
  letters: ['qwertyuiop', 'asdfghjkl', 'zxcvbnm'],
  numbers: ['1234567890', '@#$%&*-+/', "!:'\"();"],
  symbols: ['[]{}<>_=|~', '€£¥¢°©®', '`\\^…–—•'],
}

function KeyIcon({ path }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg>
}

export default function TouchKeyboard({ onKey, onHide }) {
  const [shift, setShift] = useState(false)
  const [mode, setMode] = useState('letters')
  const letters = mode === 'letters'
  function type(key) {
    onKey(key)
    setShift(false)
  }
  function changeMode(next) {
    setMode(next)
    setShift(false)
  }

  return <section id="touch-keyboard" className="touch-keyboard" aria-label="On-screen keyboard"
    onPointerDown={event => { if (event.target.closest('button')) event.preventDefault() }}>
    <div className="keyboard-keys">
      {keysByMode[mode].map((row, index) => <div className="keyboard-row" key={index}>
        {index === 2 && (letters
          ? <button type="button" className="keyboard-control keyboard-wide" aria-label="Shift" aria-pressed={shift} onClick={() => setShift(current => !current)}>
            <KeyIcon path="M12 4 4 12h4v7h8v-7h4Z" />
          </button>
          : <button type="button" className="keyboard-control keyboard-wide"
            aria-label={mode === 'numbers' ? 'More symbols' : 'Show numbers'}
            onClick={() => changeMode(mode === 'numbers' ? 'symbols' : 'numbers')}>{mode === 'numbers' ? '#+=' : '123'}</button>)}
        {Array.from(letters && shift ? row.toUpperCase() : row).map((key, column) =>
          <button type="button" key={column} onClick={() => type(key)}>{key}</button>
        )}
        {index === 2 && <button type="button" className="keyboard-control keyboard-wide" aria-label="Backspace" onClick={() => onKey('Backspace')}>
          <KeyIcon path="M9 5h12v14H9l-7-7 7-7Zm3 4 6 6m0-6-6 6" />
        </button>}
      </div>)}
      <div className="keyboard-row keyboard-actions">
        <button type="button" className="keyboard-control keyboard-wide" aria-label={letters ? 'Show numbers and symbols' : 'Show letters'}
          onClick={() => changeMode(letters ? 'numbers' : 'letters')}>{letters ? '123' : 'ABC'}</button>
        <button type="button" aria-label="Comma" onClick={() => type(',')}>,</button>
        <button type="button" className="keyboard-space" onClick={() => type(' ')}>Space</button>
        <button type="button" aria-label="Period" onClick={() => type('.')}>.</button>
        <button type="button" aria-label="Question mark" onClick={() => type('?')}>?</button>
        <button type="button" className="keyboard-control keyboard-wide" aria-label="Hide keyboard" onClick={onHide}>Hide</button>
      </div>
    </div>
  </section>
}
