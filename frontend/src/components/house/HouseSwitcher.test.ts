import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { Toaster } from '@/components/ui/sonner'
import { useSessionStore } from '@/stores/session'
import { click, getButton, getByText, waitFor } from '@/test/dom'
import { renderComponent, useScenario } from '@/test/harness'
import HouseSwitcher from './HouseSwitcher.vue'

/** Переключатель вместе с тостами: так видно, что житель прочтёт после выбора. */
const WithToasts = defineComponent({
  setup: () => () => [h(HouseSwitcher), h(Toaster)],
})

/** Строка дома в шторке «Ваши дома». */
function houseRow(title: string): HTMLButtonElement {
  const list = document.querySelector('[aria-label="Список домов"]')
  const row = Array.from(list?.querySelectorAll<HTMLButtonElement>('button') ?? []).find((b) =>
    b.textContent?.includes(title),
  )
  if (!row) throw new Error(`Нет дома «${title}» в списке`)
  return row
}

/** Открыта ли шторка: vaul ждёт конца анимации, которой в jsdom нет, поэтому смотрим на data-state. */
function drawerState(): string | null {
  return document.querySelector('[role="dialog"]')?.getAttribute('data-state') ?? null
}

async function openSwitcher(options: Parameters<typeof renderComponent>[1] = {}) {
  const rendered = await renderComponent(WithToasts, { session: true, ...options })
  await waitFor(() => useSessionStore().houses.length === 2)
  await click(getButton('Дом: Ленинского Комсомола, 5. Выбрать другой дом'))
  await waitFor(() => getByText('Ваши дома'))
  return rendered
}

describe('Выбор дома', () => {
  it('в шторке все дома жителя с адресом, текущий отмечен', async () => {
    await openSwitcher()
    expect(getByText('Дома появляются сами из чатов, где вы состоите вместе с Кузей')).toBeTruthy()
    const current = houseRow('Ленинского Комсомола, 5')
    expect(current.getAttribute('aria-current')).toBe('true')
    expect(current.textContent).toContain('Ульяновск, пр-т Ленинского Комсомола, 5')
    expect(current.textContent).not.toContain('вы администратор')
    const other = houseRow('Созидателей, 34')
    expect(other.getAttribute('aria-current')).toBeNull()
    expect(other.textContent).toContain('Ульяновск, пр-т Созидателей, 34')
  })

  it('администратору дома подписывает его роль', async () => {
    await openSwitcher({ scenario: { role: 'admin' } })
    expect(houseRow('Ленинского Комсомола, 5').textContent).toContain('вы администратор')
  })

  it('дом без адреса так и подписан', async () => {
    await openSwitcher({ scenario: { setup: true } })
    expect(houseRow('Ленинского Комсомола, 5').textContent).toContain('Адрес ещё не указан')
  })

  it('выбор другого дома переключает всё приложение на него', async () => {
    const { max } = await openSwitcher()
    await click(houseRow('Созидателей, 34'))
    const session = useSessionStore()
    await waitFor(() => session.me?.house.id === 2)
    expect(max.selection).toHaveBeenCalled()
    await waitFor(() => getByText('Дом: Созидателей, 34'))
    await waitFor(() => getButton('Дом: Созидателей, 34. Выбрать другой дом'))
    // шторка закрывается (в jsdom она остаётся в разметке, но в состоянии closed)
    await waitFor(() => drawerState() === 'closed')
  })

  it('повторный выбор текущего дома ничего не ломает', async () => {
    await openSwitcher()
    await click(houseRow('Ленинского Комсомола, 5'))
    expect(useSessionStore().me?.house.id).toBe(1)
  })

  it('«Найти мои дома» сообщает, что новых нет, и подсказывает почему', async () => {
    await openSwitcher()
    await click('Найти мои дома')
    await waitFor(() => getByText('Новых домов не нашлось'))
    expect(getByText('Кузя видит только чаты, куда его добавили')).toBeTruthy()
  })

  it('«Найти мои дома» считает новые дома', async () => {
    await openSwitcher()
    const session = useSessionStore()
    session.houses = session.houses.slice(0, 1)
    await click('Найти мои дома')
    await waitFor(() => getByText('Нашёл ещё 1 дом'))
  })

  it('если проверить чаты не вышло, так и говорит', async () => {
    await openSwitcher()
    useScenario({ name: 'error' })
    await click('Найти мои дома')
    await waitFor(() => getByText('Не удалось проверить чаты'))
  })
})
