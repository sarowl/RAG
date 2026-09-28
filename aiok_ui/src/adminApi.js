export async function adminRequest(path, token, options = {}) {
  const response = await fetch(`/api/admin/${path}`, {
    ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  })
  const data = await response.json().catch(() => { throw new Error('Admin API unavailable. Check the backend connection.') })
  if (!response.ok) {
    const error = new Error(data.error || 'Request failed.')
    error.status = response.status
    throw error
  }
  return data
}

