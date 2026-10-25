import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { safetyApi } from '@/api/endpoints'
import { useAlertsStore } from '@/stores/alerts'
import {
  click,
  getButton,
  getByText,
  queryAllButtons,
  queryButton,
  queryByText,
  textOf,
  waitFor,
} from '@/test/dom'
import { renderRoute, useScenario } from '@/test/harness'

// Настоящая карта (Leaflet) в jsdom не рисуется: вместо неё заглушка, которая показывает,
// что экран ей передал, и умеет «нажать на точку» на карте
const map = vi.hoisted(() => ({ focus: vi.fn() }))
vi.mock('@/components/safety/ShelterMap.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    // экран грузит карту через defineAsyncComponent: без флага он не возьмёт default
    __esModule: true,
    default: defineComponent({
      name: 'ShelterMapStub',
      props: {
        house: { type: Object, default: null },
        shelters: { type: Array, default: () => [] },
        me: { type: Object, default: null },
        selectedId: { type: Number, default: null },
        route: { type: Object, default: null },
      },
      emits: ['select'],
      setup(props, { emit, expose }) {
        expose({ focus: map.focus })
        return () =>
          h('div', { 'data-map': '' }, [
            h('p', `Точек на карте: ${props.shelters.length}`),
            h('p', `Выбрано на карте: ${props.selectedId ?? 'нет'}`),
            h('p', `Линия: ${props.route ? String(props.route.provider) : 'нет'}`),
            h('p', `Я на карте: ${props.me ? String(props.me.source) : 'нет'}`),
            ...(props.shelters as { id: number; name: string }[]).map((s) =>
              h('button', { type: 'button', onClick: () => emit('select', s.id) }, `Точка ${s.id}`),
            ),
          ])
      },
    }),
  }
})

const SCHOOL = 'Укрытие в подвале школы (демо)'
const CULTURE = 'Цокольный этаж Дома культуры (демо)'
const PARKING = 'Подземный паркинг'

/** Карточка укрытия по названию. */
function card(name: string): HTMLElement {
  const items = Array.from(document.querySelectorAll<HTMLElement>('li[id^="shelter-"]'))
  const found = items.find((li) => textOf(li.querySelector('.shelter-head .leading-snug')) === name)
  if (!found) throw new Error(`Нет карточки «${name}»`)
  return found
}

function mapText(): string {
  return textOf(document.querySelector('[data-map]'))
}

function stubGeolocation(result: { lat: number; lon: number } | 'denied'): void {
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: {
      getCurrentPosition: (ok: PositionCallback, fail: PositionErrorCallback) => {
        if (result === 'denied') fail({ code: 1, message: 'denied' } as GeolocationPositionError)
        else ok({ coords: { latitude: result.lat, longitude: result.lon } } as GeolocationPosition)
      },
    },
  })
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'geolocation')
})

