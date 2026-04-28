import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Shared single-source-of-truth RBAC matrix at the repo root.
      // The backend reads the same file from api/app/services/rbac.py,
      // so frontend and backend can never drift.
      '@permissions': path.resolve(__dirname, '../permissions.json'),
    },
  },
  server: {
    // Allow the dev server to serve files one directory above ``web/``
    // so the @permissions alias resolves during ``vite``.  Production
    // builds inline the JSON into the bundle and don't depend on this.
    fs: {
      allow: ['..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
