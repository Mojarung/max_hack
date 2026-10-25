import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { listingsApi } from '@/api/endpoints'
import {
  click,
  getButton,
  getByText,
  getField,
  queryButton,
  queryByText,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute, type RenderOptions } from '@/test/harness'

/** Кнопки выбора статуса своего объявления (в шапке тоже есть чип статуса). */
const statusGroup = () =>
  document.querySelector('[role="radiogroup"][aria-label="Статус объявления"]')!

/** Открыть объявление и дождаться заголовка. */
async function openListing(id: number, options: RenderOptions = {}) {
  const rendered = await renderRoute(`/market/${id}`, options)
  await waitFor(() => document.querySelector('article h2'))
  return rendered
}

const serverError = () =>
  new ApiError('http', 500, 'Кузя споткнулся на сервере. Попробуйте ещё раз')

describe('Объявление соседа', () => {
  it('показывает цену, категорию, описание и продавца', async () => {
    await openListing(202)
    expect(getByText('Диван-книжка')).toBeTruthy()
    expect(getByText(/3\s500 ₽/)).toBeTruthy()
    expect(getByText('Мебель')).toBeTruthy()
    expect(getByText(/Раскладной, чистый, без пятен/)).toBeTruthy()
    const seller = document.querySelector('a[href="/people/4"]')!
    expect(seller.getAttribute('aria-label')).toBe('Продавец: Рустем Галиев. Открыть профиль')
    expect(seller.textContent).toContain('Квартира 88')
    expect(queryByText('Ваше объявление')).toBeNull()
  })

  it('пишет продавцу через Кузю с готовым текстом', async () => {
    await openListing(202)
    await click('Написать продавцу')
    await waitFor(() => getByText('Сообщение продавцу'))
    expect(getField('Ваше сообщение').value).toBe('Здравствуйте! Ещё актуально?')
    await click('Отправить')
    await waitFor(() => getByText('Кузя передал сообщение'))
    expect(getByText('Продавец получит его в личных сообщениях MAX')).toBeTruthy()
  })

  it('за бесплатной вещью предлагает «Хочу забрать», пустое сообщение не отправить', async () => {
    const contact = vi.spyOn(listingsApi, 'contact')
    await openListing(201)
    expect(getByText('Даром')).toBeTruthy()
    await click('Хочу забрать')
    await waitFor(() => getByText('Сообщение автору'))
    expect(getField('Ваше сообщение').value).toBe('Здравствуйте! Можно забрать? Когда удобно?')
    await type('Ваше сообщение', '   ')
    expect(getButton('Отправить').hasAttribute('disabled')).toBe(true)
    expect(contact).not.toHaveBeenCalled()
  })

  it('если сообщение не ушло, говорит об этом', async () => {
    vi.spyOn(listingsApi, 'contact').mockRejectedValue(serverError())
    await openListing(202)
    await click('Написать продавцу')
    await click(await waitFor(() => getButton('Отправить')))
    await waitFor(() => getByText('Сообщение не отправлено'))
  })

  it('забронированная вещь помечена', async () => {
    await openListing(204)
    expect(getByText('Забронировано')).toBeTruthy()
  })

  it('закрытое объявление нельзя написать', async () => {
    const real = listingsApi.get.bind(listingsApi)
    vi.spyOn(listingsApi, 'get').mockImplementation(async (id) => ({
      ...(await real(id)),
      status: 'closed' as const,
    }))
    await openListing(202)
    expect(getByText('Закрыто')).toBeTruthy()
    expect(getButton('Объявление закрыто').hasAttribute('disabled')).toBe(true)
  })

  it('из карточки продавца открывается его профиль', async () => {
    const { router } = await openListing(202)
    await click(document.querySelector('a[href="/people/4"]')!)
    await waitFor(() => router.currentRoute.value.path === '/people/4')
  })

  it('неизвестное объявление: «Объявление не найдено»', async () => {
    await renderRoute('/market/999')
    await waitFor(() => getByText('Объявление не найдено'))
    expect(getByText('Не нашли: возможно, запись уже удалили')).toBeTruthy()
  })

  it('при ошибке сервера даёт повторить', async () => {
    await renderRoute('/market/202', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    await click('Попробовать ещё раз')
    expect(getByText('Не получилось загрузить')).toBeTruthy()
  })
})

describe('Своё объявление', () => {
  it('житель меняет статус: забронировано, потом закрыто', async () => {
    const { max } = await openListing(205)
    expect(getByText('Ваше объявление')).toBeTruthy()
    expect(queryButton('Написать продавцу')).toBeNull()
    expect(getButton('В продаже', statusGroup()).getAttribute('aria-checked')).toBe('true')

    await click('Забронировано')
    await waitFor(() => getByText('Статус: забронировано'))
    expect(getButton('Забронировано', statusGroup()).getAttribute('aria-checked')).toBe('true')
    expect(max.selection).toHaveBeenCalled()

    await click('Закрыто')
    await waitFor(() => getByText('Статус: закрыто'))
    expect(getButton('Закрыто', statusGroup()).getAttribute('aria-checked')).toBe('true')
  })

  it('повторное нажатие на текущий статус ничего не отправляет', async () => {
    const setStatus = vi.spyOn(listingsApi, 'setStatus')
    await openListing(205)
    await click('В продаже')
    expect(setStatus).not.toHaveBeenCalled()
  })

  it('если статус не сохранился, сообщает об ошибке', async () => {
    vi.spyOn(listingsApi, 'setStatus').mockRejectedValue(serverError())
    await openListing(205)
    await click('Забронировано')
    await waitFor(() => getByText('Статус не изменился'))
    expect(getButton('В продаже', statusGroup()).getAttribute('aria-checked')).toBe('true')
  })

  it('удаление спрашивает подтверждение и возвращает к списку', async () => {
    const { router } = await openListing(205)
    await click('Удалить объявление')
    await waitFor(() => getByText('Удалить объявление?'))
    await click('Отмена')
    await waitFor(() => !document.querySelector('.v-overlay--active'))
    expect(router.currentRoute.value.path).toBe('/market/205')

    await click('Удалить объявление')
    await click(await waitFor(() => getButton('Удалить')))
    await waitFor(() => router.currentRoute.value.path === '/market')
    await waitFor(() => getByText('Объявление удалено'))
    await waitFor(() => document.querySelector('a.card-soft[href="/market/202"]'))
    expect(document.querySelector('a.card-soft[href="/market/205"]')).toBeNull()
  })

  it('если удалить не вышло, остаётся на объявлении', async () => {
    vi.spyOn(listingsApi, 'remove').mockRejectedValue(serverError())
    const { router } = await openListing(205)
    await click('Удалить объявление')
    await click(await waitFor(() => getButton('Удалить')))
    await waitFor(() => getByText('Не удалось удалить'))
    expect(router.currentRoute.value.path).toBe('/market/205')
  })
})
