import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import {
  api,
  ApiError,
  authHeaders,
  authQuery,
  buildUrl,
  errorMessage,
  extractDetail,
  setDevUser,
  setHouseId,
  upload,
} from './client'

vi.mock('./mode', () => ({
  MOCK_API: false,
  BROWSER_DEMO: false,
  startBrowserDemo: vi.fn(),
  stopBrowserDemo: vi.fn(),
}))

let fetchMock: Mock

function reply(status: number, body?: unknown): Response {
  const text = body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body)
  return new Response(status === 204 ? null : text, { status })
}

function lastInit(): RequestInit {
  return fetchMock.mock.calls.at(-1)![1] as RequestInit
}

beforeEach(() => {
  fetchMock = vi.fn(async () => reply(200, { ok: true }))
  vi.stubGlobal('fetch', fetchMock)
  setDevUser(null)
  setHouseId(null)
})

afterEach(() => {
  vi.useRealTimers()
  delete window.WebApp
})

describe('адрес запроса', () => {
  it('пропускает пустые параметры', () => {
    expect(
      buildUrl('/issues', { status: 'voting', q: '', page: 2, free: null, x: undefined }),
    ).toBe('/api/v1/issues?status=voting&page=2')
    expect(buildUrl('/me')).toBe('/api/v1/me')
  })
})

describe('кто мы для сервера', () => {
  it('внутри MAX отправляет подпись MAX и выбранный дом', async () => {
    window.WebApp = { initData: 'signed' }
    setDevUser(1002)
    setHouseId(5)
    await api('/me')
    expect(lastInit().headers).toMatchObject({
      Accept: 'application/json',
      'X-Max-Init-Data': 'signed',
      'X-House-Id': '5',
    })
    expect(lastInit().headers).not.toHaveProperty('X-Dev-User')
  })

  it('в демо отправляет демо-жителя', () => {
    setDevUser(1002)
    expect(authHeaders()).toEqual({ 'X-Dev-User': '1002' })
    expect(authQuery().toString()).toBe('dev_user=1002')
  })

  it('без жителя и дома заголовков авторизации нет', () => {
    expect(authHeaders()).toEqual({})
    expect(authQuery().toString()).toBe('')
  })

  it('для потока событий кладёт подпись MAX в адрес', () => {
    window.WebApp = { initData: 'signed' }
    setHouseId(3)
    expect(authQuery().toString()).toBe('house_id=3&init_data=signed')
  })
})

describe('тело запроса и ответ', () => {
  it('JSON уходит с Content-Type, ответ разбирается', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { id: 7, title: 'Течёт крыша' }))
    const data = await api<{ id: number }>('/issues', { method: 'POST', body: { title: 'x' } })
    expect(data).toEqual({ id: 7, title: 'Течёт крыша' })
    expect(lastInit().method).toBe('POST')
    expect(lastInit().body).toBe('{"title":"x"}')
    expect(lastInit().headers).toMatchObject({ 'Content-Type': 'application/json' })
  })

  it('FormData уходит как есть, без Content-Type', async () => {
    const form = new FormData()
    form.append('title', 'Лифт')
    await api('/issues', { method: 'POST', body: form })
    expect(lastInit().body).toBe(form)
    expect(lastInit().headers).not.toHaveProperty('Content-Type')
  })

  it('204 и пустой ответ дают undefined и null', async () => {
    fetchMock.mockResolvedValueOnce(reply(204))
    await expect(api('/announcements/1', { method: 'DELETE' })).resolves.toBeUndefined()
    fetchMock.mockResolvedValueOnce(reply(200, ''))
    await expect(api('/x')).resolves.toBeNull()
    fetchMock.mockResolvedValueOnce(reply(200, 'не json'))
    await expect(api('/x')).resolves.toBeNull()
  })
})

