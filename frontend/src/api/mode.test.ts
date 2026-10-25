import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const DEMO_KEY = 'kuzya.browserDemo'
const SCENARIO_KEY = 'kuzya.mockScenario'

let saved: string | null

beforeEach(() => {
  saved = sessionStorage.getItem(SCENARIO_KEY)
  vi.resetModules()
  // в jsdom настоящий переход страницы не работает, проверяем только адрес
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

afterEach(() => {
  sessionStorage.removeItem(DEMO_KEY)
  if (saved === null) sessionStorage.removeItem(SCENARIO_KEY)
  else sessionStorage.setItem(SCENARIO_KEY, saved)
  vi.unstubAllEnvs()
  delete window.WebApp
})

async function loadMode() {
  vi.stubEnv('VITE_MOCK_API', 'false')
  return import('./mode')
}

describe('откуда берутся данные', () => {
  it('в обычном браузере без демо - настоящий сервер', async () => {
    const mode = await loadMode()
    expect(mode.BROWSER_DEMO).toBe(false)
    expect(mode.MOCK_API).toBe(false)
  })

  it('после кнопки «Посмотреть демо» - мок-бэкенд в памяти', async () => {
    sessionStorage.setItem(DEMO_KEY, '1')
    const mode = await loadMode()
    expect(mode.BROWSER_DEMO).toBe(true)
    expect(mode.MOCK_API).toBe(true)
  })

  it('внутри MAX демо не включается никогда', async () => {
    sessionStorage.setItem(DEMO_KEY, '1')
    window.WebApp = { initData: 'signed' }
    const mode = await loadMode()
    expect(mode.BROWSER_DEMO).toBe(false)
  })

  it('без доступа к хранилищу демо выключено', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    const mode = await loadMode()
    expect(mode.BROWSER_DEMO).toBe(false)
  })

  it('npm run dev:mock включает мок сборкой', async () => {
    vi.stubEnv('VITE_MOCK_API', 'true')
    const mode = await import('./mode')
    expect(mode.MOCK_API).toBe(true)
  })
})

describe('включение и выключение демо', () => {
  it('демо запоминает режим без имитации MAX и с анимациями', async () => {
    const { startBrowserDemo } = await loadMode()
    expect(startBrowserDemo()).toBe(true)
    expect(sessionStorage.getItem(DEMO_KEY)).toBe('1')
    expect(JSON.parse(sessionStorage.getItem(SCENARIO_KEY)!)).toEqual({
      inMax: false,
      motion: true,
    })
  })

  it('если хранилище запрещено, демо не стартует', async () => {
    const { startBrowserDemo } = await loadMode()
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(startBrowserDemo()).toBe(false)
    spy.mockRestore()
  })

  it('выход из демо забывает режим', async () => {
    sessionStorage.setItem(DEMO_KEY, '1')
    const { stopBrowserDemo } = await loadMode()
    stopBrowserDemo()
    expect(sessionStorage.getItem(DEMO_KEY)).toBeNull()
    expect(sessionStorage.getItem(SCENARIO_KEY)).toBeNull()
  })

  it('выход из демо не падает без хранилища', async () => {
    const { stopBrowserDemo } = await loadMode()
    const spy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    expect(() => stopBrowserDemo()).not.toThrow()
    spy.mockRestore()
  })
})
