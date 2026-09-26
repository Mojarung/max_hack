import { getInitData, isInMax } from '@/max/bridge'
import { MOCK_API } from './mode'

export const API_BASE = '/api/v1'

/** Кто мы для сервера: подпись MAX или демо-житель. */
const auth = {
  devUser: null as number | null,
  houseId: null as number | null,
}

export function setDevUser(id: number | null): void {
  auth.devUser = id
}

export function setHouseId(id: number | null): void {
  auth.houseId = id
}

export function getDevUser(): number | null {
  return auth.devUser
}

export function getHouseId(): number | null {
  return auth.houseId
}

export type ApiErrorKind = 'network' | 'http' | 'timeout' | 'aborted'

export class ApiError extends Error {
  readonly status: number
  readonly kind: ApiErrorKind
  readonly detail: string

  constructor(kind: ApiErrorKind, status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
  }

  get isValidation(): boolean {
    return this.status === 422
  }

  get isAuth(): boolean {
    return this.status === 401 || this.status === 403
  }
}

const STATUS_TEXT: Record<number, string> = {
  400: 'Запрос не получился. Проверьте данные',
  401: 'Не удалось вас узнать. Откройте приложение из MAX заново',
  403: 'Недостаточно прав для этого действия',
  404: 'Не нашли: возможно, запись уже удалили',
  409: 'Это уже сделано',
  413: 'Файл слишком большой',
  422: 'Проверьте введённые данные',
  429: 'Слишком часто. Подождите немного',
  500: 'Кузя споткнулся на сервере. Попробуйте ещё раз',
  502: 'Сервер недоступен. Попробуйте через минуту',
  503: 'Сервер недоступен. Попробуйте через минуту',
}

/** Достаёт человекочитаемый текст из `{"detail": ...}` (строка или список ошибок FastAPI). */
export function extractDetail(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown }
      if (typeof first?.msg === 'string') return first.msg
    }
  }
  return STATUS_TEXT[status] ?? `Ошибка ${status}`
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error && error.message) return error.message
  return 'Что-то пошло не так'
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  if (isInMax()) {
    headers['X-Max-Init-Data'] = getInitData()
  } else if (auth.devUser !== null) {
    headers['X-Dev-User'] = String(auth.devUser)
  }
  if (auth.houseId !== null) headers['X-House-Id'] = String(auth.houseId)
  return headers
}

/** Query-параметры авторизации для EventSource, который не умеет заголовки. */
export function authQuery(): URLSearchParams {
  const params = new URLSearchParams()
  if (auth.houseId !== null) params.set('house_id', String(auth.houseId))
  if (isInMax()) params.set('init_data', getInitData())
  else if (auth.devUser !== null) params.set('dev_user', String(auth.devUser))
  return params
}

type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  query?: Record<string, QueryValue>
  body?: unknown
  signal?: AbortSignal
  timeoutMs?: number
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const qs = params.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

const DEFAULT_TIMEOUT = 20_000

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, signal, timeoutMs = DEFAULT_TIMEOUT } = options
  if (MOCK_API) {
    const { mockRequest } = await import('@/mock/server')
    return mockRequest<T>(method, path, query, body as Record<string, unknown> | undefined)
  }
  const headers: Record<string, string> = { Accept: 'application/json', ...authHeaders() }
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort('timeout'), timeoutMs)
  const onAbort = () => controller.abort('aborted')
  signal?.addEventListener('abort', onAbort, { once: true })

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: payload,
      signal: controller.signal,
    })
  } catch {
    if (controller.signal.aborted) {
      const reason = controller.signal.reason === 'timeout' ? 'timeout' : 'aborted'
      throw new ApiError(
        reason,
        0,
        reason === 'timeout' ? 'Сервер долго не отвечает. Попробуйте ещё раз' : 'Запрос отменён',
      )
    }
    throw new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }

  if (response.status === 204) return undefined as T
  const text = await response.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (!response.ok)
    throw new ApiError('http', response.status, extractDetail(data, response.status))
  return data as T
}

/**
 * Отправка multipart с прогрессом загрузки (fetch не умеет upload progress).
 * `onProgress` получает долю 0..1.
 */
export function upload<T>(
  path: string,
  form: FormData,
  onProgress?: (fraction: number) => void,
): Promise<T> {
  if (MOCK_API) return import('@/mock/server').then((m) => m.mockUpload<T>(path, form, onProgress))
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', buildUrl(path))
    xhr.timeout = 120_000
    xhr.setRequestHeader('Accept', 'application/json')
    for (const [key, value] of Object.entries(authHeaders())) xhr.setRequestHeader(key, value)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => {
      let data: unknown = null
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        data = null
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T)
      else reject(new ApiError('http', xhr.status, extractDetail(data, xhr.status)))
    }
    xhr.onerror = () =>
      reject(new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет'))
    xhr.ontimeout = () =>
      reject(new ApiError('timeout', 0, 'Загрузка заняла слишком много времени'))
    xhr.send(form)
  })
}
