import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      ['/health', '/ready', '/chat', '/docs', '/openapi.json'].map((path) => [
        path,
        {
          target: process.env.WELL_API_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          timeout: 660_000,
          proxyTimeout: 660_000,
        },
      ]),
    ),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
