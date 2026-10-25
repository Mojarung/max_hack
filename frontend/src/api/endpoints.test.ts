import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import {
  achievementsApi,
  announcementsApi,
  devChatApi,
  documentsApi,
  eventsApi,
  houseApi,
  issuesApi,
  listingsApi,
  mcpApi,
  meApi,
  normalizeCategories,
  peopleApi,
  safetyApi,
  searchApi,
} from './endpoints'
import { MCP_NAME_RE } from './types'

vi.mock('./mode', () => ({
  MOCK_API: false,
  BROWSER_DEMO: false,
  startBrowserDemo: vi.fn(),
  stopBrowserDemo: vi.fn(),
}))

const FALLBACK = { kids: 'Детское', tools: 'Инструменты' }

describe('normalizeCategories', () => {
  it('список кодов получает названия из контракта', () => {
    expect(normalizeCategories(['kids', 'books'], FALLBACK)).toEqual([
      { code: 'kids', title: 'Детское' },
      { code: 'books', title: 'books' },
    ])
  })

  it('понимает объекты с разными именами полей и пропускает мусор', () => {
    expect(
      normalizeCategories(
        [
          { code: 'kids', title: 'Детям' },
          { id: 'tools', name: 'Инструмент' },
          { value: 'food' },
          { category: 'plants', label: 'Цветы' },
          { title: 'без кода' },
          42,
          null,
        ],
        FALLBACK,
      ),
    ).toEqual([
      { code: 'kids', title: 'Детям' },
      { code: 'tools', title: 'Инструмент' },
      { code: 'food', title: 'food' },
      { code: 'plants', title: 'Цветы' },
    ])
  })

  it('словарь «код: название» и словарь без названий', () => {
    expect(normalizeCategories({ kids: 'Для детей', tools: 1 }, FALLBACK)).toEqual([
      { code: 'kids', title: 'Для детей' },
      { code: 'tools', title: 'Инструменты' },
    ])
  })

  it('без ответа сервера берёт категории из контракта', () => {
    expect(normalizeCategories(null, FALLBACK)).toEqual([
      { code: 'kids', title: 'Детское' },
      { code: 'tools', title: 'Инструменты' },
    ])
  })
})

