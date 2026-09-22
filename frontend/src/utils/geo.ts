export interface Position {
  lat: number
  lon: number
  /** gps - реальная геопозиция, house - координаты дома как запасной вариант. */
  source: 'gps' | 'house'
}

/** Геопозиция с таймаутом; при отказе или ошибке возвращает координаты дома. */
export function locate(
  fallback: { lat: number; lon: number },
  timeoutMs = 8000,
): Promise<Position> {
  const fromHouse: Position = { lat: fallback.lat, lon: fallback.lon, source: 'house' }
  if (typeof navigator === 'undefined' || !navigator.geolocation) return Promise.resolve(fromHouse)
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(fromHouse), timeoutMs + 500)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(timer)
        resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude, source: 'gps' })
      },
      () => {
        clearTimeout(timer)
        resolve(fromHouse)
      },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60_000 },
    )
  })
}