describe('Безопасность: укрытия рядом', () => {
  it('показывает укрытия по порядку с расстоянием, источником и инструкцией', async () => {
    await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))

    const names = Array.from(document.querySelectorAll('.shelter-head .leading-snug')).map(textOf)
    expect(names).toEqual([SCHOOL, CULTURE, PARKING])
    expect(textOf(card(SCHOOL))).toContain('180 м')
    expect(textOf(card(SCHOOL))).toContain('Реестр')
    expect(textOf(card(SCHOOL))).toContain('до 300 человек')
    expect(textOf(card(CULTURE))).toContain('Демо-точка · подвал')
    // у объекта OSM без имени вид не повторяется второй раз, остаётся только адрес
    expect(textOf(card(PARKING))).toContain('OpenStreetMap · паркинг')
    expect(textOf(card(PARKING).querySelector('.text-muted'))).toBe('пр-т Ленинского Комсомола, 30')

    expect(getByText('Что делать при тревоге')).toBeTruthy()
    expect(getByText('Отойдите от окон и стеклянных дверей')).toBeTruthy()
    expect(mapText()).toContain('Точек на карте: 3')
    expect(mapText()).toContain('Выбрано на карте: нет')
  })

  it('«Маршрут на карте» строит путь пешком и показывает время', async () => {
    const { max } = await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))

    await click(getButton('Маршрут на карте', card(SCHOOL)))
    expect(max.impact).toHaveBeenCalledWith('light')
    await waitFor(() => mapText().includes('Линия: osrm'))

    const strip = document.querySelector('.route-strip')
    expect(textOf(strip)).toContain(SCHOOL)
    expect(textOf(strip)).toMatch(/≈ \d+ мин пешком · \d+ м/)
    expect(textOf(strip)).not.toContain('по прямой')
    expect(card(SCHOOL).querySelector('.shelter-head')?.getAttribute('aria-pressed')).toBe('true')
    expect(mapText()).toContain('Выбрано на карте: 1')
    expect(map.focus).toHaveBeenCalledWith(1)
  })

  it('до объекта OpenStreetMap маршрут только по прямой, о чём честно сказано', async () => {
    await renderRoute('/more/safety')
    await waitFor(() => getByText(PARKING))
    await click(getButton('Маршрут на карте', card(PARKING)))
    await waitFor(() => mapText().includes('Линия: straight'))
    expect(getByText(/по прямой, дорога может быть длиннее/)).toBeTruthy()
    expect(textOf(card(PARKING).querySelector('.route-info'))).toContain('· по прямой')
  })

  it('нажатие на карточку или точку на карте выбирает укрытие', async () => {
    const scrolled = vi.spyOn(Element.prototype, 'scrollIntoView')
    await renderRoute('/more/safety')
    await waitFor(() => getByText(CULTURE))

    await click(card(CULTURE).querySelector('.shelter-head')!)
    await waitFor(() => mapText().includes('Выбрано на карте: 2'))
    expect(scrolled).toHaveBeenCalled()

    await click('Точка 3')
    await waitFor(() => mapText().includes('Выбрано на карте: 3'))
    expect(card(PARKING).querySelector('.shelter-head')?.getAttribute('aria-pressed')).toBe('true')
    expect(card(CULTURE).querySelector('.shelter-head')?.getAttribute('aria-pressed')).toBe('false')
    expect(map.focus).toHaveBeenLastCalledWith(3)
  })

  it('из экрана тревоги с ?shelter= сразу выбирает укрытие и строит маршрут', async () => {
    await renderRoute('/more/safety?shelter=2')
    await waitFor(() => mapText().includes('Линия: osrm'))
    expect(mapText()).toContain('Выбрано на карте: 2')
    expect(textOf(document.querySelector('.route-strip'))).toContain(CULTURE)
  })

  it('если маршрут не построился, предлагает Яндекс Карты', async () => {
    vi.spyOn(safetyApi, 'route').mockRejectedValue(new ApiError('timeout', 0, 'долго'))
    await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))
    await click(getButton('Маршрут на карте', card(SCHOOL)))
    await waitFor(() => getByText('Маршрут не построился. Откройте его в Яндекс Картах.'))
    expect(mapText()).toContain('Линия: нет')
  })

  it('кнопка «В Яндекс Картах» открывает маршрут через MAX', async () => {
    const { max } = await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))
    await click(getButton('Открыть маршрут пешком в Яндекс Картах', card(SCHOOL)))
    expect(max.openLink).toHaveBeenCalledWith('https://yandex.ru/maps/?rtext=~54.3868,48.609')
    await waitFor(() => getByText('Открываю Яндекс Карты с маршрутом...'))
  })
})

