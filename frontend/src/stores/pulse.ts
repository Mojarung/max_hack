import { defineStore } from 'pinia'
import { ref } from 'vue'
import { errorMessage } from '@/api/client'
import { meApi } from '@/api/endpoints'
import type { PulseOut } from '@/api/types'
import { onRealtime } from '@/realtime/sse'
import { registerReset } from './helpers'

function isPulse(data: unknown): data is PulseOut {
  return !!data && typeof data === 'object' && 'mood' in data && 'score' in data && 'stats' in data
}

export const usePulseStore = defineStore('pulse', () => {
  const pulse = ref<PulseOut | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let refetchTimer: ReturnType<typeof setTimeout> | null = null

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      pulse.value = await meApi.pulse()
    } catch (e) {
      error.value = errorMessage(e)
    } finally {
      loading.value = false
    }
  }

  /** Тихо перезапрашиваем пульс (с дебаунсом), если событие пришло без полного объекта. */
  function softRefresh(): void {
    if (!pulse.value) return
    if (refetchTimer) clearTimeout(refetchTimer)
    refetchTimer = setTimeout(() => {
      meApi
        .pulse()
        .then((data) => (pulse.value = data))
        .catch(() => undefined)
    }, 400)
  }

  onRealtime('pulse.changed', (data) => {
    if (isPulse(data)) pulse.value = data
    else softRefresh()
  })
  onRealtime('resync', softRefresh)

  registerReset(() => {
    pulse.value = null
    error.value = null
  })

  return { pulse, loading, error, load, softRefresh }
})