describe('ошибки сервера', () => {
  it('берёт текст ошибки из detail', async () => {
    fetchMock.mockResolvedValueOnce(reply(409, { detail: 'Вы уже голосовали' }))
    const error = await api('/issues/1/vote').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ kind: 'http', status: 409, detail: 'Вы уже голосовали' })
  })

  it('берёт первое сообщение из списка ошибок проверки', async () => {
    fetchMock.mockResolvedValueOnce(reply(422, { detail: [{ msg: 'Слишком короткий текст' }] }))
    const error = (await api('/issues').catch((e: unknown) => e)) as ApiError
    expect(error.detail).toBe('Слишком короткий текст')
    expect(error.isValidation).toBe(true)
    expect(error.isAuth).toBe(false)
  })

  it('без detail говорит по-человечески по коду ответа', async () => {
    fetchMock.mockResolvedValueOnce(reply(403, 'Forbidden'))
    const error = (await api('/house').catch((e: unknown) => e)) as ApiError
    expect(error.detail).toBe('Недостаточно прав для этого действия')
    expect(error.isAuth).toBe(true)
  })

  it('неизвестный код ответа показывает номер ошибки', () => {
    expect(extractDetail(null, 418)).toBe('Ошибка 418')
    expect(extractDetail({ detail: '  ' }, 500)).toBe(
      'Кузя споткнулся на сервере. Попробуйте ещё раз',
    )
    expect(extractDetail({ detail: [{ loc: ['body'] }] }, 422)).toBe('Проверьте введённые данные')
    expect(extractDetail({ detail: [] }, 401)).toBe(
      'Не удалось вас узнать. Откройте приложение из MAX заново',
    )
  })

  it('без сети сообщает про интернет', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api('/me')).rejects.toMatchObject({
      kind: 'network',
      status: 0,
      detail: 'Нет связи с сервером. Проверьте интернет',
    })
  })

  it('долгий ответ прерывается по таймауту', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new DOMException('aborted')))
        }),
    )
    const pending = api('/house/sync', { timeoutMs: 1000 }).catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(1000)
    expect(await pending).toMatchObject({
      kind: 'timeout',
      detail: 'Сервер долго не отвечает. Попробуйте ещё раз',
    })
  })

  it('отмена со стороны экрана даёт ошибку «отменён»', async () => {
    fetchMock.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new DOMException('aborted')))
        }),
    )
    const controller = new AbortController()
    const pending = api('/search', { signal: controller.signal }).catch((e: unknown) => e)
    controller.abort()
    expect(await pending).toMatchObject({ kind: 'aborted', detail: 'Запрос отменён' })
  })

  it('уже отменённый запрос сразу даёт «отменён», а не ждёт таймаута', async () => {
    fetchMock.mockImplementationOnce((_url: string, init: RequestInit) =>
      init.signal?.aborted
        ? Promise.reject(new DOMException('aborted'))
        : new Promise(() => undefined),
    )
    const controller = new AbortController()
    controller.abort()
    await expect(api('/search', { signal: controller.signal })).rejects.toMatchObject({
      kind: 'aborted',
      detail: 'Запрос отменён',
    })
  })
})

describe('errorMessage', () => {
  it('достаёт текст из любой ошибки', () => {
    expect(errorMessage(new ApiError('http', 404, 'Не нашли'))).toBe('Не нашли')
    expect(errorMessage(new Error('Сломалось'))).toBe('Сломалось')
    expect(errorMessage(new Error(''))).toBe('Что-то пошло не так')
    expect(errorMessage('строка')).toBe('Что-то пошло не так')
  })
})

/** XMLHttpRequest, которым тест управляет вручную. */
class FakeXhr {
  static last: FakeXhr | null = null
  method = ''
  url = ''
  timeout = 0
  status = 0
  responseText = ''
  headers: Record<string, string> = {}
  sent: unknown = null
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  ontimeout: (() => void) | null = null

  constructor() {
    FakeXhr.last = this
  }
  open(method: string, url: string): void {
    this.method = method
    this.url = url
  }
  setRequestHeader(key: string, value: string): void {
    this.headers[key] = value
  }
  send(body: unknown): void {
    this.sent = body
  }
  progress(loaded: number, total: number, lengthComputable = true): void {
    this.upload.onprogress?.({ loaded, total, lengthComputable } as ProgressEvent)
  }
  respond(status: number, text: string): void {
    this.status = status
    this.responseText = text
    this.onload?.()
  }
}

describe('загрузка файлов', () => {
  beforeEach(() => {
    FakeXhr.last = null
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
  })

  it('отправляет форму с подписью и показывает прогресс', async () => {
    window.WebApp = { initData: 'signed' }
    setHouseId(2)
    const progress = vi.fn()
    const form = new FormData()
    const pending = upload<{ id: number }>('/issues', form, progress)
    const xhr = FakeXhr.last!
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/v1/issues')
    expect(xhr.headers).toMatchObject({ 'X-Max-Init-Data': 'signed', 'X-House-Id': '2' })
    expect(xhr.sent).toBe(form)
    xhr.progress(50, 100)
    xhr.progress(10, 0, false)
    expect(progress).toHaveBeenCalledTimes(1)
    expect(progress).toHaveBeenCalledWith(0.5)
    xhr.respond(201, '{"id": 12}')
    await expect(pending).resolves.toEqual({ id: 12 })
  })

  it('ошибка сервера с понятным текстом', async () => {
    const pending = upload('/documents', new FormData())
    FakeXhr.last!.respond(413, '')
    await expect(pending).rejects.toMatchObject({ status: 413, detail: 'Файл слишком большой' })
  })

  it('битый ответ сервера не роняет загрузку', async () => {
    const pending = upload('/documents', new FormData())
    FakeXhr.last!.respond(200, '<html>')
    await expect(pending).resolves.toBeNull()
  })

  it('обрыв связи и слишком долгая загрузка', async () => {
    const offline = upload('/issues', new FormData())
    FakeXhr.last!.onerror?.()
    await expect(offline).rejects.toMatchObject({ kind: 'network' })

    const slow = upload('/issues', new FormData())
    FakeXhr.last!.ontimeout?.()
    await expect(slow).rejects.toMatchObject({
      kind: 'timeout',
      detail: 'Загрузка заняла слишком много времени',
    })
  })
})
