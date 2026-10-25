import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { searchApi } from '@/api/endpoints'
import {
  click,
  getButton,
  getByText,
  getField,
  queryByText,
  textOf,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute } from '@/test/harness'

/** Поиск ждёт 400 мс после ввода: даём ему время. */
const SEARCH_WAIT_MS = 2500

function headings(): string[] {
  return Array.from(document.querySelectorAll('h2.section-title')).map(textOf)
}

describe('Поиск по дому', () => {
  it('до ввода предлагает слова и показывает заявки, которым нужны голоса', async () => {
    await renderRoute('/more/search')
    for (const word of ['лифт', 'крыша', 'коляска', 'субботник', 'шум']) {
      expect(getButton(word)).toBeTruthy()
    }
    expect(getByText('Ищем сразу по заявкам, событиям и вещам соседей.')).toBeTruthy()
    await waitFor(() => getByText('Нужны голоса'))
    expect(getByText('Течёт крыша над 9 этажом')).toBeTruthy()
    expect(getByText('Не горит свет в подъезде 3')).toBeTruthy()
  })

  it('подсказка «лифт» находит заявку и вещь соседа', async () => {
    await renderRoute('/more/search')
    await click('лифт')
    expect((getField('Поиск по дому') as HTMLInputElement).value).toBe('лифт')
    await waitFor(() => headings().length === 2, SEARCH_WAIT_MS)
    expect(headings()).toEqual(['Заявки · 1', 'Вещи соседей · 1'])
    expect(getByText('Не работает лифт в подъезде 1')).toBeTruthy()
    expect(getByText('Диван-книжка')).toBeTruthy()
    // подсказки прячутся, когда житель уже ищет
    expect(document.querySelector('.tags')).toBeNull()
  })

  it('находит события и ведёт в них', async () => {
    const { router } = await renderRoute('/more/search')
    await type(getField('Поиск по дому'), 'субботник')
    await waitFor(() => headings()[0] === 'События · 2', SEARCH_WAIT_MS)
    const link = getByText('Осенний субботник').closest('a')!
    expect(textOf(link)).toContain('Двор, у детской площадки')
    await click(link)
    await waitFor(() => router.currentRoute.value.path === '/events/301')
  })

  it('если ничего нет, так и говорит', async () => {
    await renderRoute('/more/search')
    await type(getField('Поиск по дому'), 'батут')
    await waitFor(() => getByText('Ничего не нашлось'), SEARCH_WAIT_MS)
    expect(getByText('Попробуйте другие слова')).toBeTruthy()
  })

  it('одна буква не ищет, а возвращает подсказки', async () => {
    const search = vi.spyOn(searchApi, 'search')
    await renderRoute('/more/search')
    await type(getField('Поиск по дому'), 'л')
    await new Promise((resolve) => setTimeout(resolve, 500))
    expect(search).not.toHaveBeenCalled()
    expect(getByText('Ищем сразу по заявкам, событиям и вещам соседей.')).toBeTruthy()
  })

  it('ошибка поиска видна жителю', async () => {
    vi.spyOn(searchApi, 'search').mockRejectedValue(
      new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет'),
    )
    await renderRoute('/more/search')
    await type(getField('Поиск по дому'), 'лифт')
    await waitFor(() => getByText('Нет связи с сервером. Проверьте интернет'), SEARCH_WAIT_MS)
    expect(queryByText('Заявки · 1')).toBeNull()
  })

  it('отменённый запрос не показывает ошибку', async () => {
    vi.spyOn(searchApi, 'search').mockRejectedValue(new ApiError('aborted', 0, 'Запрос отменён'))
    await renderRoute('/more/search')
    await type(getField('Поиск по дому'), 'лифт')
    await new Promise((resolve) => setTimeout(resolve, 600))
    expect(queryByText('Запрос отменён')).toBeNull()
  })

  it('без связи с сервером подсказки остаются, а блока голосования нет', async () => {
    await renderRoute('/more/search', { scenario: { name: 'error' } })
    expect(getButton('лифт')).toBeTruthy()
    expect(queryByText('Нужны голоса')).toBeNull()
  })
})
