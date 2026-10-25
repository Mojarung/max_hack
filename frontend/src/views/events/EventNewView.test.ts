import { DOMWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import {
  click,
  getButton,
  getByText,
  getField,
  queryByText,
  settle,
  type,
  waitFor,
} from '@/test/dom'
import { ApiError } from '@/api/client'
import { eventsApi } from '@/api/endpoints'
import { renderRoute } from '@/test/harness'

/** Выбрать фото через скрытое поле «Галерея», как это делает телефон. */
async function pickPhotos(files: File[]): Promise<void> {
  const input = document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!
  Object.defineProperty(input, 'files', { configurable: true, value: files })
  await new DOMWrapper(input).trigger('change')
  await settle()
}

const photo = (name: string) => new File(['jpeg'], name, { type: 'image/jpeg' })

describe('Новое событие', () => {
  it('выбор типа подставляет название и даёт отклик вибрацией', async () => {
    const { max } = await renderRoute('/events/new')
    const meeting = getButton('Собрание')
    await click(meeting)
    expect(meeting.getAttribute('aria-checked')).toBe('true')
    expect(getField('Название').value).toBe('Собрание жильцов')
    expect(max.selection).toHaveBeenCalled()
    // своё название не перетираем, когда житель передумал с типом
    await click('Праздник')
    expect(getField('Название').value).toBe('Собрание жильцов')
  })

  it('пустая форма не отправляется и подсказывает, что заполнить', async () => {
    const { router, max } = await renderRoute('/events/new')
    await click('Создать событие')
    await waitFor(() => getByText('Проверьте поля формы'))
    expect(getByText('Как назовём событие?')).toBeTruthy()
    expect(getByText('Где собираемся?')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('warning')
    expect(router.currentRoute.value.path).toBe('/events/new')
  })

  it('не даёт назначить событие на прошедшее время', async () => {
    await renderRoute('/events/new')
    await type('Название', 'Чаепитие')
    await type('Место', 'Холл')
    await type('Дата', '2026-10-21')
    await type('Время', '09:00')
    await click('Создать событие')
    await waitFor(() => getByText('Время уже прошло, выберите будущее'))
    await type('Дата', '')
    await waitFor(() => getByText('Укажите дату и время'))
  })

  it('ограничение участников требует хотя бы двух человек', async () => {
    await renderRoute('/events/new')
    expect(queryByText('Сколько человек максимум')).toBeNull()
    await click(getField('Ограничить число участников'))
    await type('Сколько человек максимум', '1')
    await click('Создать событие')
    await waitFor(() => getByText('Минимум 2 участника'))
    await type('Сколько человек максимум', '15')
    expect(queryByText('Минимум 2 участника')).toBeNull()
  })

  it('создаёт событие и открывает его страницу с подсказкой добавить подробности', async () => {
    const { router, max } = await renderRoute('/events/new')
    await type('Название', 'Посадка деревьев')
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(true)
    await type('Место', 'Сквер у 3 подъезда')
    await click('Создать событие')
    await waitFor(() => router.currentRoute.value.path === '/events/1000')
    await waitFor(() => getByText('Событие создано'))
    await waitFor(() => getByText('Посадка деревьев'))
    expect(getByText('Сквер у 3 подъезда')).toBeTruthy()
    expect(getByText('Добавьте подробности и фото')).toBeTruthy()
    expect(getByText('Вы идёте. Кузя напомнит за пару часов')).toBeTruthy()
    // форма больше не «грязная»: MAX не спросит подтверждение при закрытии
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(false)
  })

  it('загружает фото вторым запросом после создания события', async () => {
    const { router } = await renderRoute('/events/new')
    await type('Название', 'Субботник у гаражей')
    await type('Место', 'Гаражи')
    await type('Подробности', 'Возьмите перчатки')
    await pickPhotos([photo('a.jpg'), photo('b.jpg')])
    expect(getByText('2 из 5 фото')).toBeTruthy()
    await click('Создать событие')
    await waitFor(() => router.currentRoute.value.path === '/events/1000')
    await waitFor(() => getByText('Возьмите перчатки'))
    expect(getButton('Изменить описание и фото')).toBeTruthy()
    expect(queryByText('Добавьте подробности и фото')).toBeNull()
  })
})

describe('Новое событие: сбои сервера', () => {
  it('если событие не создалось, остаётся на форме и объясняет причину', async () => {
    vi.spyOn(eventsApi, 'create').mockRejectedValue(
      new ApiError('http', 500, 'Кузя споткнулся на сервере. Попробуйте ещё раз'),
    )
    const { router } = await renderRoute('/events/new')
    await type('Название', 'Посадка деревьев')
    await type('Место', 'Сквер')
    await click('Создать событие')
    await waitFor(() => getByText('Не удалось создать событие'))
    expect(router.currentRoute.value.path).toBe('/events/new')
    expect(getField('Название').value).toBe('Посадка деревьев')
  })

  it('если фото не загрузились, событие всё равно открывается с предупреждением', async () => {
    vi.spyOn(eventsApi, 'addPhotos').mockRejectedValue(
      new ApiError('http', 413, 'Файл слишком большой'),
    )
    const { router } = await renderRoute('/events/new')
    await type('Название', 'Посадка деревьев')
    await type('Место', 'Сквер')
    await pickPhotos([photo('big.jpg')])
    await click('Создать событие')
    await waitFor(() => router.currentRoute.value.path === '/events/1000')
    await waitFor(() =>
      getByText('Событие создано, но фото не загрузились. Добавьте их на странице события'),
    )
  })
})
