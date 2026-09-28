import { useState } from 'react'

const letterRows = ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']
const symbolRows = [",.?!:;'\"", '()[]{}<>', '@#$%&*_=', '+-/\\|~`^']

export default function TouchKeyboard({ onKey, onHide }) {
  const [shift, setShift] = useState(false)
  const [symbols, setSymbols] = useState(false)
  const rows = symbols ? symbolRows : letterRows
  function type(key) {
    onKey(key)
    setShift(false)
  }
  return <section id="touch-keyboard" className="touch-keyboard" aria-label="On-screen keyboard"
    onPointerDown={event => { if (event.target.closest('button')) event.preventDefault() }}>
    <div className="keyboard-keys">
      {rows.map((row, index) => <div className="keyboard-row" key={index}>
        {Array.from(!symbols && shift ? row.toUpperCase() : row).map((key, column) => <button type="button" key={column} onClick={() => type(key)}>{key}</button>)}
      </div>)}
      <div className="keyboard-row keyboard-actions">
        <button type="button" aria-label={symbols ? 'Show letters and numbers' : 'Show punctuation and symbols'} onClick={() => { setSymbols(current => !current); setShift(false) }}>{symbols ? 'ABC' : '?123'}</button>
        {!symbols && <button type="button" aria-pressed={shift} onClick={() => setShift(current => !current)}>Shift</button>}
        <button type="button" className="keyboard-space" onClick={() => type(' ')}>Space</button>
        <button type="button" onClick={() => onKey('Backspace')}>Backspace</button>
        <button type="button" onClick={onHide}>Hide</button>
      </div>
    </div>
  </section>
}
