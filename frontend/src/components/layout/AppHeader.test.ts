import { afterEach, describe, expect, it } from 'vitest'
import { realtimeStatus } from '@/realtime/sse'
import { click, getButton, queryButton, queryByText, settle, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import { useSessionStore } from '@/stores/session'
import AppHeader from './AppHeader.vue'

function title(): string {
  return document.querySelector('.app-header__title')?.textContent?.trim() ?? ''
}

afterEach(() => {
  realtimeStatus.value = 'idle'
})

describe('Шапка', () => {
  it('на главной показывает название дома кнопкой выбора, если домов несколько', async () => {
    await renderComponent(AppHeader, { session: true, path: '/' })
    await waitFor(() => useSessionStore().houses.length === 2)
    expect(getButton('Дом: Ленинского Комсомола, 5. Выбрать другой дом')).toBeTruthy()
    expect(document.querySelector('a[aria-label="На главную"]')).not.toBeNull()
    expect(queryButton('Назад')).toBeNull()
  })

  it('с одним домом название просто текстом', async () => {
    await renderComponent(AppHeader, { session: true, path: '/' })
    const session = useSessionStore()
    await waitFor(() => session.houses.length === 2)
    session.houses = session.houses.slice(0, 1)
    await settle()
    expect(title()).toBe('Ленинского Комсомола, 5')
    expect(queryButton(/Выбрать другой дом/)).toBeNull()
  })

  it('на разделе показывает его название', async () => {
    await renderComponent(AppHeader, { session: true, path: '/more' })
    expect(title()).toBe('Ещё')
  })

  it('на внутреннем экране есть «Назад», и оно ведёт в родительский раздел', async () => {
    const { router } = await renderComponent(AppHeader, {
      session: true,
      path: '/more/achievements',
    })
    expect(title()).toBe('Награды и рейтинг')
    expect(document.querySelector('a[aria-label="На главную"]')).toBeNull()
    await click('Назад')
    await waitFor(() => router.currentRoute.value.path === '/more')
  })

  it('при обрыве связи предупреждает «Нет связи»', async () => {
    await renderComponent(AppHeader, { session: true, path: '/more' })
    expect(queryByText('Нет связи')).toBeNull()
    realtimeStatus.value = 'reconnecting'
    await settle()
    await waitFor(() => queryByText('Нет связи'))
  })

  it('вне MAX показывает переключатель демо-жителей', async () => {
    await renderComponent(AppHeader, {
      session: true,
      path: '/more',
      scenario: { inMax: false },
    })
    expect(getButton('Демо-режим. Сейчас: Анна. Сменить жителя')).toBeTruthy()
  })

  it('в эмуляторе чата переключатель жителей не показывается', async () => {
    await renderComponent(AppHeader, {
      session: true,
      path: '/dev/chat',
      scenario: { inMax: false },
    })
    expect(queryButton(/Демо-режим/)).toBeNull()
  })

  it('внутри MAX переключателя жителей нет', async () => {
    await renderComponent(AppHeader, { session: true, path: '/more' })
    expect(queryButton(/Демо-режим/)).toBeNull()
  })
})
