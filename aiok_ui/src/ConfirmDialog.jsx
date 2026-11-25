import { useEffect, useRef } from 'react'

export default function ConfirmDialog({ title, children, action, onConfirm, onCancel, disabled }) {
  const dialog = useRef(null)

  useEffect(() => {
    const element = dialog.current
    element.showModal()
    return () => element.close()
  }, [])

  function cancel() {
    dialog.current.close()
    onCancel()
  }

  return <dialog ref={dialog} className="confirm-dialog" aria-labelledby="confirm-title"
    aria-describedby="confirm-description" onCancel={event => { event.preventDefault(); cancel() }}>
    <h2 id="confirm-title">{title}</h2>
    <p id="confirm-description">{children}</p>
    <div className="dialog-actions">
      <button type="button" className="secondary-button" autoFocus onClick={cancel}>Cancel</button>
      <button type="button" className="primary-button" disabled={disabled} onClick={onConfirm}>{action}</button>
    </div>
  </dialog>
}
