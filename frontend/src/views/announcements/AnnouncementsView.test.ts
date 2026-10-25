import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { announcementsApi } from '@/api/endpoints'
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
import { renderRoute, useScenario } from '@/test/harness'

/** Заголовки карточек объявлений в порядке на экране. */
function titles(): string[] {
  return Array.from(document.querySelectorAll('article h3')).map((h) =>
    (h.textContent ?? '').replace('Закреплено.', '').replace(/\s+/g, ' ').trim(),
  )
}

describe('Объявления дома', () => {
  it('показывает объявления: закреплённое сверху', async () => {
    await renderRoute('/announcements')
    await waitFor(() => getByText('Покраска подъезда 2'))
    expect(titles()).toEqual(['Отключение горячей воды 1-3 октября', 'Покраска подъезда 2'])
    expect(getByText(/закреплено/)).toBeTruthy()
    // житель не может закреплять и удалять чужие объявления
    expect(queryButton('Закрепить')).toBeNull()
    expect(queryButton('Удалить')).toBeNull()
  })

  it('житель пишет объявление: оно появляется первым среди незакреплённых', async () => {
    const { max } = await renderRoute('/announcements')
    await waitFor(() => getByText('Покраска подъезда 2'))

    await click('Написать объявление')
    await waitFor(() => getByText('Новое объявление'))
    const publish = getButton('Опубликовать')
    expect(publish.hasAttribute('disabled')).toBe(true)

    await type(getField('Заголовок'), 'Собрание во дворе')
    await type(getField('Подробности'), 'В субботу в 11:00 у второго подъезда')
    expect(getButton('Опубликовать').hasAttribute('disabled')).toBe(false)
    await click('Опубликовать')

    await waitFor(() => getByText('Объявление опубликовано'))
    expect(getByText('Кузя написал о нём в чат дома')).toBeTruthy()
    expect(titles()).toEqual([
      'Отключение горячей воды 1-3 октября',
      'Собрание во дворе',
      'Покраска подъезда 2',
    ])
    // своё объявление можно удалить
    expect(getButton('Удалить')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('success')
  })

  it('слишком короткий заголовок не даёт опубликовать', async () => {
    await renderRoute('/announcements')
    await waitFor(() => getByText('Покраска подъезда 2'))
    await click('Написать объявление')
    await type(await waitFor(() => getField('Заголовок')), 'Ой')
    expect(getButton('Опубликовать').hasAttribute('disabled')).toBe(true)
  })

  it('администратор закрепляет и открепляет объявление', async () => {
    await renderRoute('/announcements', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Покраска подъезда 2'))
    expect(getButton('Открепить')).toBeTruthy()

    await click('Закрепить')
    await waitFor(() => !queryButton('Закрепить'))
    expect(titles()).toEqual(['Отключение горячей воды 1-3 октября', 'Покраска подъезда 2'])
    expect(document.querySelectorAll('article.announcement--pinned')).toHaveLength(2)

    // открепляем первое: теперь сверху закреплённая «Покраска»
    await click(getButton('Открепить'))
    await waitFor(() => titles()[0] === 'Покраска подъезда 2')
  })

  it('удаление спрашивает подтверждение и убирает объявление', async () => {
    await renderRoute('/announcements', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Покраска подъезда 2'))

    const card = getByText('Покраска подъезда 2').closest('article') as HTMLElement
    await click(getButton('Удалить', card))
    await waitFor(() => getByText('Удалить «Покраска подъезда 2»?'))

    // «Оставить» ничего не удаляет
    await click('Оставить')
    await waitFor(() => !queryByText('Удалить «Покраска подъезда 2»?'))
    expect(getByText('Покраска подъезда 2')).toBeTruthy()

    await click(getButton('Удалить', card))
    const dialog = await waitFor(() => document.querySelector('[role="dialog"]')!)
    expect(dialog.textContent).toContain(
      'Объявление пропадёт у всех соседей. Вернуть не получится.',
    )
    await click(getButton('Удалить', dialog))
    await waitFor(() => getByText('Объявление удалено'))
    expect(titles()).toEqual(['Отключение горячей воды 1-3 октября'])
  })

  it('если закрепить или удалить не вышло, объявление остаётся как было', async () => {
    vi.spyOn(announcementsApi, 'pin').mockRejectedValue(
      new ApiError('http', 403, 'Недостаточно прав для этого действия'),
    )
    vi.spyOn(announcementsApi, 'remove').mockRejectedValue(
      new ApiError('http', 404, 'Не нашли: возможно, запись уже удалили'),
    )
    const { max } = await renderRoute('/announcements', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Покраска подъезда 2'))

    await click('Закрепить')
    await waitFor(() => getByText('Недостаточно прав для этого действия'))
    expect(getButton('Закрепить')).toBeTruthy()

    const card = getByText('Покраска подъезда 2').closest('article') as HTMLElement
    await click(getButton('Удалить', card))
    const dialog = await waitFor(() => document.querySelector('[role="dialog"]')!)
    await click(getButton('Удалить', dialog))
    await waitFor(() => getByText('Не нашли: возможно, запись уже удалили'))
    expect(titles()).toEqual(['Отключение горячей воды 1-3 октября', 'Покраска подъезда 2'])
    expect(max.notify).toHaveBeenCalledWith('error')
  })

  it('без объявлений предлагает написать первое', async () => {
    vi.spyOn(announcementsApi, 'list').mockResolvedValue([])
    await renderRoute('/announcements')
    await waitFor(() => getByText('Объявлений пока нет'))
    expect(
      getByText('Предупредите соседей об отключении воды или позовите на собрание'),
    ).toBeTruthy()
    // кнопка в пустом экране открывает ту же форму, что и плавающая
    const buttons = document.querySelectorAll('section[role="status"] .v-btn')
    expect(buttons).toHaveLength(1)
    await click(buttons[0]!)
    await waitFor(() => getByText('Новое объявление'))
  })

  it('если публикация не удалась, говорит об этом и оставляет форму', async () => {
    vi.spyOn(announcementsApi, 'create').mockRejectedValue(
      new ApiError('http', 429, 'Слишком часто. Подождите немного'),
    )
    const { max } = await renderRoute('/announcements')
    await waitFor(() => getByText('Покраска подъезда 2'))
    await click('Написать объявление')
    await type(await waitFor(() => getField('Заголовок')), 'Собрание во дворе')
    await click('Опубликовать')
    await waitFor(() => getByText('Не получилось опубликовать'))
    expect(getByText('Слишком часто. Подождите немного')).toBeTruthy()
    expect(getByText('Новое объявление')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('error')
  })

  it('при ошибке сервера показывает текст ошибки, повтор загружает список', async () => {
    await renderRoute('/announcements', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    expect(getByText('Не получилось загрузить')).toBeTruthy()
    expect(queryByText('Покраска подъезда 2')).toBeNull()

    // сервер ожил: повтор показывает объявления
    useScenario({})
    await click('Попробовать ещё раз')
    await waitFor(() => getByText('Покраска подъезда 2'))
  })
})
