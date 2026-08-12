import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is proxied so the browser sees one origin in development. Without
// this every fetch is a cross-origin request and CORS failures look identical
// to the backend being down.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
