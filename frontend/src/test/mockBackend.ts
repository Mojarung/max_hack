/**
 * Лёгкая подготовка для тестов сторов: мок-бэкенд src/mock без монтирования экранов
 * (без Vuetify и App.vue, поэтому файлы сторов грузятся быстро).
 * Перед каждым тестом «база» мока возвращается к фикстурам, время стоит на NOW,
 * у Pinia свежий экземпляр.
 */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, vi, type Mock } from 'vitest'
import { setDevUser, setHouseId } from '@/api/client'
import { resetMockState } from '@/mock/server'
import { scenario, type MockScenario } from '@/mock/scenario'

/** То же «сейчас», что в harness.ts: среда, 21 октября 2026, 10:00 по Ульяновску. */
export const NOW = new Date('2026-10-21T10:00:00+04:00')

const DEFAULT_SCENARIO: MockScenario = {
  name: 'default',
  role: 'resident',
  inMax: true,
  latency: 0,
  motion: false,
  theme: null,
  onboarding: false,
  setup: false,
}

/** Сценарий мока и пересборка данных, как ?scenario=... с перезагрузкой вкладки. */
export function setScenario(patch: Partial<MockScenario>): void {
  Object.assign(scenario, DEFAULT_SCENARIO, patch)
  resetMockState()
}

/** Сервер «падает» со следующего запроса, данные мока при этом не меняются. */
export function breakServer(name: 'error' | 'boot-error' = 'error'): void {
  scenario.name = name
}

export interface MaxSpies {
  ready: Mock
  impact: Mock
  notify: Mock
  selection: Mock
  closing: Mock
}

/** Мост MAX со шпионами (inMax=true) или обычный браузер с пустым initData. */
export function fakeMax(inMax = true, platform = 'ios'): MaxSpies {
  const spies: MaxSpies = {
    ready: vi.fn(),
    impact: vi.fn(),
    notify: vi.fn(),
    selection: vi.fn(),
    closing: vi.fn(),
  }
  window.WebApp = inMax
    ? {
        initData: 'test-init-data',
        platform,
        ready: spies.ready,
        HapticFeedback: {
          impactOccurred: spies.impact,
          notificationOccurred: spies.notify,
          selectionChanged: spies.selection,
        },
        enableClosingConfirmation: () => spies.closing(true),
        disableClosingConfirmation: () => spies.closing(false),
      }
    : { initData: '' }
  return spies
}

/** Подключает сброс мока, заморозку времени и свежую Pinia для всех тестов файла. */
export function useMockBackend(): void {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(NOW)
    setScenario({})
    setDevUser(null)
    setHouseId(null)
    try {
      localStorage.clear()
    } catch {
      // хранилище недоступно: нечего чистить
    }
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.useRealTimers()
    delete window.WebApp
  })
}

/** Дождаться ответов мока (у него задержка setTimeout(0)) и всех цепочек промисов. */
export async function flushMock(rounds = 4): Promise<void> {
  for (let i = 0; i < rounds; i++) await new Promise((resolve) => setTimeout(resolve, 0))
}
