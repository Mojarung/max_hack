/**
 * Откуда берутся данные: настоящий сервер или мок-бэкенд в памяти (`src/mock`).
 *
 * Мок включается сборкой `npm run dev:mock` или по кнопке «Посмотреть демо в браузере»
 * на экране «Кузя живёт в MAX»: жюри и гости без MAX проходят сценарий на вымышленном доме,
 * ничего не уходит на сервер и в домовой чат. Внутри MAX демо не включается никогда.
 */
import { isInMax } from '@/max/bridge'

const DEMO_KEY = 'kuzya.browserDemo'
const SCENARIO_KEY = 'kuzya.mockScenario'

function readDemoFlag(): boolean {
  try {
    return sessionStorage.getItem(DEMO_KEY) === '1'
  } catch {
    return false
  }
}

/** Демо в обычном браузере на данных в памяти. */
export const BROWSER_DEMO = !isInMax() && readDemoFlag()

export const MOCK_API = import.meta.env.VITE_MOCK_API === 'true' || BROWSER_DEMO

/** false, если браузер не даёт sessionStorage (приватный режим с запретом хранилища). */
export function startBrowserDemo(): boolean {
  try {
    sessionStorage.setItem(DEMO_KEY, '1')
    // переключатель жителей вместо имитации MAX и живые анимации (сценарии мока: src/mock/scenario.ts)
    sessionStorage.setItem(SCENARIO_KEY, JSON.stringify({ inMax: false, motion: true }))
  } catch {
    return false
  }
  window.location.replace(`${window.location.pathname}${window.location.hash}`)
  return true
}

export function stopBrowserDemo(): void {
  try {
    sessionStorage.removeItem(DEMO_KEY)
    sessionStorage.removeItem(SCENARIO_KEY)
  } catch {
    // хранилище недоступно: демо и так не включится
  }
  window.location.replace('/')
}