describe('Безопасность: поиск ближайшего укрытия', () => {
  it('по геопозиции выбирает ближайшее и говорит, сколько до него идти', async () => {
    stubGeolocation({ lat: 54.386, lon: 48.608 })
    const { max } = await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))

    await click('Найти ближайшее укрытие')
    expect(max.impact).toHaveBeenCalledWith('medium')
    await waitFor(() => getByText('Ближайшее: 180 м'))
    expect(getByText('Расстояние посчитано от того места, где вы сейчас.')).toBeTruthy()
    expect(mapText()).toContain('Я на карте: gps')
    expect(mapText()).toContain('Выбрано на карте: 1')
  })

  it('без доступа к геопозиции считает от дома и предупреждает', async () => {
    stubGeolocation('denied')
    await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))

    await click('Найти ближайшее укрытие')
    await waitFor(() => getByText('Не удалось узнать, где вы'))
    expect(getByText('Не удалось узнать, где вы: считаем расстояние от дома.')).toBeTruthy()
    expect(mapText()).toContain('Я на карте: house')
  })

  it('когда укрытий нет, советует подвал и даёт проверить ещё раз', async () => {
    await renderRoute('/more/safety', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('Рядом не нашлось укрытий в реестре и на карте'))
    expect(getByText('При тревоге спуститесь в подвал или в помещение без окон.')).toBeTruthy()

    await click('Найти ближайшее укрытие')
    await waitFor(() => getByText('Укрытий рядом не нашлось'))

    // укрытия появились в реестре: повторная проверка их показывает
    useScenario({})
    await click('Проверить ещё раз')
    await waitFor(() => getByText(SCHOOL))
  })

  it('пока укрытия грузятся, на месте списка заготовки', async () => {
    // ответ сервера придержан, пока не проверим экран загрузки
    let release = () => undefined as void
    const gate = new Promise<void>((resolve) => (release = resolve))
    const original = safetyApi.shelters
    vi.spyOn(safetyApi, 'shelters').mockImplementation(async (lat, lon) => {
      await gate
      return original(lat, lon)
    })
    await renderRoute('/more/safety')
    expect(document.querySelector('[aria-label="Загрузка"]')).not.toBeNull()
    release()
    await waitFor(() => getByText(SCHOOL))
    expect(document.querySelector('[aria-label="Загрузка"]')).toBeNull()
  })

  it('при ошибке сервера показывает ошибку и даёт повторить', async () => {
    await renderRoute('/more/safety', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    useScenario({})
    await click('Попробовать ещё раз')
    await waitFor(() => getByText(SCHOOL))
  })
})

describe('Безопасность: тревога', () => {
  it('во время тревоги сверху красная плашка, «Открыть» возвращает экран тревоги', async () => {
    await renderRoute('/more/safety', { scenario: { name: 'alert' } })
    await waitFor(() => getByText('Беспилотная опасность'))
    expect(getByText('Идёт тревога. Следуйте инструкции и идите в укрытие.')).toBeTruthy()

    const alerts = useAlertsStore()
    alerts.minimized = true
    await click('Открыть')
    expect(alerts.minimized).toBe(false)
  })

  it('жителю в MAX учебная тревога недоступна', async () => {
    await renderRoute('/more/safety')
    await waitFor(() => getByText(SCHOOL))
    expect(queryByText('Проверка оповещения (демо)')).toBeNull()
    expect(queryButton('Тестовая тревога')).toBeNull()
  })

  it('администратор запускает учебную тревогу и даёт отбой', async () => {
    const { max } = await renderRoute('/more/safety', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Проверка оповещения (демо)'))
    expect(getButton('Отбой').hasAttribute('disabled')).toBe(true)

    await click('Тестовая тревога')
    await waitFor(() => getByText('Беспилотная опасность'))
    expect(max.notify).toHaveBeenCalledWith('warning')
    expect(getButton('Тестовая тревога').hasAttribute('disabled')).toBe(true)

    await click('Отбой')
    await waitFor(() => getByText('Отбой тревоги'))
    expect(getByText('Опасность миновала. Можно возвращаться домой')).toBeTruthy()
    await waitFor(() => !queryByText('Идёт тревога. Следуйте инструкции и идите в укрытие.'))
    expect(getButton('Тестовая тревога').hasAttribute('disabled')).toBe(false)
  })

  it('если тревога не запустилась или отбой не прошёл, говорит об этом', async () => {
    vi.spyOn(safetyApi, 'startAlert').mockRejectedValueOnce(
      new ApiError('http', 403, 'Недостаточно прав для этого действия'),
    )
    vi.spyOn(safetyApi, 'endAlert').mockRejectedValueOnce(
      new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет'),
    )
    await renderRoute('/more/safety', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Проверка оповещения (демо)'))

    await click('Тестовая тревога')
    await waitFor(() => getByText('Тревога не запустилась'))
    expect(getByText('Недостаточно прав для этого действия')).toBeTruthy()

    await click('Тестовая тревога')
    await waitFor(() => getByText('Беспилотная опасность'))
    await click('Отбой')
    await waitFor(() => getByText('Отбой не прошёл'))
    expect(queryAllButtons('Отбой').some((b) => !b.hasAttribute('disabled'))).toBe(true)
  })
})
