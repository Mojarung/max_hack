/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_PROXY?: string
  /** 'true': мок-бэкенд из src/mock вместо /api (npm run dev:mock) */
  readonly VITE_MOCK_API?: string
}