describe('запросы к серверу', () => {
  let fetchMock: Mock

  beforeEach(() => {
    fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
  })

  const last = () => {
    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit]
    return { url, method: init.method, body: init.body }
  }

  it('фильтры вещей: «даром» и «мои» уходят параметрами, «открытые» - нет', async () => {
    await listingsApi.list({ q: 'коляска', free: true, scope: 'mine', category: 'kids' })
    expect(last().url).toBe(
      '/api/v1/listings?q=%D0%BA%D0%BE%D0%BB%D1%8F%D1%81%D0%BA%D0%B0&category=kids&free=true&scope=mine',
    )
    await listingsApi.list({ scope: 'active', free: false })
    expect(last().url).toBe('/api/v1/listings')
  })

  it('обновление списка домов просит сервер поискать чаты', async () => {
    await houseApi.list(true)
    expect(last().url).toBe('/api/v1/houses?refresh=true')
    await houseApi.list()
    expect(last().url).toBe('/api/v1/houses')
  })

  it('выбор аватарки и сообщение соседу', async () => {
    await meApi.setAvatar(3)
    expect(last()).toMatchObject({ url: '/api/v1/me/avatar', method: 'PUT', body: '{"preset":3}' })
    await peopleApi.message(2, 'Здравствуйте')
    expect(last()).toMatchObject({ url: '/api/v1/people/2/message', method: 'POST' })
  })

  it('фото события уходят формой, фото по номеру удаляется', async () => {
    const xhrSend = vi.fn()
    class Xhr {
      upload = {}
      timeout = 0
      open = vi.fn()
      setRequestHeader = vi.fn()
      send = xhrSend
    }
    vi.stubGlobal('XMLHttpRequest', Xhr)
    const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' })
    void eventsApi.addPhotos(301, [file, file])
    const form = xhrSend.mock.calls[0]![0] as FormData
    expect(form.getAll('photos')).toHaveLength(2)

    await eventsApi.removePhoto(301, 1)
    expect(last()).toMatchObject({ url: '/api/v1/events/301/photos/1', method: 'DELETE' })
  })

  it.each([
    ['дом: настройки', () => houseApi.update({ title: 'Дом' }), 'PATCH', '/api/v1/house'],
    ['дом: участники чата', () => houseApi.sync(), 'POST', '/api/v1/house/sync'],
    [
      'дом: поиск адреса',
      () => houseApi.geocode('Гончарова 1'),
      'GET',
      '/api/v1/house/geocode?q=%D0%93%D0%BE%D0%BD%D1%87%D0%B0%D1%80%D0%BE%D0%B2%D0%B0+1',
    ],
    ['объявления', () => announcementsApi.list(), 'GET', '/api/v1/announcements'],
    [
      'новое объявление',
      () => announcementsApi.create({ title: 'a', text: '', pin: false }),
      'POST',
      '/api/v1/announcements',
    ],
    [
      'закрепить объявление',
      () => announcementsApi.pin(9, true),
      'PATCH',
      '/api/v1/announcements/9',
    ],
    ['удалить объявление', () => announcementsApi.remove(9), 'DELETE', '/api/v1/announcements/9'],
    ['документы дома', () => documentsApi.list('house'), 'GET', '/api/v1/documents?scope=house'],
    ['ссылка на документ', () => documentsApi.link(4), 'GET', '/api/v1/documents/4/link'],
    ['удалить документ', () => documentsApi.remove(4), 'DELETE', '/api/v1/documents/4'],
    ['соседи', () => peopleApi.list(), 'GET', '/api/v1/people'],
    ['профиль соседа', () => peopleApi.profile(2), 'GET', '/api/v1/people/2'],
    ['спасибо соседу', () => peopleApi.thank(2), 'POST', '/api/v1/people/2/thanks'],
    ['похожие заявки', () => issuesApi.similar('лифт'), 'POST', '/api/v1/issues/similar'],
    ['категория заявки', () => issuesApi.classify('лифт'), 'POST', '/api/v1/issues/classify'],
    ['вещь', () => listingsApi.get(3), 'GET', '/api/v1/listings/3'],
    [
      'написать продавцу',
      () => listingsApi.contact(3, 'Добрый день'),
      'POST',
      '/api/v1/listings/3/contact',
    ],
    ['награды', () => achievementsApi.list(), 'GET', '/api/v1/achievements'],
    ['поиск', () => searchApi.search('лифт'), 'GET', '/api/v1/search?q=%D0%BB%D0%B8%D1%84%D1%82'],
    ['сообщение в чат', () => devChatApi.send(1, 1001, 'Привет'), 'POST', '/api/v1/dev/chat/send'],
    ['навыки Кузи', () => mcpApi.list(), 'GET', '/api/v1/mcp/servers'],
    [
      'новый навык',
      () => mcpApi.create({ name: 'gis', transport: 'sse', url: 'https://x', headers: {} }),
      'POST',
      '/api/v1/mcp/servers',
    ],
    ['инструменты навыка', () => mcpApi.tools(4), 'GET', '/api/v1/mcp/servers/4/tools'],
  ] as const)('адрес и метод запроса: %s', async (_name, call, method, url) => {
    await call()
    expect(last()).toMatchObject({ url, method })
  })

  it('загрузка фото и документов идёт формой на свой адрес', () => {
    const urls: string[] = []
    class Xhr {
      upload = {}
      timeout = 0
      open = (_method: string, url: string) => urls.push(url)
      setRequestHeader = vi.fn()
      send = vi.fn()
    }
    vi.stubGlobal('XMLHttpRequest', Xhr)
    const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' })
    void meApi.uploadAvatar(file)
    void documentsApi.upload(new FormData())
    void issuesApi.create(new FormData())
    void listingsApi.create(new FormData())
    expect(urls).toEqual([
      '/api/v1/me/avatar/photo',
      '/api/v1/documents',
      '/api/v1/issues',
      '/api/v1/listings',
    ])
  })

  it('тревога, маршрут до укрытия, чат и навыки', async () => {
    await safetyApi.route(1, 54.3, 48.6)
    expect(last().url).toBe('/api/v1/shelters/1/route?lat=54.3&lon=48.6')
    await safetyApi.startAlert('Учебная')
    expect(last()).toMatchObject({ method: 'POST', body: '{"kind":"drone","message":"Учебная"}' })
    await devChatApi.messages(1)
    expect(last().url).toBe('/api/v1/dev/chat/messages?chat_id=1')
    await devChatApi.callback(1, 1001, 'm1', 'vote:5')
    expect(JSON.parse(String(last().body))).toEqual({
      chat_id: 1,
      user_id: 1001,
      message_id: 'm1',
      payload: 'vote:5',
    })
    await mcpApi.remove(4)
    expect(last()).toMatchObject({ url: '/api/v1/mcp/servers/4', method: 'DELETE' })
  })
})

describe('имя навыка Кузи', () => {
  it('латиница в нижнем регистре, цифры и подчёркивание, начинается с буквы', () => {
    expect(MCP_NAME_RE.test('house_passport')).toBe(true)
    expect(MCP_NAME_RE.test('gis2')).toBe(true)
    expect(MCP_NAME_RE.test('2gis')).toBe(false)
    expect(MCP_NAME_RE.test('Гис')).toBe(false)
    expect(MCP_NAME_RE.test('a')).toBe(false)
  })
})
