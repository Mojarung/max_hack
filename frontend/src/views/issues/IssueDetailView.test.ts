import { afterEach, describe, expect, it, vi } from 'vitest'
import { setDevUser } from '@/api/client'
import { issuesApi } from '@/api/endpoints'
import { mockRequest } from '@/mock/server'
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
import { NOW, renderRoute, useScenario } from '@/test/harness'

const HOUR = 3_600_000
const UK = 'в управляющую компанию «Уютный дом»'

/** Буфер обмена браузера: в jsdom его нет. */
function stubClipboard(writeText = vi.fn().mockResolvedValue(undefined)): typeof writeText {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  })
  return writeText
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'clipboard')
  Reflect.deleteProperty(navigator, 'share')
})

describe('Карточка заявки: голосование', () => {
  it('показывает суть заявки, место, автора и сколько голосов не хватает', async () => {
    await renderRoute('/issues/101')
    await waitFor(() => getByText('Течёт крыша над 9 этажом'))
    expect(getByText('Подъезд 2, 9 этаж')).toBeTruthy()
    expect(getByText('Собираем голоса')).toBeTruthy()
    expect(getByText(/Когда поддержат ещё 2 соседа/)).toBeTruthy()
    expect(getByText(new RegExp(`Кузя отправит его ${UK}`))).toBeTruthy()
    const author = getButton('Автор: Марина Соколова. Открыть профиль')
    expect(author.getAttribute('href')).toBe('/people/3')
    expect(getByText('Как идут дела')).toBeTruthy()
    expect(getByText('Кузя написал о заявке в чат дома')).toBeTruthy()
  })

  it('голос жителя засчитывается, а вибро подтверждает нажатие', async () => {
    const { max } = await renderRoute('/issues/101')
    await waitFor(() => getButton('Меня это тоже касается'))
    await click('Меня это тоже касается')
    await waitFor(() => getByText('Голос учтён, спасибо!'))
    expect(max.impact).toHaveBeenCalledWith('medium')
    expect(getByText('Вы поддержали. Кузя учтёт ваш голос в обращении.')).toBeTruthy()
    expect(getByText(/Когда поддержит ещё 1 сосед,/)).toBeTruthy()
    expect(document.querySelector('[aria-label="Голосов: 5 из 6"]')).not.toBeNull()
  })

  it('голос можно отозвать', async () => {
    await renderRoute('/issues/102')
    await waitFor(() => getButton('Отозвать голос'))
    await click('Отозвать голос')
    await waitFor(() => getByText('Голос отозван'))
    expect(getButton('Меня это тоже касается')).toBeTruthy()
    expect(document.querySelector('[aria-label="Голосов: 1 из 6"]')).not.toBeNull()
  })

  it('последний нужный голос отправляет обращение и запускает срок', async () => {
    // демо в браузере; сосед Рустем уже поддержал заявку: до порога не хватает одного голоса
    useScenario({ inMax: false })
    setDevUser(1004)
    await mockRequest('POST', '/issues/101/vote')
    setDevUser(null)

    await renderRoute('/issues/101')
    await waitFor(() => getButton('Меня это тоже касается'))
    expect(getByText(/Когда поддержит ещё 1 сосед,/)).toBeTruthy()
    await click('Меня это тоже касается')
    await waitFor(() => getByText('Голосов хватает!'))
    expect(getByText(`Кузя отправил обращение ${UK}`)).toBeTruthy()
    await waitFor(() => getByText('Обращение отправлено: управляющая компания «Уютный дом»'))
    expect(getByText('Отправлено')).toBeTruthy()
    expect(queryButton('Меня это тоже касается')).toBeNull()
    const timer = document.querySelector('[role="timer"]')
    expect(timer?.textContent).toContain('1 д')
  })

  it('если голос не сохранился, возвращает кнопку и сообщает об ошибке', async () => {
    await renderRoute('/issues/101')
    await waitFor(() => getButton('Меня это тоже касается'))
    // пока житель смотрел карточку, голосование закрылось
    await mockRequest('POST', '/issues/101/status', {}, { status: 'in_progress' })
    await click('Меня это тоже касается')
    await waitFor(() => getByText('Голос не сохранился'))
    expect(getByText('Голосование уже закончилось')).toBeTruthy()
    expect(document.querySelector('[aria-label="Голосов: 4 из 6"]')).not.toBeNull()
  })

  it('«Позвать соседей» отправляет в MAX ссылку на заявку', async () => {
    const { max } = await renderRoute('/issues/102')
    await waitFor(() => getButton('Позвать соседей'))
    await click('Позвать соседей')
    expect(max.shareMaxContent).toHaveBeenCalledWith(
      expect.stringContaining(
        'Соседи, поддержите заявку «Не горит свет в подъезде 3»: нужно ещё 4 голоса',
      ),
      'https://max.ru/domovoy_kuzya_bot?startapp=issue_102',
    )
  })

  it('в обычном браузере приглашение копируется в буфер', async () => {
    const writeText = stubClipboard()
    await renderRoute('/issues/102', { scenario: { inMax: false } })
    await waitFor(() => getButton('Позвать соседей'))
    await click('Позвать соседей')
    await waitFor(() => getByText('Приглашение скопировано'))
    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining('https://max.ru/domovoy_kuzya_bot?startapp=issue_102'),
    )
  })

  it('если поделиться не вышло, говорит об этом', async () => {
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: vi.fn().mockRejectedValue(new DOMException('отмена', 'AbortError')),
    })
    await renderRoute('/issues/102', { scenario: { inMax: false } })
    await waitFor(() => getButton('Позвать соседей'))
    await click('Позвать соседей')
    await waitFor(() => getByText('Не получилось поделиться'))
  })
})

