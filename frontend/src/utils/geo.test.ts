import { afterEach, describe, expect, it, vi } from 'vitest'
import { locate } from './geo'

const HOUSE = { lat: 54.3857, lon: 48.6072 }

function stubGeolocation(getCurrentPosition: Geolocation['getCurrentPosition']): void {
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition },
  })
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'geolocation')
  vi.useRealTimers()
})

describe('где находится житель', () => {
  it('без геолокации в браузере берёт координаты дома', async () => {
    await expect(locate(HOUSE)).resolves.toEqual({ ...HOUSE, source: 'house' })
  })

  it('берёт точку с GPS, если житель разрешил', async () => {
    const getCurrentPosition = vi.fn(
      (ok: PositionCallback, _fail?: PositionErrorCallback | null, _options?: PositionOptions) =>
        ok({ coords: { latitude: 54.31, longitude: 48.4 } } as GeolocationPosition),
    )
    stubGeolocation(getCurrentPosition)
    await expect(locate(HOUSE, 5000)).resolves.toEqual({ lat: 54.31, lon: 48.4, source: 'gps' })
    expect(getCurrentPosition.mock.calls[0]![2]).toMatchObject({
      enableHighAccuracy: true,
      timeout: 5000,
    })
  })

  it('при отказе в доступе берёт координаты дома', async () => {
    stubGeolocation((_ok, fail) => fail?.({ code: 1 } as GeolocationPositionError))
    await expect(locate(HOUSE)).resolves.toMatchObject({ source: 'house' })
  })

  it('если телефон долго молчит, не ждёт дольше таймаута', async () => {
    vi.useFakeTimers()
    stubGeolocation(() => undefined)
    const pending = locate(HOUSE, 1000)
    await vi.advanceTimersByTimeAsync(1500)
    await expect(pending).resolves.toEqual({ ...HOUSE, source: 'house' })
  })
})
