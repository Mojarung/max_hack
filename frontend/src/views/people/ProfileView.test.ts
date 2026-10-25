import { DOMWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { peopleApi } from '@/api/endpoints'
import { scenario } from '@/mock/scenario'
import { useSessionStore } from '@/stores/session'
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
import { NOW, renderRoute } from '@/test/harness'
import { formatDate } from '@/utils/format'

const DAY = 86_400_000

/** Открытая шторка vaul (сообщение соседу, выбор аватарки). */
function inDrawer(): HTMLElement {
  return document.querySelector<HTMLElement>('[role="dialog"]')!
}

beforeEach(() => {
  // своё фото для аватарки мок превращает в object URL, а Node не принимает Blob из jsdom
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test/avatar')
})

describe('Свой профиль', () => {
  it('показывает имя, квартиру, уровень, очки, вклад в дом и награды', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    const since = formatDate(new Date(NOW.getTime() - 120 * DAY))
    expect(getByText(`Квартира 12 · в доме с ${since}`)).toBeTruthy()
    expect(getByText('уровень 3 · Добрый сосед')).toBeTruthy()
    expect(getByText('145 очков')).toBeTruthy()
    expect(getByText('заявка')).toBeTruthy()
    expect(getByText('голоса за соседей')).toBeTruthy()
    expect(getByText('события')).toBeTruthy()
    for (const award of ['Глаза дома', 'Голос соседа', 'Добрая рука', 'Чистый двор'])
      expect(getByText(award)).toBeTruthy()
  })

  it('себе нельзя написать или сказать спасибо, зато можно сменить аватарку', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    expect(queryButton('Написать')).toBeNull()
    expect(queryButton('Спасибо +5')).toBeNull()
    expect(getButton('Сменить аватарку')).toBeTruthy()
    expect(getField('Номер квартиры').value).toBe('12')
  })

  it('сохраняет номер квартиры по кнопке', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    await type(getField('Номер квартиры'), '14')
    await click(getButton('Сохранить'))
    await waitFor(() => getByText('Квартира сохранена'))
    expect(getByText(/^Квартира 14 · в доме с/)).toBeTruthy()
    expect(useSessionStore().me!.user.apartment).toBe('14')
  })

  it('сохраняет квартиру, когда житель уходит из поля', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    const field = getField('Номер квартиры')
    await type(field, '15')
    await new DOMWrapper(field).trigger('blur')
    await waitFor(() => getByText('Квартира сохранена'))
    expect(useSessionStore().me!.user.apartment).toBe('15')
  })

  it('не теряет введённую квартиру при уходе с экрана', async () => {
    const { router } = await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    await type(getField('Номер квартиры'), '16')
    await router.push('/people')
    await waitFor(() => router.currentRoute.value.path === '/people')
    expect(useSessionStore().me!.user.apartment).toBe('16')
    await waitFor(() => getByText('Квартира сохранена'))
  })

  it('пустая квартира убирает её из профиля', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    await type(getField('Номер квартиры'), '')
    await click(getButton('Сохранить'))
    await waitFor(() => getByText('Квартира сохранена'))
    expect(getByText(/^в доме с/)).toBeTruthy()
    expect(useSessionStore().me!.user.apartment).toBeNull()
  })

  it('не сохраняет квартиру, если сервер отказал, и говорит почему', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    scenario.name = 'error'
    await type(getField('Номер квартиры'), '20')
    await click(getButton('Сохранить'))
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    expect(useSessionStore().me!.user.apartment).toBe('12')
  })

  it('выбирает готовую аватарку и обновляет профиль', async () => {
    const { max } = await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    await click(getButton('Сменить аватарку'))
    await waitFor(() => getByText('Выберите картинку или поставьте своё фото'))
    await click(getButton('Картинка 3', inDrawer()))
    await waitFor(() => getByText('Аватарка обновлена'))
    expect(useSessionStore().me!.user.avatar).toBe('preset:3')
    expect(max.notify).toHaveBeenCalledWith('success')
  })

  it('ставит своё фото вместо картинки', async () => {
    await renderRoute('/people/1')
    await waitFor(() => getByText('Анна Петрова'))
    await click(getButton('Сменить аватарку'))
    await waitFor(() => getByText('Поставить своё фото'))
    const input = inDrawer().querySelector<HTMLInputElement>('input[type="file"]')!
    const photo = new File(['фото'], 'me.jpg', { type: 'image/jpeg' })
    Object.defineProperty(input, 'files', { configurable: true, value: [photo] })
    input.dispatchEvent(new Event('change'))
    await settle()
    await waitFor(() => getByText('Аватарка обновлена'))
    expect(useSessionStore().me!.user.avatar).toBe('upload')
  })
})

