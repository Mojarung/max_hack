import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { errorMessage, setDevUser, setHouseId } from '@/api/client'
import { meApi } from '@/api/endpoints'
import type { DevUser, MeOut } from '@/api/types'
import { notify } from '@/lib/notify'
import { isInMax, ready } from '@/max/bridge'
import { connectRealtime, onRealtime } from '@/realtime/sse'
import { resetAllStores } from './helpers'

const DEV_USER_KEY = 'kuzya.devUser'

function readSavedDevUser(): number | null {
  try {
    const raw = localStorage.getItem(DEV_USER_KEY)
    const id = raw ? Number(raw) : NaN
    return Number.isFinite(id) ? id : null
  } catch {
    return null
  }
}

function saveDevUser(id: number): void {
  try {
    localStorage.setItem(DEV_USER_KEY, String(id))
  } catch {
    // приватный режим или запрет хранилища: просто не запоминаем выбор
  }
}

export type BootStatus = 'booting' | 'ready' | 'error'

export const useSessionStore = defineStore('session', () => {
  const status = ref<BootStatus>('booting')
  const bootError = ref<string | null>(null)
  const inMax = ref(false)
  const me = ref<MeOut | null>(null)
  const devUsers = ref<DevUser[]>([])
  const devUserId = ref<number | null>(null)
  /** Меняется при смене жителя: страницы по нему перемонтируются и перезагружают данные. */
  const userKey = ref(0)
  let listenersReady = false

  const isMock = computed(() => !inMax.value || !!me.value?.mock)
  const isAdmin = computed(() => me.value?.role === 'admin')
  const canUseDevTools = computed(() => !!me.value?.mock)
  const canManageMcp = computed(() => isAdmin.value || !!me.value?.mock)
  const currentDevUser = computed(
    () => devUsers.value.find((u) => u.max_user_id === devUserId.value) ?? null,
  )

  function setupListeners(): void {
    if (listenersReady) return
    listenersReady = true
    onRealtime('achievement.awarded', (data) => {
      const payload = (data ?? {}) as { user_id?: number; title?: string; points?: number }
      if (!me.value || payload.user_id !== me.value.user.id) return
      notify.success(
        payload.title ? `Новая ачивка: ${payload.title}` : 'Новая ачивка!',
        payload.points ? `+${payload.points} очков` : 'Загляните в раздел «Ачивки»',
      )
      void refreshMe()
    })
  }

  async function refreshMe(): Promise<void> {
    const data = await meApi.me()
    me.value = data
    setHouseId(data.house?.id ?? null)
  }

  async function init(): Promise<void> {
    status.value = 'booting'
    bootError.value = null
    ready()
    inMax.value = isInMax()
    try {
      if (!inMax.value) await pickDevUser()
      await refreshMe()
      setupListeners()
      connectRealtime()
      status.value = 'ready'
    } catch (error) {
      bootError.value = inMax.value
        ? errorMessage(error)
        : `${errorMessage(error)}. Для демо запустите сервер с MOCK_MAX=true или откройте приложение в MAX.`
      status.value = 'error'
    }
  }

  async function pickDevUser(): Promise<void> {
    devUsers.value = await meApi.devUsers()
    if (devUsers.value.length === 0) throw new Error('Нет демо-жителей')
    const saved = readSavedDevUser()
    const found = devUsers.value.find((u) => u.max_user_id === saved)
    devUserId.value = (found ?? devUsers.value[0]!).max_user_id
    setDevUser(devUserId.value)
  }

  async function switchUser(id: number): Promise<void> {
    if (id === devUserId.value) return
    const previous = devUserId.value
    devUserId.value = id
    setDevUser(id)
    saveDevUser(id)
    try {
      await refreshMe()
      resetAllStores()
      connectRealtime()
      userKey.value += 1
      notify.success(`Теперь вы: ${me.value?.user.first_name ?? 'житель'}`)
    } catch (error) {
      devUserId.value = previous
      setDevUser(previous)
      notify.error(error, 'Не удалось сменить жителя')
    }
  }

  return {
    status,
    bootError,
    inMax,
    me,
    devUsers,
    devUserId,
    userKey,
    isMock,
    isAdmin,
    canUseDevTools,
    canManageMcp,
    currentDevUser,
    init,
    refreshMe,
    switchUser,
  }
})
