import { describe, expect, it } from 'vitest'
import { useSessionStore } from '@/stores/session'
import { click, getButton, getByText, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import { defineComponent, h } from 'vue'
import { Toaster } from '@/components/ui/sonner'
import DemoUserSwitcher from './DemoUserSwitcher.vue'

/** Компонент вместе с тостами: так видно, что житель прочтёт после действия. */
const WithToasts = defineComponent({
  inheritAttrs: false,
  setup:
    (_, { attrs }) =>
    () => [h(DemoUserSwitcher, attrs), h(Toaster)],
})

/** Пункт меню жителя по имени: в списке Vuetify это элемент с role="option" или ссылка. */
function menuItem(name: string): HTMLElement {
  const item = Array.from(document.querySelectorAll<HTMLElement>('.v-list-item')).find((el) =>
    el.textContent?.includes(name),
  )
  if (!item) throw new Error(`Нет жителя «${name}» в меню`)
  return item
}

describe('Переключатель демо-жителей', () => {
  it('показывает, под кем вы вошли', async () => {
    await renderComponent(WithToasts, { session: true, scenario: { inMax: false } })
    const button = getButton('Демо-режим. Сейчас: Анна. Сменить жителя')
    expect(button.textContent).toContain('Демо: Анна')
  })

  it('в меню все соседи с квартирой и ролью, текущий отмечен', async () => {
    await renderComponent(WithToasts, { session: true, scenario: { inMax: false } })
    await click(getButton(/Демо-режим/))
    await waitFor(() => getByText('Войти как житель (демо)'))
    expect(menuItem('Анна Петрова').textContent).toContain('кв. 12')
    expect(menuItem('Ильдар Хайруллин').textContent).toContain('кв. 45 · администратор')
    expect(menuItem('Анна Петрова').classList.contains('v-list-item--active')).toBe(true)
  })

  it('выбор другого жителя входит под ним и запоминает выбор', async () => {
    await renderComponent(WithToasts, { session: true, scenario: { inMax: false } })
    const session = useSessionStore()
    await click(getButton(/Демо-режим/))
    await waitFor(() => menuItem('Марина Соколова'))
    await click(menuItem('Марина Соколова'))
    await waitFor(() => session.me?.user.first_name === 'Марина')
    expect(localStorage.getItem('kuzya.devUser')).toBe('1003')
    await waitFor(() => getByText('Теперь вы: Марина'))
    await waitFor(() => getButton('Демо-режим. Сейчас: Марина. Сменить жителя'))
  })

  it('после перезахода помнит выбранного жителя', async () => {
    localStorage.setItem('kuzya.devUser', '1004')
    await renderComponent(WithToasts, { session: true, scenario: { inMax: false } })
    expect(useSessionStore().me?.user.first_name).toBe('Рустем')
    expect(getButton(/Демо-режим/).textContent).toContain('Демо: Рустем')
  })
})
