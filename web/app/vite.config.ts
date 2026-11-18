import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_BASE sets the public path: '/' locally, '/pathfinder-demo/' on GitHub Pages. Every asset and the engine
// worker resolve against import.meta.env.BASE_URL / import.meta.url, so the app works under either.
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: { port: 5173, host: true },
  worker: { format: 'es' },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          fluent: ['@fluentui/react-components', '@fluentui/react-icons'],
          charts: ['recharts'],
        },
      },
    },
  },
})
