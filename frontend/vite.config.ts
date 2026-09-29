import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Which backend the dev server proxies to. `labpilot app` sets this,
// because the port it ends up using is not knowable here: it asks the OS
// for another one when 8000 cannot be bound, which on Windows happens
// whenever Hyper-V or WSL has reserved that range.
const backend = process.env.LABPILOT_BACKEND || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
      },
      '/ws': {
        target: backend.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
})