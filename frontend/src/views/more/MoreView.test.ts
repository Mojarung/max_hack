import { describe, expect, it, vi } from 'vitest'
import { mockRequest } from '@/mock/server'
import { click, getButton, getByText, queryByText, textOf, waitFor } from '@/test/dom'
import { renderRoute } from '@/test/harness'

/** Названия пунктов в группе «Мой дом». */
function entries(): string[] {
  const nav = document.querySelector('nav[aria-label="Разделы"]')
  return Array.from(nav?.querySelectorAll('a .font-semibold') ?? []).map((el) => textOf(el))
}

describe('Экран «Ещё»', () => {
  it('показывает профиль жителя и его дом', async () => {
    await renderRoute('/more')
    await waitFor(() => getByText('Анна Петрова'))
    expect(getByText(/Квартира 12/).textContent).toMatch(/Добрый сосед · 145 очков/)
    expect(queryByText('Укажите номер квартиры')).toBeNull()
    await waitFor(() => getByText('Мой дом, нажмите, чтобы сменить'))
    expect(getByText('Ленинского Комсомола, 5')).toBeTruthy()
    expect(getByText('Домовой Кузя · MAX')).toBeTruthy()
  })

  it('у жителя в MAX нет служебных разделов', async () => {
    await renderRoute('/more')
    await waitFor(() => getByText('Анна Петрова'))
    expect(entries()).toEqual([
      'О доме',
      'Объявления',
      'Документы',
      'Соседи',
      'Поиск',
      'Спросить Кузю',
      'Награды и рейтинг',
    ])
  })

  it('администратор видит «Навыки Кузи»', async () => {
    await renderRoute('/more', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Ильдар Хайруллин'))
    expect(entries()).toContain('Навыки Кузи')
    expect(entries()).not.toContain('Эмулятор чата MAX')
  })

  it('в демо без MAX есть эмулятор чата и навыки, а внизу подпись про демо', async () => {
    await renderRoute('/more', { scenario: { inMax: false } })
    await waitFor(() => getByText('Анна Петрова'))
    expect(entries().slice(-2)).toEqual(['Эмулятор чата MAX', 'Навыки Кузи'])
    expect(getByText('Домовой Кузя · демо-режим в браузере')).toBeTruthy()
  })

  it('без номера квартиры просит его указать', async () => {
    await mockRequest('PATCH', '/house', {}, { apartment: '' })
    await renderRoute('/more')
    await waitFor(() => getByText('Укажите номер квартиры'))
    expect(queryByText(/Квартира 12/)).toBeNull()
  })

  it('кнопка чата с Кузей открывает бота в MAX', async () => {
    const { max } = await renderRoute('/more')
    await click(await waitFor(() => getButton('Открыть чат с Кузей в MAX')))
    expect(max.openMaxLink).toHaveBeenCalledWith('https://max.ru/domovoy_kuzya_bot')
  })

  it('вне MAX ссылка на бота открывается в новой вкладке', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    await renderRoute('/more', { scenario: { inMax: false } })
    await click(await waitFor(() => getButton('Открыть чат с Кузей в MAX')))
    expect(open).toHaveBeenCalledWith(
      'https://max.ru/domovoy_kuzya_bot',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('пункты ведут в свои разделы', async () => {
    const { router } = await renderRoute('/more')
    await click(await waitFor(() => getByText('Безопасность').closest('a')!))
    await waitFor(() => router.currentRoute.value.path === '/more/safety')

    await router.push('/more')
    await click(await waitFor(() => getButton('Мой профиль')))
    await waitFor(() => router.currentRoute.value.path === '/people/1')
  })

  it('нажатие на дом открывает список домов', async () => {
    await renderRoute('/more')
    await click(
      await waitFor(() => getByText('Мой дом, нажмите, чтобы сменить').closest('button')!),
    )
    await waitFor(() => getByText('Ваши дома'))
    expect(getByText('Созидателей, 34')).toBeTruthy()
  })
})
