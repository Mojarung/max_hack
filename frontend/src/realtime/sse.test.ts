import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeEventSource } from '@/test/fakeEventSource'

vi.mock('@/api/mode', () => ({
  MOCK_API: false,
  BROWSER_DEMO: false,
  startBrowserDemo: vi.fn(),
  stopBrowserDemo: vi.fn(),
}))

type Sse = typeof import('./sse')
type Client = typeof import('@/api/client')

let sse: Sse
let client: Client

beforeEach(async () => {
  vi.resetModules()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  window.WebApp = { initData: 'signed-init', platform: 'ios' }
  sse = await import('./sse')
  client = await import('@/api/client')
})

afterEach(() => {
  sse.disconnectRealtime()
  vi.useRealTimers()
  delete window.WebApp
})

describe('подключение к потоку событий', () => {
  it('подписывается с подписью MAX и домом, показывает статус', () => {
    client.setHouseId(7)
    sse.connectRealtime()
    const es = FakeEventSource.last()
    expect(es.url).toBe('/api/v1/realtime/stream?house_id=7&init_data=signed-init')
    expect(sse.realtimeStatus.value).toBe('connecting')
    es.open()
    expect(sse.realtimeStatus.value).toBe('open')
  })

  it('вне MAX подписывается от имени демо-жителя', () => {
    window.WebApp = { initData: '' }
    client.setDevUser(1002)
    sse.connectRealtime()
    expect(FakeEventSource.last().url).toBe('/api/v1/realtime/stream?dev_user=1002')
  })

  it('без EventSource в браузере не подключается', () => {
    vi.stubGlobal('EventSource', undefined)
    sse.connectRealtime()
    expect(FakeEventSource.instances).toHaveLength(0)
    expect(sse.realtimeStatus.value).toBe('idle')
  })

  it('отключение закрывает поток', () => {
    sse.connectRealtime()
    const es = FakeEventSource.last()
    es.open()
    sse.disconnectRealtime()
    expect(es.readyState).toBe(FakeEventSource.CLOSED)
    expect(sse.realtimeStatus.value).toBe('idle')
  })
})

describe('доставка событий', () => {
  it('передаёт разобранный JSON подписчикам, а не JSON - строкой', () => {
    const handler = vi.fn()
    sse.onRealtime('issue.created', handler)
    sse.connectRealtime()
    const es = FakeEventSource.last()
    es.emit('issue.created', { id: 5, title: 'Течёт крыша' })
    es.emit('issue.created', 'не json')
    expect(handler).toHaveBeenNthCalledWith(1, { id: 5, title: 'Течёт крыша' })
    expect(handler).toHaveBeenNthCalledWith(2, 'не json')
  })

  it('отписка прекращает доставку', () => {
    const handler = vi.fn()
    const off = sse.onRealtime('pulse.changed', handler)
    off()
    sse.connectRealtime()
    FakeEventSource.last().emit('pulse.changed', { mood: 'ok' })
    expect(handler).not.toHaveBeenCalled()
  })

  it('ошибка одного подписчика не мешает другим', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const broken = vi.fn(() => {
      throw new Error('сломался')
    })
    const healthy = vi.fn()
    sse.onRealtime('alert.started', broken)
    sse.onRealtime('alert.started', healthy)
    sse.connectRealtime()
    FakeEventSource.last().emit('alert.started', { id: 1 })
    expect(healthy).toHaveBeenCalledWith({ id: 1 })
    expect(consoleError).toHaveBeenCalledWith('[realtime]', 'alert.started', expect.any(Error))
  })

  it('проверяет, что в событии сущность с числовым id', () => {
    expect(sse.hasNumericId({ id: 3 })).toBe(true)
    expect(sse.hasNumericId({ id: '3' })).toBe(false)
    expect(sse.hasNumericId(null)).toBe(false)
    expect(sse.hasNumericId('3')).toBe(false)
  })
})

describe('обрыв связи', () => {
  it('временная ошибка: статус «переподключение», браузер справится сам', () => {
    sse.connectRealtime()
    const es = FakeEventSource.last()
    es.open()
    es.fail(false)
    expect(sse.realtimeStatus.value).toBe('reconnecting')
    expect(FakeEventSource.instances).toHaveLength(1)
  })

  it('поток закрыт: переподключается с растущей паузой и просит добрать пропущенное', async () => {
    vi.useFakeTimers()
    const resync = vi.fn()
    sse.onRealtime('resync', resync)
    sse.connectRealtime()
    FakeEventSource.last().open()
    expect(resync).not.toHaveBeenCalled()

    FakeEventSource.last().fail()
    await vi.advanceTimersByTimeAsync(1999)
    expect(FakeEventSource.instances).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(sse.realtimeStatus.value).toBe('reconnecting')

    // второй обрыв подряд: пауза уже 4 секунды
    FakeEventSource.last().fail()
    await vi.advanceTimersByTimeAsync(3999)
    expect(FakeEventSource.instances).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(FakeEventSource.instances).toHaveLength(3)

    FakeEventSource.last().open()
    expect(resync).toHaveBeenCalledTimes(1)
    expect(sse.realtimeStatus.value).toBe('open')
  })

  it('повторный обрыв до переподключения не плодит таймеры', async () => {
    vi.useFakeTimers()
    sse.connectRealtime()
    const es = FakeEventSource.last()
    es.fail()
    es.fail()
    await vi.advanceTimersByTimeAsync(2000)
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('ошибка старого, уже заменённого потока игнорируется', () => {
    sse.connectRealtime()
    const old = FakeEventSource.last()
    sse.connectRealtime()
    FakeEventSource.last().open()
    old.fail()
    expect(sse.realtimeStatus.value).toBe('open')
  })

  it('отключение отменяет запланированное переподключение', async () => {
    vi.useFakeTimers()
    sse.connectRealtime()
    FakeEventSource.last().fail()
    sse.disconnectRealtime()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(FakeEventSource.instances).toHaveLength(1)
  })
})

describe('мок-режим', () => {
  it('в мок-режиме поток не нужен: статус сразу «на связи»', async () => {
    vi.resetModules()
    vi.doMock('@/api/mode', () => ({ MOCK_API: true, BROWSER_DEMO: false }))
    const mocked = await import('./sse')
    mocked.connectRealtime()
    expect(mocked.realtimeStatus.value).toBe('open')
    expect(FakeEventSource.instances).toHaveLength(0)
    vi.doUnmock('@/api/mode')
  })
})
