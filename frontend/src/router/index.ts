import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

export type TabKey = 'home' | 'issues' | 'market' | 'events' | 'more'

declare module 'vue-router' {
  interface RouteMeta {
    tab: TabKey
    title: string
    /** Внутренняя страница: в шапке кнопка «Назад», в MAX включается BackButton. */
    inner?: boolean
    /** Куда вернуться, если истории нет (открыли по диплинку). */
    parent?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { tab: 'home', title: 'Домовой Кузя' },
  },
  {
    path: '/issues',
    name: 'issues',
    component: () => import('@/views/issues/IssuesView.vue'),
    meta: { tab: 'issues', title: 'Проблемы дома' },
  },
  {
    path: '/issues/new',
    name: 'issue-new',
    component: () => import('@/views/issues/IssueNewView.vue'),
    meta: { tab: 'issues', title: 'Новая проблема', inner: true, parent: '/issues' },
  },
  {
    path: '/issues/:id(\\d+)',
    name: 'issue',
    component: () => import('@/views/issues/IssueDetailView.vue'),
    props: (route) => ({ id: Number(route.params.id) }),
    meta: { tab: 'issues', title: 'Проблема', inner: true, parent: '/issues' },
  },
  {
    path: '/market',
    name: 'market',
    component: () => import('@/views/market/MarketView.vue'),
    meta: { tab: 'market', title: 'Вещи соседей' },
  },
  {
    path: '/market/new',
    name: 'listing-new',
    component: () => import('@/views/market/ListingNewView.vue'),
    meta: { tab: 'market', title: 'Новое объявление', inner: true, parent: '/market' },
  },
  {
    path: '/market/:id(\\d+)',
    name: 'listing',
    component: () => import('@/views/market/ListingDetailView.vue'),
    props: (route) => ({ id: Number(route.params.id) }),
    meta: { tab: 'market', title: 'Объявление', inner: true, parent: '/market' },
  },
  {
    path: '/events',
    name: 'events',
    component: () => import('@/views/events/EventsView.vue'),
    meta: { tab: 'events', title: 'События двора' },
  },
  {
    path: '/events/new',
    name: 'event-new',
    component: () => import('@/views/events/EventNewView.vue'),
    meta: { tab: 'events', title: 'Новое событие', inner: true, parent: '/events' },
  },
  {
    path: '/events/:id(\\d+)',
    name: 'event',
    component: () => import('@/views/events/EventDetailView.vue'),
    props: (route) => ({ id: Number(route.params.id) }),
    meta: { tab: 'events', title: 'Событие', inner: true, parent: '/events' },
  },
  {
    path: '/more',
    name: 'more',
    component: () => import('@/views/more/MoreView.vue'),
    meta: { tab: 'more', title: 'Ещё' },
  },
  {
    path: '/more/achievements',
    name: 'achievements',
    component: () => import('@/views/more/AchievementsView.vue'),
    meta: { tab: 'more', title: 'Награды и рейтинг', inner: true, parent: '/more' },
  },
  {
    path: '/more/safety',
    name: 'safety',
    component: () => import('@/views/more/SafetyView.vue'),
    meta: { tab: 'more', title: 'Безопасность', inner: true, parent: '/more' },
  },
  {
    path: '/more/search',
    name: 'search',
    component: () => import('@/views/more/SearchView.vue'),
    meta: { tab: 'more', title: 'Поиск', inner: true, parent: '/more' },
  },
  {
    path: '/more/assistant',
    name: 'assistant',
    component: () => import('@/views/more/AssistantView.vue'),
    meta: { tab: 'more', title: 'Спросить Кузю', inner: true, parent: '/more' },
  },
  {
    path: '/more/mcp',
    name: 'mcp',
    component: () => import('@/views/more/McpView.vue'),
    meta: { tab: 'more', title: 'Настройки MCP', inner: true, parent: '/more' },
  },
  {
    path: '/dev/chat',
    name: 'dev-chat',
    component: () => import('@/views/dev/ChatEmulatorView.vue'),
    meta: { tab: 'more', title: 'Эмулятор чата MAX', inner: true, parent: '/more' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory('/'),
  routes,
  scrollBehavior(_to, _from, saved) {
    return saved ?? { top: 0 }
  },
})

/** «Назад»: по истории, а если её нет (диплинк) - на родительский раздел. */
export function goBack(): void {
  const parent = router.currentRoute.value.meta.parent ?? '/'
  if (window.history.state?.back) router.back()
  else void router.replace(parent)
}
