import { describe, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'
import { setNavDirection } from '@/composables/useMotion'
import { goBack, router } from './index'

vi.mock('@/composables/useMotion', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/useMotion')>()),
  setNavDirection: vi.fn(),
}))

// Экраны заменены пустышками: здесь проверяем маршруты, а не сами экраны (у них свои тесты)
vi.mock('@/views/HomeView.vue', () => ({ default: { name: 'HomeView', render: () => null } }))
vi.mock('@/views/issues/IssuesView.vue', () => ({
  default: { name: 'IssuesView', render: () => null },
}))
vi.mock('@/views/issues/IssueNewView.vue', () => ({
  default: { name: 'IssueNewView', render: () => null },
}))
vi.mock('@/views/issues/IssueDetailView.vue', () => ({
  default: { name: 'IssueDetailView', render: () => null },
}))
vi.mock('@/views/market/MarketView.vue', () => ({
  default: { name: 'MarketView', render: () => null },
}))
vi.mock('@/views/market/ListingNewView.vue', () => ({
  default: { name: 'ListingNewView', render: () => null },
}))
vi.mock('@/views/market/ListingDetailView.vue', () => ({
  default: { name: 'ListingDetailView', render: () => null },
}))
vi.mock('@/views/events/EventsView.vue', () => ({
  default: { name: 'EventsView', render: () => null },
}))
vi.mock('@/views/events/EventNewView.vue', () => ({
  default: { name: 'EventNewView', render: () => null },
}))
vi.mock('@/views/events/EventDetailView.vue', () => ({
  default: { name: 'EventDetailView', render: () => null },
}))
vi.mock('@/views/more/MoreView.vue', () => ({ default: { name: 'MoreView', render: () => null } }))
vi.mock('@/views/more/AchievementsView.vue', () => ({
  default: { name: 'AchievementsView', render: () => null },
}))
vi.mock('@/views/more/SafetyView.vue', () => ({
  default: { name: 'SafetyView', render: () => null },
}))
vi.mock('@/views/more/SearchView.vue', () => ({
  default: { name: 'SearchView', render: () => null },
}))
vi.mock('@/views/more/AssistantView.vue', () => ({
  default: { name: 'AssistantView', render: () => null },
}))
vi.mock('@/views/more/McpView.vue', () => ({ default: { name: 'McpView', render: () => null } }))
vi.mock('@/views/announcements/AnnouncementsView.vue', () => ({
  default: { name: 'AnnouncementsView', render: () => null },
}))
vi.mock('@/views/house/HouseView.vue', () => ({
  default: { name: 'HouseView', render: () => null },
}))
vi.mock('@/views/house/HouseEditView.vue', () => ({
  default: { name: 'HouseEditView', render: () => null },
}))
vi.mock('@/views/house/DocumentsView.vue', () => ({
  default: { name: 'DocumentsView', render: () => null },
}))
vi.mock('@/views/people/PeopleView.vue', () => ({
  default: { name: 'PeopleView', render: () => null },
}))
vi.mock('@/views/people/ProfileView.vue', () => ({
  default: { name: 'ProfileView', render: () => null },
}))
vi.mock('@/views/dev/ChatEmulatorView.vue', () => ({
  default: { name: 'ChatEmulatorView', render: () => null },
}))

const direction = vi.mocked(setNavDirection)

async function go(path: string): Promise<string | undefined> {
  direction.mockClear()
  await router.push(path)
  return direction.mock.calls.at(-1)?.[0]
}

async function waitForPath(path: string): Promise<void> {
  for (let i = 0; i < 100 && router.currentRoute.value.fullPath !== path; i++) {
    await new Promise((resolve) => setTimeout(resolve, 5))
  }
  expect(router.currentRoute.value.fullPath).toBe(path)
}

describe('маршруты', () => {
  it('номер заявки, события и вещи из адреса приходит экрану числом', () => {
    for (const [path, id] of [
      ['/issues/101', 101],
      ['/events/301', 301],
      ['/market/205', 205],
      ['/people/2', 2],
    ] as const) {
      const record = router.resolve(path).matched[0]!
      const props = record.props.default as (r: unknown) => unknown
      expect(props(router.resolve(path))).toEqual({ id })
    }
  })

  it('у внутренних экранов есть родитель для кнопки «Назад»', () => {
    expect(router.resolve('/issues/new').meta).toMatchObject({ inner: true, parent: '/issues' })
    expect(router.resolve('/people/2').meta.parent).toBe('/people')
    expect(router.resolve('/dev/chat').meta.bare).toBe(true)
    expect(router.resolve('/market').meta.inner).toBeUndefined()
  })

  it('каждый экран приложения открывается по своему адресу', async () => {
    const paths = [
      '/issues/new',
      '/market',
      '/market/new',
      '/market/205',
      '/events/new',
      '/more/safety',
      '/more/search',
      '/more/assistant',
      '/more/mcp',
      '/announcements',
      '/more/house',
      '/more/house/edit',
      '/more/documents',
      '/dev/chat',
    ]
    for (const path of paths) {
      await router.push(path)
      expect(router.currentRoute.value.path).toBe(path)
      // ленивый экран загрузился: вместо функции загрузки в маршруте лежит компонент
      const component = router.currentRoute.value.matched[0]!.components!.default
      expect(typeof component, path).toBe('object')
      expect(router.currentRoute.value.meta.title, path).toBeTruthy()
    }
  })

  it('неизвестный адрес ведёт на главную', async () => {
    await router.push('/такого-нет')
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('после перехода страница открывается сверху, при возврате - на том же месте', () => {
    const scroll = router.options.scrollBehavior!
    const to = router.resolve('/issues') as unknown as RouteLocationNormalized
    expect(scroll(to, to, null)).toEqual({ top: 0 })
    expect(scroll(to, to, { left: 0, top: 420 })).toEqual({ left: 0, top: 420 })
  })
})

describe('направление анимации перехода', () => {
  it('вглубь, назад и между вкладками', async () => {
    await go('/')
    expect(await go('/issues')).toBe('tab')
    expect(await go('/issues/101')).toBe('push')
    expect(await go('/issues')).toBe('pop')
    expect(await go('/more')).toBe('tab')
    expect(await go('/people')).toBe('push')
    expect(await go('/people/2')).toBe('push')
    // с одного внутреннего экрана на соседний того же уровня - тоже вглубь
    expect(await go('/people/3')).toBe('push')
    expect(await go('/more')).toBe('pop')
  })
})

describe('кнопка «Назад»', () => {
  it('есть история - возвращает на предыдущий экран', async () => {
    await router.push('/events')
    await router.push('/events/301')
    goBack()
    await waitForPath('/events')
  })

  it('открыли по ссылке без истории - ведёт в родительский раздел', async () => {
    await router.push('/more/achievements')
    window.history.replaceState({ ...window.history.state, back: null }, '')
    goBack()
    await waitForPath('/more')
  })
})
