import { DOMWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { eventsApi } from '@/api/endpoints'
import {
  click,
  getButton,
  getByText,
  getField,
  queryButton,
  queryByText,
  settle,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute, type RenderOptions } from '@/test/harness'

/** Открыть событие и дождаться, пока оно загрузится. */
async function openEvent(id: number, options: RenderOptions = {}) {
  const rendered = await renderRoute(`/events/${id}`, options)
  await waitFor(() => document.querySelector('article h2'))
  return rendered
}

describe('Страница события', () => {
  it('показывает тип, место, организатора, участников и обсуждение', async () => {
    await openEvent(301)
    expect(getByText('Осенний субботник')).toBeTruthy()
    expect(getByText('Субботник')).toBeTruthy()
    expect(getByText('Двор, у детской площадки')).toBeTruthy()
    expect(getByText('Организатор: Марина Соколова')).toBeTruthy()
    expect(getByText(/Перчатки и грабли выдаст УК/)).toBeTruthy()
    expect(getByText('4 участника')).toBeTruthy()
    expect(getByText('свободно 16 из 20')).toBeTruthy()
    await waitFor(() => getByText('Грабли и мешки УК привезёт к 9:45'))
    expect(getByText('Зелёный, как в прошлом году')).toBeTruthy()
    expect(getButton('Иду')).toBeTruthy()
  })

  it('«Иду» записывает жителя, «Не смогу прийти» снимает запись', async () => {
    const { max } = await openEvent(301)
    await click('Иду')
    await waitFor(() => getByText('Вы идёте. Кузя напомнит за пару часов'))
    expect(getByText('5 участников')).toBeTruthy()
    await waitFor(() => getByText('Вы идёте! Кузя напомнит заранее'))
    expect(max.impact).toHaveBeenCalledWith('medium')

    await click('Не смогу прийти')
    await waitFor(() => getByText('Запись отменена. Передумаете - нажмите «Иду»'))
    expect(getByText('4 участника')).toBeTruthy()
    expect(queryByText('Вы идёте. Кузя напомнит за пару часов')).toBeNull()
  })

  it('если запись не сохранилась, возвращает как было и сообщает об ошибке', async () => {
    vi.spyOn(eventsApi, 'join').mockRejectedValue(
      new ApiError('http', 500, 'Кузя споткнулся на сервере. Попробуйте ещё раз'),
    )
    await openEvent(301)
    await click('Иду')
    await waitFor(() => getByText('Не удалось сохранить'))
    expect(getByText('4 участника')).toBeTruthy()
    expect(getButton('Иду')).toBeTruthy()
  })

  it('когда мест нет, кнопка записи недоступна', async () => {
    const real = eventsApi.get.bind(eventsApi)
    vi.spyOn(eventsApi, 'get').mockImplementation(async (id) => ({
      ...(await real(id)),
      max_participants: 4,
    }))
    await openEvent(301)
    const full = getButton('Мест нет')
    expect(full.hasAttribute('disabled')).toBe(true)
    expect(getByText('свободно 0 из 4')).toBeTruthy()
  })

  it('прошедшее событие нельзя отметить и нельзя менять', async () => {
    await openEvent(304)
    expect(getByText('Событие уже прошло')).toBeTruthy()
    expect(queryButton('Иду')).toBeNull()
    expect(queryButton('Не смогу прийти')).toBeNull()
    expect(queryButton('Изменить описание и фото')).toBeNull()
  })

  it('событие без участников зовёт быть первым, без комментариев - начать обсуждение', async () => {
    const real = eventsApi.get.bind(eventsApi)
    vi.spyOn(eventsApi, 'get').mockImplementation(async (id) => ({
      ...(await real(id)),
      participants: [],
      participants_count: 0,
    }))
    await openEvent(303)
    expect(getByText('Пока никто не отметился. Будьте первым!')).toBeTruthy()
    await waitFor(() => getByText(/Пока тихо/))
  })

  it('неизвестное событие: «Событие не найдено»', async () => {
    await renderRoute('/events/999')
    await waitFor(() => getByText('Событие не найдено'))
    expect(getByText('Не нашли: возможно, запись уже удалили')).toBeTruthy()
  })

  it('при ошибке сервера даёт повторить загрузку', async () => {
    await renderRoute('/events/301', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    await click('Попробовать ещё раз')
    expect(getByText('Не получилось загрузить')).toBeTruthy()
  })
})

describe('Обсуждение события', () => {
  it('отправляет комментарий кнопкой и очищает поле', async () => {
    const { max } = await openEvent(303)
    await waitFor(() => getByText(/Пока тихо/))
    const send = getButton('Отправить комментарий')
    expect(send.hasAttribute('disabled')).toBe(true)
    await type('Текст комментария', 'Принесу гитару')
    await click('Отправить комментарий')
    await waitFor(() => getByText('Принесу гитару'))
    expect(getField('Текст комментария').value).toBe('')
    expect(max.impact).toHaveBeenCalledWith('light')
    expect(queryByText(/Пока тихо/)).toBeNull()
  })

  it('отправляет комментарий клавишей Enter', async () => {
    await openEvent(303)
    await type('Текст комментария', 'Во сколько начинаем?')
    await new DOMWrapper(getField('Текст комментария')).trigger('keydown', { key: 'Enter' })
    await waitFor(() => getByText('Во сколько начинаем?'))
  })

  it('комментарий, который не пропустил модератор, объясняется предупреждением', async () => {
    vi.spyOn(eventsApi, 'comment').mockRejectedValue(new ApiError('http', 422, 'похоже на рекламу'))
    const { max } = await openEvent(301)
    await type('Текст комментария', 'Купите окна недорого')
    await click('Отправить комментарий')
    await waitFor(() => getByText('Кузя не пропустил: похоже на рекламу'))
    expect(max.notify).toHaveBeenCalledWith('warning')
    expect(getField('Текст комментария').value).toBe('Купите окна недорого')
  })

  it('при сбое сети говорит, что комментарий не отправлен', async () => {
    vi.spyOn(eventsApi, 'comment').mockRejectedValue(
      new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет'),
    )
    await openEvent(301)
    await type('Текст комментария', 'Буду')
    await click('Отправить комментарий')
    await waitFor(() => getByText('Комментарий не отправлен'))
  })

  it('если обсуждение не загрузилось, даёт повторить', async () => {
    const spy = vi
      .spyOn(eventsApi, 'comments')
      .mockRejectedValueOnce(new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет'))
    await openEvent(301)
    await waitFor(() => getByText('Нет связи с сервером. Проверьте интернет'))
    spy.mockRestore()
    await click('Повторить')
    await waitFor(() => getByText('Грабли и мешки УК привезёт к 9:45'))
  })
})

describe('Подробности события от организатора', () => {
  it('администратор меняет описание через шторку', async () => {
    // администратор в моке - Ильдар, он же организатор собрания 302
    const { max } = await openEvent(302, { scenario: { role: 'admin' } })
    await click('Изменить описание и фото')
    await waitFor(() => getByText('Подробности события'))
    const save = getButton('Сохранить')
    expect(save.hasAttribute('disabled')).toBe(true)
    await type('Описание', 'Смета в чате, приходите с паспортом')
    await click('Сохранить')
    await waitFor(() => getByText('Сохранено, соседи увидят обновление'))
    await waitFor(() => getByText('Смета в чате, приходите с паспортом'))
    expect(max.notify).toHaveBeenCalledWith('success')
  })

  it('житель не может менять чужое событие', async () => {
    await openEvent(301)
    expect(queryButton('Изменить описание и фото')).toBeNull()
    expect(queryByText('Добавьте подробности и фото')).toBeNull()
  })

  it('организатор добавляет фото, а потом удаляет лишнее', async () => {
    await openEvent(302, { scenario: { role: 'admin' } })
    await click('Изменить описание и фото')
    await waitFor(() => getByText('Подробности события'))
    const input = document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!
    const files = [
      new File(['1'], 'a.jpg', { type: 'image/jpeg' }),
      new File(['2'], 'b.jpg', { type: 'image/jpeg' }),
    ]
    Object.defineProperty(input, 'files', { configurable: true, value: files })
    await new DOMWrapper(input).trigger('change')
    await settle()
    await click('Сохранить')
    await waitFor(() => getByText('Сохранено, соседи увидят обновление'))

    await click('Изменить описание и фото')
    await waitFor(() => getByText('Фото события'))
    expect(getButton('Удалить фото 2')).toBeTruthy()
    await click('Удалить фото 1')
    await waitFor(() => !queryButton('Удалить фото 2'))
    expect(getButton('Удалить фото 1')).toBeTruthy()
  })

  it('если сохранить не вышло, шторка остаётся открытой с ошибкой', async () => {
    vi.spyOn(eventsApi, 'update').mockRejectedValue(
      new ApiError('http', 403, 'Недостаточно прав для этого действия'),
    )
    await openEvent(302, { scenario: { role: 'admin' } })
    await click('Изменить описание и фото')
    await type('Описание', 'Новое описание')
    await click('Сохранить')
    await waitFor(() => getByText('Не удалось сохранить'))
    expect(getByText('Подробности события')).toBeTruthy()
  })
})
