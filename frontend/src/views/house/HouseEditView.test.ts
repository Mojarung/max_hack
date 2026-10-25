import { DOMWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { houseApi } from '@/api/endpoints'
import { scenario } from '@/mock/scenario'
import { useSessionStore } from '@/stores/session'
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
import { renderRoute } from '@/test/harness'

const ADMIN = { scenario: { role: 'admin' as const } }

describe('Настройки дома: житель', () => {
  it('объясняет, что настройки меняет администратор, и ведёт в «О доме»', async () => {
    const { router } = await renderRoute('/more/house/edit')
    expect(getByText(/Настройки дома меняет администратор чата/)).toBeTruthy()
    await click('О доме')
    await waitFor(() => router.currentRoute.value.path === '/more/house')
  })
})

describe('Настройки дома: администратор', () => {
  it('заполняет форму текущими данными дома и считает порог голосов', async () => {
    await renderRoute('/more/house/edit', ADMIN)
    expect(getField('Название').value).toBe('Ленинского Комсомола, 5')
    expect(getField('Адрес').value).toBe('Ульяновск, пр-т Ленинского Комсомола, 5')
    expect(getField('Почта для обращений').value).toBe('uk@example.org')
    expect(getField('Телефон диспетчерской').value).toBe('+7 (8422) 00-00-01')
    expect(getByText('15%')).toBeTruthy()
    // 15% от 40 участников - 6 голосов
    expect(getByText('Сейчас это 6 голосов из 40 участников чата')).toBeTruthy()
    expect(getByText(/Дом отмечен на карте/)).toBeTruthy()
  })

  it('сохраняет изменения, сообщает об этом и возвращает на «О доме»', async () => {
    const { router } = await renderRoute('/more/house/edit', ADMIN)
    await type(getField('Название'), 'Дом на Комсомольском')
    await type(getField('Информация для жителей'), '  Председатель: Ильдар, кв. 45  ')
    await click('Сохранить')
    await waitFor(() => router.currentRoute.value.path === '/more/house')
    await waitFor(() => getByText('Дом сохранён'))
    const house = useSessionStore().me!.house
    expect(house.title).toBe('Дом на Комсомольском')
    // лишние пробелы по краям не сохраняются
    expect(house.info).toBe('Председатель: Ильдар, кв. 45')
    expect(house.setup_done).toBe(true)
  })

  it('пока форма заполнена, просит MAX подтвердить закрытие', async () => {
    const { max } = await renderRoute('/more/house/edit', ADMIN)
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(false)
    await type(getField('Телефон диспетчерской'), '+7 900 000-00-00')
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(true)
  })

  it('не даёт сохранить короткое название и неверную почту', async () => {
    await renderRoute('/more/house/edit', ADMIN)
    await type(getField('Название'), 'Д')
    await type(getField('Почта для обращений'), 'не почта')
    await waitFor(() => getByText('Хотя бы 3 символа'))
    expect(getByText('Проверьте адрес почты')).toBeTruthy()
    expect(getButton('Сохранить').hasAttribute('disabled')).toBe(true)
  })

  it('без улицы и номера дома нельзя искать адрес на карте', async () => {
    await renderRoute('/more/house/edit', ADMIN)
    await type(getField('Адрес'), 'Ул')
    await waitFor(() => getByText('Укажите улицу и номер дома'))
    expect(getButton('Найти дом на карте').hasAttribute('disabled')).toBe(true)
  })

  it('новый дом: находит адрес на карте и запоминает выбранные координаты', async () => {
    const { router } = await renderRoute('/more/house/edit', {
      scenario: { role: 'admin', setup: true },
    })
    expect(getByText(/Кузя подключился к чату дома/)).toBeTruthy()
    expect(getByText(/Нажмите «Найти дом на карте»/)).toBeTruthy()

    await type(getField('Адрес'), 'Ленина, 1')
    await click('Найти дом на карте')
    const found = await waitFor(() => getByText('Ленина, 1, Димитровград, Ульяновская область'))
    expect(getByText('Ленина, 1, Ульяновск, Ульяновская область')).toBeTruthy()

    await click(found.closest('.v-list-item')!)
    await waitFor(() => getByText('Координаты дома заданы'))
    expect(getByText(/Дом отмечен на карте/)).toBeTruthy()
    expect(queryByText('Ленина, 1, Ульяновск, Ульяновская область')).toBeNull()

    await click('Сохранить')
    await waitFor(() => router.currentRoute.value.path === '/more/house')
    const house = useSessionStore().me!.house
    expect(house.address).toBe('Ленина, 1')
    expect(house.lat).toBe(54.2138)
    expect(house.lon).toBe(49.6184)
  })

  it('если адрес не нашёлся, подсказывает уточнить город и улицу', async () => {
    await renderRoute('/more/house/edit', ADMIN)
    vi.spyOn(houseApi, 'geocode').mockResolvedValue([])
    await click('Найти дом на карте')
    await waitFor(() => getByText('Адрес не нашёлся'))
  })

  it('ошибку поиска адреса показывает тостом', async () => {
    await renderRoute('/more/house/edit', { scenario: { role: 'admin', name: 'error' } })
    await click('Найти дом на карте')
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
  })

  it('сервер отказал в правах: остаётся на форме и говорит, почему не сохранилось', async () => {
    const { router } = await renderRoute('/more/house/edit', ADMIN)
    // пока форма открыта, жителя лишили прав администратора
    scenario.role = 'resident'
    await type(getField('Название'), 'Новое название дома')
    await click('Сохранить')
    await waitFor(() => getByText('Не удалось сохранить'))
    expect(getByText('Настройки дома меняет администратор')).toBeTruthy()
    expect(router.currentRoute.value.path).toBe('/more/house/edit')
  })

  it('ползунок порога меняет подсказку о числе голосов', async () => {
    await renderRoute('/more/house/edit', ADMIN)
    const thumb = document.querySelector<HTMLElement>('[role="slider"]')!
    await new DOMWrapper(thumb).trigger('keydown', { key: 'ArrowRight' })
    await settle()
    expect(getByText('20%')).toBeTruthy()
    expect(getByText('Сейчас это 8 голосов из 40 участников чата')).toBeTruthy()
  })
})

describe('Настройки дома: чат дома', () => {
  /** Настоящий дом из чата (не демо): открываем настройки уже после загрузки сессии. */
  async function openRealHouse(botIsAdmin: boolean) {
    const rendered = await renderRoute('/more/house', ADMIN)
    const session = useSessionStore()
    session.me = {
      ...session.me!,
      house: { ...session.me!.house, is_demo: false, has_chat: true, bot_is_admin: botIsAdmin },
    }
    await rendered.router.push('/more/house/edit')
    await settle(5)
    return rendered
  }

  it('Кузя администратор чата: сверяет жителей и сообщает итог', async () => {
    await openRealHouse(true)
    expect(getByText(/Кузя - администратор чата: убирает спам и знает соседей/)).toBeTruthy()
    await click('Сверить жителей с чатом')
    await waitFor(() => getByText('Сверил 40 участников'))
    expect(getByText('Администраторы чата стали администраторами дома')).toBeTruthy()
  })

  it('Кузя не администратор: просит назначить его, а пустую сверку объясняет', async () => {
    await openRealHouse(false)
    expect(getByText(/Кузя не администратор чата/)).toBeTruthy()
    vi.spyOn(houseApi, 'sync').mockResolvedValue({ members: 0, bot_is_admin: false })
    await click('Сверить жителей с чатом')
    await waitFor(() => getByText('Список участников недоступен'))
    expect(getByText('Сделайте Кузю администратором чата')).toBeTruthy()
  })

  it('ошибку сверки показывает тостом', async () => {
    await openRealHouse(true)
    vi.spyOn(houseApi, 'sync').mockRejectedValue(new Error('Чат недоступен'))
    await click('Сверить жителей с чатом')
    await waitFor(() => getByText('Не удалось сверить с чатом'))
    expect(getByText('Чат недоступен')).toBeTruthy()
  })
})
