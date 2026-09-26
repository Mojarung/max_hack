import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ApiError, errorMessage, setDevUser, setHouseId } from '@/api/client'
import { houseApi, meApi } from '@/api/endpoints'
import type { DevUser, HouseBrief, MeOut } from '@/api/types'
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

/** outside: открыто в обычном браузере, а сервер работает с настоящим MAX (без демо-жителей). */
export type BootStatus = 'booting' | 'ready' | 'error' | 'outside'

export const useSessionStore = defineStore('session', () => {
  const status = ref<BootStatus>('booting')
  const bootError = ref<string | null>(null)
  const inMax = ref(false)
  /** Ник бота для ссылки «Открыть в MAX» на экране outside. */
  const botUsername = ref<string | null>(null)
  const me = ref<MeOut | null>(null)
  const devUsers = ref<DevUser[]>([])
  const devUserId = ref<number | null>(null)
  const houses = ref<HouseBrief[]>([])
  const housesLoading = ref(false)
  /** Меняется при смене жителя: страницы по нему перемонтируются и перезагружают данные. */
  const userKey = ref(0)
  let listenersReady = false

  const isMock = computed(() => !inMax.value || !!me.value?.mock)
  const isAdmin = computed(() => me.value?.role === 'admin')
  const canUseDevTools = computed(() => !!me.value?.mock)
  const canManageMcp = computed(() => isAdmin.value || !!me.value?.mock)
  /** Дом только что подключили из чата: администратор должен указать адрес и УК. */
  const needsSetup = computed(() => isAdmin.value && me.value?.house.setup_done === false)
  const needsOnboarding = computed(() => !!me.value && me.value.user.onboarded === false)
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
        payload.title ? `Новая награда: ${payload.title}` : 'Новая награда!',
        payload.points ? `+${payload.points} очков` : 'Загляните в раздел «Награды»',
      )
      void refreshMe()
    })
  }

  async function refreshMe(): Promise<void> {
    let data: MeOut
    try {
      data = await meApi.me()
    } catch (error) {
      // житель вышел из чата выбранного дома: сервер сам подберёт доступный дом
      if (!(error instanceof ApiError && error.status === 403)) throw error
      setHouseId(null)
      data = await meApi.me()
    }
    me.value = data
    setHouseId(data.house?.id ?? null)
  }

  /** Дома жителя. refresh: Кузя заново проверит, в каких чатах с ним состоит житель. */
  async function loadHouses(refresh = false): Promise<void> {
    housesLoading.value = true
    try {
      houses.value = await houseApi.list(refresh)
    } finally {
      housesLoading.value = false
    }
  }

  /** Переключить дом: все экраны перезагружают данные нового дома. Бот в личке тоже переключится. */
  async function switchHouse(id: number): Promise<void> {
    if (id === me.value?.house.id) return
    const previous = me.value?.house.id ?? null
    setHouseId(id)
    try {
      await refreshMe()
      resetAllStores()
      connectRealtime()
      userKey.value += 1
      houses.value = houses.value.map((h) => ({ ...h, is_current: h.id === id }))
      notify.success(`Дом: ${me.value?.house.title ?? ''}`)
    } catch (error) {
      setHouseId(previous)
      notify.error(error, 'Не удалось переключить дом')
    }
  }

  async function completeOnboarding(): Promise<void> {
    if (me.value) me.value = { ...me.value, user: { ...me.value.user, onboarded: true } }
    try {
      me.value = await meApi.onboarded()
    } catch {
      // не критично: покажем обучалку ещё раз при следующем входе
    }
  }

  async function init(): Promise<void> {
    status.value = 'booting'
    bootError.value = null
    ready()
    inMax.value = isInMax()
    try {
      if (!inMax.value) {
        // старый сервер без /meta: ведём себя как раньше и просим демо-жителей
        const meta = await meApi.meta().catch(() => null)
        botUsername.value = meta?.bot_username ?? null
        if (meta && !meta.mock) {
          status.value = 'outside'
          return
        }
        await pickDevUser()
      }
      await refreshMe()
      setupListeners()
      connectRealtime()
      status.value = 'ready'
      void loadHouses().catch(() => undefined)
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
      setHouseId(null)
      await refreshMe()
      resetAllStores()
      connectRealtime()
      userKey.value += 1
      void loadHouses().catch(() => undefined)
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
    botUsername,
    me,
    devUsers,
    devUserId,
    houses,
    housesLoading,
    userKey,
    needsSetup,
    needsOnboarding,
    isMock,
    isAdmin,
    canUseDevTools,
    canManageMcp,
    currentDevUser,
    init,
    refreshMe,
    switchUser,
    loadHouses,
    switchHouse,
    completeOnboarding,
  }
})
