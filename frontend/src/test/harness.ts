/**
 * Монтирование экранов и компонентов «как в приложении»: Vuetify, Pinia, настоящий роутер
 * и API-клиент, который в тестах ходит в мок-бэкенд `src/mock` (VITE_MOCK_API=true в vite.config.ts).
 *
 * Перед каждым тестом «база» мока возвращается к фикстурам, время замораживается на NOW,
 * мост MAX подменяется шпионами. После теста всё размонтируется и чистится.
 */
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, vi, type Mock } from 'vitest'
import { defineComponent, h, type Component } from 'vue'
import { VApp } from 'vuetify/components'
import App from '@/App.vue'
import { setDevUser, setHouseId } from '@/api/client'
import type { MaxWebApp } from '@/max/bridge'
import { scenario, type MockScenario } from '@/mock/scenario'
import { vuetify } from '@/plugins/vuetify'
import { router } from '@/router'
import { useAlertsStore } from '@/stores/alerts'
import { usePulseStore } from '@/stores/pulse'
import { useSessionStore } from '@/stores/session'
import { settle, waitFor } from './dom'
import { NOW, setScenario } from './mockBackend'
import TestShell from './TestShell.vue'

/** «Сейчас» во всех тестах: среда, 21 октября 2026, 10:00 по Ульяновску. */
export { NOW }

export interface MaxFake {
  app: MaxWebApp
  ready: Mock
  impact: Mock
  notify: Mock
  selection: Mock
  openLink: Mock
  openMaxLink: Mock
  shareMaxContent: Mock
  closingConfirmation: Mock
  backShow: Mock
  backHide: Mock
  /** Нажать системную кнопку «Назад» MAX. */
  pressBack: () => void
}

export interface MaxOptions {
  inMax?: boolean
  platform?: string
  startParam?: string
}

/** Подменяет window.WebApp: внутри MAX (по умолчанию) или обычный браузер с пустым initData. */
export function installMax(options: MaxOptions = {}): MaxFake {
  const { inMax = true, platform = 'ios', startParam } = options
  const clicks = new Set<() => void>()
  const fake = {
    ready: vi.fn(),
    impact: vi.fn(),
    notify: vi.fn(),
    selection: vi.fn(),
    openLink: vi.fn(),
    openMaxLink: vi.fn(),
    shareMaxContent: vi.fn(),
    closingConfirmation: vi.fn(),
    backShow: vi.fn(),
    backHide: vi.fn(),
  }
  const app: MaxWebApp = inMax
    ? {
        initData: 'test-init-data',
        initDataUnsafe: {
          start_param: startParam,
          user: { id: 1001, first_name: 'Анна' },
        },
        platform,
        version: 'test',
        ready: fake.ready,
        close: vi.fn(),
        BackButton: {
          isVisible: false,
          show: fake.backShow,
          hide: fake.backHide,
          onClick: (cb) => clicks.add(cb),
          offClick: (cb) => clicks.delete(cb),
        },
        HapticFeedback: {
          impactOccurred: fake.impact,
          notificationOccurred: fake.notify,
          selectionChanged: fake.selection,
        },
        openLink: fake.openLink,
        openMaxLink: fake.openMaxLink,
        shareMaxContent: fake.shareMaxContent,
        enableClosingConfirmation: () => fake.closingConfirmation(true),
        disableClosingConfirmation: () => fake.closingConfirmation(false),
      }
    : { initData: '' }
  window.WebApp = app
  return { ...fake, app, pressBack: () => clicks.forEach((cb) => cb()) }
}

/** Меняет сценарий мок-бэкенда и пересобирает данные (как ?scenario=... с перезагрузкой). */
export function useScenario(patch: Partial<MockScenario>): void {
  setScenario(patch)
}