describe('Карточка заявки: сроки и жалоба', () => {
  it('у отправленной заявки идёт обратный отсчёт срока', async () => {
    await renderRoute('/issues/103')
    await waitFor(() => getByText('Не работает лифт в подъезде 1'))
    const timer = document.querySelector('[role="timer"]')
    expect(timer?.textContent).toContain('Осталось')
    expect(timer?.textContent).toContain('18 ч')
    expect(timer?.classList.contains('sla--urgent')).toBe(false)
    expect(getByText(/Если не успеют, Кузя подготовит жалобу/)).toBeTruthy()
    expect(getByText(/По закону должны устранить за/)).toBeTruthy()
  })

  it('когда до срока меньше трёх часов, таймер выделен как срочный', async () => {
    await renderRoute('/issues/104')
    await waitFor(() => getByText('Нет горячей воды'))
    const timer = document.querySelector('[role="timer"]')
    expect(timer?.textContent).toContain('2 ч')
    expect(timer?.classList.contains('sla--urgent')).toBe(true)
    expect(getByText('Чинят')).toBeTruthy()
    expect(
      getByText('Управляющая компания: бригада на месте, меняют задвижку в подвале'),
    ).toBeTruthy()
  })

  it('таймер тикает сам, пока карточка открыта', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(NOW)
    await renderRoute('/issues/103')
    await waitFor(() => document.querySelector('[role="timer"]'))
    expect(document.querySelector('[role="timer"]')?.textContent).toContain('18 ч')
    vi.advanceTimersByTime(30 * 60_000)
    await waitFor(() =>
      document.querySelector('[role="timer"]')?.textContent?.includes('17 ч 30 мин'),
    )
  })

  it('когда срок истёк, а сервер ещё не отметил просрочку, показывает «Срок вышел»', async () => {
    vi.setSystemTime(NOW.getTime() + 19 * HOUR)
    await renderRoute('/issues/103')
    await waitFor(() => getByText('Срок вышел'))
    expect(getByText('просрочено на 1 ч')).toBeTruthy()
    expect(getByText('Просрочено')).toBeTruthy()
    expect(document.querySelector('[role="timer"]')).toBeNull()
  })

  it('просроченная заявка ведёт к готовой жалобе, которую можно переслать', async () => {
    const { max } = await renderRoute('/issues/105')
    await waitFor(() => getByText('Срок вышел'))
    expect(getByText('просрочено на 20 ч')).toBeTruthy()
    await click('Посмотреть жалобу')
    await waitFor(() => getByText('Жалоба в Госжилинспекцию'))
    const complaint = document.querySelector('[aria-label="Текст жалобы"]')
    expect(complaint?.textContent).toContain('ЖАЛОБА')
    expect(complaint?.textContent).toContain('пр-т Ленинского Комсомола, 5')
    expect(complaint?.textContent).toContain(
      'оператору вывоза мусора «Гринта»: «Переполнены мусорные баки»',
    )
    expect(complaint?.textContent).toContain('Обращение поддержали 6 жителей')

    await click('Поделиться жалобой')
    expect(max.shareMaxContent).toHaveBeenCalledWith(
      expect.stringContaining('В Государственную жилищную инспекцию'),
      undefined,
    )
  })

  it('текст жалобы можно скопировать', async () => {
    const writeText = stubClipboard()
    await renderRoute('/issues/105')
    await waitFor(() => getByText('Срок вышел'))
    await click('Посмотреть жалобу')
    await waitFor(() => getButton('Скопировать текст'))
    await click('Скопировать текст')
    await waitFor(() => getByText('Текст скопирован'))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('ЖАЛОБА'))
  })

  it('если скопировать не вышло, предупреждает', async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error('нет доступа')))
    Object.defineProperty(document, 'execCommand', { configurable: true, value: () => false })
    await renderRoute('/issues/105')
    await waitFor(() => getByText('Срок вышел'))
    await click('Посмотреть жалобу')
    await waitFor(() => getButton('Скопировать текст'))
    await click('Скопировать текст')
    await waitFor(() => getByText('Не удалось скопировать текст'))
    Reflect.deleteProperty(document, 'execCommand')
  })
})

