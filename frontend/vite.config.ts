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
    // npm run dev:mock: фронтенд без бэкенда на данных из src/mock
    define: mode === 'mock' ? { 'import.meta.env.VITE_MOCK_API': JSON.stringify('true') } : {},
    plugins: [
      // В тестах картинки из public (src="/kuzya-head.png") остаются строками: Node их не импортирует
      vue(mode === 'test' ? { template: { transformAssetUrls: { includeAbsolute: false } } } : {}),
      vuetify({ autoImport: true }),
      tailwindcss(),
    ],
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
            groups: [{ name: 'vue', test: /node_modules[\\/](@vue|vue|pinia|vue-router)[\\/]/ }],
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts'],
      // экраны в тестах ходят в мок-бэкенд src/mock, как в npm run dev:mock
      env: { VITE_MOCK_API: 'true', TZ: 'Europe/Ulyanovsk' },
      setupFiles: ['src/test/setup.ts'],
      // vuetify импортирует свои .css: пусть их обработает Vite, а не Node
      server: { deps: { inline: ['vuetify'] } },
      restoreMocks: true,
      unstubGlobals: true,
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,vue}'],
        exclude: [
          'src/mock/**',
          'src/main.ts',
          'src/test/**',
          '**/*.test.ts',
          'src/components/ui/**',
          'src/**/sprites/**',
          'src/**/*.d.ts',
        ],
        reporter: ['text', 'text-summary', 'html'],
        reportsDirectory: 'coverage',
      },
    },
  }
})
