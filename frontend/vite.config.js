import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, /api/* is forwarded to the Flask server on port 5000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
