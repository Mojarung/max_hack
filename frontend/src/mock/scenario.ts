/**
 * Сценарии мок-режима (`npm run dev:mock`). Выбираются параметрами адреса и
 * запоминаются на вкладку, чтобы переходы по приложению их не сбрасывали:
 *
 *   ?scenario=default|empty|overdue|alert|long|error|boot-error
 *   ?role=resident|admin     кто открыл приложение
 *   ?max=0                   браузерный демо-режим с переключателем жителей (по умолчанию имитируем MAX)
 *   ?latency=1500            задержка ответов в мс (скелетоны, спиннеры)
 *   ?motion=1                включить анимации (по умолчанию выключены ради стабильных скриншотов)
 *   ?theme=dark|light        тема независимо от системной
 *   ?reset=1                 сбросить запомненные параметры
 */

export type ScenarioName =
  'default' | 'empty' | 'overdue' | 'alert' | 'long' | 'error' | 'boot-error'

export interface MockScenario {
  name: ScenarioName
  role: 'resident' | 'admin'
  inMax: boolean
  latency: number
  motion: boolean
  theme: 'dark' | 'light' | null
}

const KEY = 'kuzya.mockScenario'
const NAMES: ScenarioName[] = [
  'default',
  'empty',
  'overdue',
  'alert',
  'long',
  'error',
  'boot-error',
]

function read(): MockScenario {
  const fallback: MockScenario = {
    name: 'default',
    role: 'resident',
    inMax: true,
    latency: 250,
    motion: false,
    theme: null,
  }
  let saved: Partial<MockScenario> = {}
  try {
    const params = new URLSearchParams(window.location.search)
    if (params.get('reset')) sessionStorage.removeItem(KEY)
    saved = JSON.parse(sessionStorage.getItem(KEY) ?? '{}') as Partial<MockScenario>
    const name = params.get('scenario') as ScenarioName | null
    if (name && NAMES.includes(name)) saved.name = name
    const role = params.get('role')
    if (role === 'admin' || role === 'resident') saved.role = role
    if (params.has('max')) saved.inMax = params.get('max') !== '0'
    if (params.has('motion')) saved.motion = params.get('motion') !== '0'
    const theme = params.get('theme')
    if (theme === 'dark' || theme === 'light') saved.theme = theme
    if (theme === 'system') saved.theme = null
    const latency = Number(params.get('latency'))
    if (params.has('latency') && Number.isFinite(latency)) saved.latency = latency
    sessionStorage.setItem(KEY, JSON.stringify(saved))
  } catch {
    // хранилище недоступно: работаем со значениями по умолчанию
  }
  return { ...fallback, ...saved }
}

export const scenario: MockScenario = read()