const mounted: VueWrapper[] = []

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  useScenario({})
  setDevUser(null)
  setHouseId(null)
  try {
    localStorage.clear()
    // выбранные вкладки и прочее из прошлого теста; сценарий мока уже прочитан и живёт в scenario
    for (const key of Object.keys(sessionStorage)) {
      if (key !== 'kuzya.mockScenario') sessionStorage.removeItem(key)
    }
  } catch {
    // хранилище недоступно: нечего чистить
  }
})

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
  document.documentElement.className = ''
  // тест мог включить анимации: следующий начинает без них
  document.documentElement.dataset.motion = 'off'
  vi.useRealTimers()
  delete window.WebApp
})

export interface RenderOptions {
  /** Сценарий мока: name, role, inMax и т.д. */
  scenario?: Partial<MockScenario>
  /** Параметры моста MAX; по умолчанию внутри MAX, если scenario.inMax не false. */
  max?: Omit<MaxOptions, 'inMax'>
  /** Загрузить сессию до монтирования (как после BootScreen). */
  session?: boolean
}

export interface Rendered {
  wrapper: VueWrapper
  pinia: Pinia
  max: MaxFake
  router: typeof router
}

async function prepare(options: RenderOptions): Promise<{ pinia: Pinia; max: MaxFake }> {
  if (options.scenario) useScenario(options.scenario)
  const max = installMax({ ...options.max, inMax: scenario.inMax })
  const pinia = createPinia()
  setActivePinia(pinia)
  if (options.session !== false) {
    const session = useSessionStore()
    await session.init()
    if (session.status !== 'ready') throw new Error(`Сессия не загрузилась: ${session.bootError}`)
    // то же, что App.vue делает после загрузки
    await Promise.all([useAlertsStore().check(), usePulseStore().load()])
  }
  return { pinia, max }
}

function track(wrapper: VueWrapper): VueWrapper {
  mounted.push(wrapper)
  return wrapper
}

/** Экран по адресу внутри оболочки (router-view + слой кнопки + тосты), сессия уже загружена. */
export async function renderRoute(path: string, options: RenderOptions = {}): Promise<Rendered> {
  const { pinia, max } = await prepare(options)
  await router.push(path)
  await router.isReady()
  const wrapper = track(
    mount(TestShell, {
      attachTo: document.body,
      global: { plugins: [pinia, router, vuetify] },
    }),
  )
  await settle(5)
  return { wrapper, pinia, max, router }
}

/** Всё приложение целиком (App.vue): загрузочный экран, шапка, меню, обучалка, тревога. */
export async function renderApp(path = '/', options: RenderOptions = {}): Promise<Rendered> {
  const { pinia, max } = await prepare({ ...options, session: false })
  await router.push(path)
  await router.isReady()
  const wrapper = track(
    mount(App, { attachTo: document.body, global: { plugins: [pinia, router, vuetify] } }),
  )
  await waitFor(() => useSessionStore().status !== 'booting')
  await settle(5)
  return { wrapper, pinia, max, router }
}

export interface ComponentOptions extends RenderOptions {
  props?: Record<string, unknown>
  slots?: Record<string, () => unknown>
  /** Адрес роутера, на котором рисуем компонент (для router-link и useRoute). */
  path?: string
}

/** Отдельный компонент внутри <v-app> с Vuetify, Pinia и роутером. */
export async function renderComponent(
  component: Component,
  options: ComponentOptions = {},
): Promise<Rendered> {
  const { pinia, max } = await prepare({ session: false, ...options })
  await router.push(options.path ?? '/')
  await router.isReady()
  const Host = defineComponent({
    setup: () => () =>
      h(VApp, null, {
        default: () => [
          h(component, options.props ?? {}, options.slots),
          h('div', { id: 'fab-layer' }),
        ],
      }),
  })
  const wrapper = track(
    mount(Host, { attachTo: document.body, global: { plugins: [pinia, router, vuetify] } }),
  )
  await settle()
  return { wrapper, pinia, max, router }
}