describe('Профиль соседа', () => {
  it('показывает администратора дома и кнопки «Написать» и «Спасибо»', async () => {
    await renderRoute('/people/2')
    await waitFor(() => getByText('Ильдар Хайруллин'))
    expect(getByText('администратор дома')).toBeTruthy()
    expect(getByText('уровень 5 · Хранитель дома')).toBeTruthy()
    expect(getButton('Написать')).toBeTruthy()
    expect(getButton('Спасибо +5')).toBeTruthy()
    expect(queryButton('Сменить аватарку')).toBeNull()
    expect(queryByText('Моя квартира')).toBeNull()
  })

  it('«Спасибо» добавляет соседу 5 очков и больше не нажимается', async () => {
    const { max } = await renderRoute('/people/2')
    await waitFor(() => getByText('Ильдар Хайруллин'))
    expect(getByText('420 очков')).toBeTruthy()
    await click(getButton('Спасибо +5'))
    await waitFor(() => getByText('Спасибо отправлено'))
    expect(getByText('Сосед получил +5 очков')).toBeTruthy()
    expect(getByText('425 очков')).toBeTruthy()
    expect(getByText('Соседи сказали спасибо 1 раз')).toBeTruthy()
    expect(getButton('Спасибо сказано').hasAttribute('disabled')).toBe(true)
    expect(max.notify).toHaveBeenCalledWith('success')
  })

  it('повторное «Спасибо» за день сервер не принимает, и житель видит почему', async () => {
    await renderRoute('/people/3')
    await waitFor(() => getByText('Марина Соколова'))
    // житель уже поблагодарил Марину с другого устройства, а экран ещё старый
    await peopleApi.thank(3)
    await click(getButton('Спасибо +5'))
    await waitFor(() => getByText('Вы уже благодарили этого соседа сегодня'))
  })

  it('без ника в MAX пишет соседу через Кузю', async () => {
    await renderRoute('/people/2')
    await waitFor(() => getByText('Ильдар Хайруллин'))
    await click(getButton('Написать'))
    await waitFor(() => getByText('Написать: Ильдар Хайруллин'))
    const send = getButton('Отправить', inDrawer())
    expect(send.hasAttribute('disabled')).toBe(true)
    await type(getField('Сообщение', inDrawer()), 'Добрый день! Когда собрание?')
    await click(getButton('Отправить', inDrawer()))
    await waitFor(() => getByText('Кузя передал сообщение'))
    expect(getByText('Сосед ответит вам в личных сообщениях MAX')).toBeTruthy()
  })

  it('если сообщение не ушло, говорит об этом', async () => {
    await renderRoute('/people/2')
    await waitFor(() => getByText('Ильдар Хайруллин'))
    vi.spyOn(peopleApi, 'message').mockRejectedValue(new Error('Кузя занят'))
    await click(getButton('Написать'))
    await waitFor(() => getByText('Написать: Ильдар Хайруллин'))
    await type(getField('Сообщение', inDrawer()), 'Привет')
    await click(getButton('Отправить', inDrawer()))
    await waitFor(() => getByText('Не удалось отправить'))
    expect(getByText('Кузя занят')).toBeTruthy()
  })

  it('с ником в MAX открывает личный чат с соседом', async () => {
    const real = peopleApi.profile
    vi.spyOn(peopleApi, 'profile').mockImplementation(async (id) => ({
      ...(await real(id)),
      username: 'ildar_h',
    }))
    const { max } = await renderRoute('/people/2')
    await waitFor(() => getByText('Ильдар Хайруллин'))
    await click(getButton('Написать'))
    expect(max.openMaxLink).toHaveBeenCalledWith('https://max.ru/ildar_h')
    expect(queryByText('Написать: Ильдар Хайруллин')).toBeNull()
  })

  it('неизвестный житель: «Житель не найден» и путь ко всем соседям', async () => {
    const { router } = await renderRoute('/people/999')
    await waitFor(() => getByText('Житель не найден'))
    expect(getByText('Возможно, он уже не состоит в чате дома')).toBeTruthy()
    await click('Все соседи')
    await waitFor(() => router.currentRoute.value.path === '/people')
  })

  it('ошибка сервера: показывает причину и загружает заново по кнопке', async () => {
    await renderRoute('/people/2', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    scenario.name = 'default'
    await click('Попробовать ещё раз')
    await waitFor(() => getByText('Ильдар Хайруллин'))
  })
})
