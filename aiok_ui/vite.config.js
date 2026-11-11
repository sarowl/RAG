import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  const proxyOptions = target => ({ target, timeout: 0, proxyTimeout: 0 })
  const apiProxy = {
    '/api/admin': proxyOptions(env.VITE_ADMIN_API || 'http://127.0.0.1:8003'),
    '/api/stt': proxyOptions(env.VITE_STT_API || 'http://127.0.0.1:8001'),
    '/api/tts': proxyOptions(env.VITE_TTS_API || 'http://127.0.0.1:8002'),
    '/api': proxyOptions(env.VITE_RAG_API || 'http://127.0.0.1:8000'),
  }
  return {
    plugins: [react()],
    server: { proxy: apiProxy },
    preview: { proxy: apiProxy },
  }
})
