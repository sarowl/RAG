let nextMessageId = 0

// Message IDs are local UI keys, so a per-page counter is sufficient when
// randomUUID is unavailable (for example, when accessing the app over HTTP).
export function createMessageId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }
  return `message-${Date.now()}-${nextMessageId++}`
}
