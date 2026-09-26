import { defineStore } from 'pinia'
import { ref } from 'vue'
import { safetyApi } from '@/api/endpoints'
import type { AlertOut, ShelterOut } from '@/api/types'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { locate, type Position } from '@/utils/geo'
import { useSessionStore } from './session'

export const useAlertsStore = defineStore('alerts', () => {
  const active = ref<AlertOut | null>(null)
  const minimized = ref(false)
  const nearest = ref<ShelterOut | null>(null)
  const nearestLoading = ref(false)
  const position = ref<Position | null>(null)

  function activate(alert: AlertOut): void {
    const isNew = active.value?.id !== alert.id
    active.value = alert
    if (isNew) {
      minimized.value = false
      haptic.notify('warning')
      void findNearest()
    }
  }

  function clear(announce: boolean): void {
    if (!active.value) return
    active.value = null
    minimized.value = false
    if (announce) notify.success('Отбой тревоги', 'Опасность миновала. Можно возвращаться домой')
  }

  async function check(): Promise<void> {
    try {
      const alert = await safetyApi.activeAlert()
      if (alert && alert.active) activate(alert)
      else clear(false)
    } catch {
      // не мешаем запуску: SSE сообщит о тревоге
    }
  }

  async function findNearest(): Promise<void> {
    const house = useSessionStore().me?.house
    nearestLoading.value = true
    try {
      position.value = await locate(house ?? { lat: 54.3142, lon: 48.4031 })
      const list = await safetyApi.shelters(position.value.lat, position.value.lon)
      nearest.value = list[0] ?? null
    } catch {
      nearest.value = null
    } finally {
      nearestLoading.value = false
    }
  }

  async function startTest(): Promise<void> {
    const alert = await safetyApi.startAlert('Учебная тревога. Это проверка оповещения жителей.')
    activate(alert)
  }

  async function end(): Promise<void> {
    if (!active.value) return
    await safetyApi.endAlert(active.value.id)
    clear(true)
  }

  onRealtime('alert.started', (data) => {
    if (hasNumericId(data)) activate(data as AlertOut)
    else void check()
  })
  onRealtime('alert.ended', () => clear(true))
  onRealtime('resync', () => void check())

  return {
    active,
    minimized,
    nearest,
    nearestLoading,
    position,
    check,
    findNearest,
    startTest,
    end,
  }
})