describe('Карточка заявки: текст обращения', () => {
  it('показывает, что отправил Кузя, и честно пишет про тестовый режим', async () => {
    const { max } = await renderRoute('/issues/103')
    await waitFor(() => getByText('Что отправил Кузя'))
    await click(getByText('Что отправил Кузя').closest('button')!)
    await waitFor(() => getByText('Тестовый режим.'))
    expect(getByText(/Текст обращения сохранён здесь/)).toBeTruthy()
    expect(getByText(/ОБРАЩЕНИЕ/)).toBeTruthy()
    await click('Поделиться')
    expect(max.shareMaxContent).toHaveBeenCalledWith(
      expect.stringContaining('ОБРАЩЕНИЕ'),
      undefined,
    )
  })

  it('в браузере без «Поделиться» текст обращения копируется', async () => {
    const writeText = stubClipboard()
    await renderRoute('/issues/103', { scenario: { inMax: false } })
    await waitFor(() => getByText('Что отправил Кузя'))
    await click(getByText('Что отправил Кузя').closest('button')!)
    await waitFor(() => getButton('Поделиться'))
    await click('Поделиться')
    await waitFor(() => getByText('Текст скопирован, его можно вставить в чат'))
    await click('Скопировать')
    await waitFor(() => writeText.mock.calls.length === 2)
  })
})

describe('Карточка заявки: смена статуса', () => {
  it('житель не меняет статус чужой заявки', async () => {
    await renderRoute('/issues/103')
    await waitFor(() => getByText('Не работает лифт в подъезде 1'))
    expect(queryByText('Что с заявкой сейчас?')).toBeNull()
  })

  it('автор видит управление статусом своей заявки', async () => {
    await renderRoute('/issues/105')
    await waitFor(() => getByText('Что с заявкой сейчас?'))
    expect(getButton('Начали чинить')).toBeTruthy()
  })

  it('администратор отмечает, что начали чинить, с комментарием', async () => {
    await renderRoute('/issues/101', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Что с заявкой сейчас?'))
    expect(getButton('Всё исправили')).toBeTruthy()
    expect(getButton('Отклонить')).toBeTruthy()
    await click('Начали чинить')
    await waitFor(() => getField('Комментарий'))
    await type('Комментарий', 'Мастер придёт завтра')
    await click('Сохранить')
    await waitFor(() => getByText('Статус обновлён'))
    await waitFor(() => getByText('Мастер придёт завтра'))
    expect(getByText('Чинят')).toBeTruthy()
    // из «Чинят» можно только закончить или отклонить
    expect(queryButton('Начали чинить')).toBeNull()
    expect(getButton('Всё исправили')).toBeTruthy()
  })

  it('после «Всё исправили» управление пропадает', async () => {
    await renderRoute('/issues/104', { scenario: { role: 'admin' } })
    await waitFor(() => getButton('Всё исправили'))
    await click('Всё исправили')
    await waitFor(() => getButton('Сохранить'))
    await click('Сохранить')
    await waitFor(() => getByText('Статус обновлён'))
    await waitFor(() => queryByText('Что с заявкой сейчас?') === null)
    expect(getByText('Решено')).toBeTruthy()
  })
})

describe('Карточка заявки: загрузка и ошибки', () => {
  it('пока заявка грузится, показывает заглушку', async () => {
    // ответ сервера задерживаем, пока не посмотрим на экран загрузки
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const original = issuesApi.get
    vi.spyOn(issuesApi, 'get').mockImplementation(async (id) => {
      await gate
      return original(id)
    })
    await renderRoute('/issues/101')
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    release()
    await waitFor(() => getByText('Течёт крыша над 9 этажом'))
    expect(document.querySelector('[aria-busy="true"]')).toBeNull()
  })

  it('несуществующая заявка: «Заявка не найдена»', async () => {
    await renderRoute('/issues/999')
    await waitFor(() => getByText('Заявка не найдена'))
    expect(getByText('Не нашли: возможно, запись уже удалили')).toBeTruthy()
  })

  it('ошибка сервера: текст ошибки и повтор', async () => {
    await renderRoute('/issues/101', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    await click('Попробовать ещё раз')
    await waitFor(() => getByText('Не получилось загрузить'))
  })
})
