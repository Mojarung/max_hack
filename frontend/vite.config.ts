/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'
import vuetify from 'vite-plugin-vuetify'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY || 'http://localhost:8000'

  return {
    base: '/',
    plugins: [vue(), vuetify({ autoImport: true }), tailwindcss()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: true,
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // SSE: не буферизуем ответ
          configure: (proxy) => {
            proxy.on('proxyRes', (res) => {
              if (String(res.headers['content-type'] ?? '').includes('text/event-stream')) {
                res.headers['cache-control'] = 'no-cache'
                res.headers['x-accel-buffering'] = 'no'
              }
            })
          },
        },
      },
    },
    build: {
      target: 'es2022',
      chunkSizeWarningLimit: 700,
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: 'vue', test: /node_modules[\\/](@vue|vue|pinia|vue-router)[\\/]/ },
            ],
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts'],
    },
  }
})
