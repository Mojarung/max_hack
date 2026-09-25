import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { errorMessage } from '@/api/client'
import { announcementsApi } from '@/api/endpoints'
import type { AnnouncementOut } from '@/api/types'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { registerReset, removeById, upsertById } from './helpers'
import { useSessionStore } from './session'

/** Закреплённые сверху, дальше новые. */
function sorted(list: AnnouncementOut[]): AnnouncementOut[] {
  return [...list].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || b.created_at.localeCompare(a.created_at),
  )
}

export const useAnnouncementsStore = defineStore('announcements', () => {
  const items = ref<AnnouncementOut[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const top = computed(() => items.value.slice(0, 2))

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      items.value = sorted(await announcementsApi.list())
      loaded.value = true
    } catch (e) {
      error.value = errorMessage(e)
    } finally {
      loading.value = false
    }
  }

  function withMine(a: AnnouncementOut): AnnouncementOut {
    const me = useSessionStore().me
    return me ? { ...a, is_mine: a.author?.id === me.user.id } : a
  }

  async function create(body: { title: string; text: string; pin: boolean }): Promise<void> {
    const created = await announcementsApi.create(body)
    items.value = sorted(upsertById(items.value, created, { prepend: true }))
  }

  async function setPinned(id: number, pinned: boolean): Promise<void> {
    const updated = await announcementsApi.pin(id, pinned)
    items.value = sorted(upsertById(items.value, updated))
  }

  async function remove(id: number): Promise<void> {
    await announcementsApi.remove(id)
    items.value = removeById(items.value, id)
  }

  onRealtime('announcement.created', (data) => {
    if (!hasNumericId(data) || !loaded.value) return
    items.value = sorted(upsertById(items.value, withMine(data as AnnouncementOut)))
  })
  onRealtime('announcement.updated', (data) => {
    if (!hasNumericId(data)) return
    if ((data as { deleted?: boolean }).deleted) {
      items.value = removeById(items.value, data.id)
      return
    }
    items.value = sorted(
      upsertById(items.value, withMine(data as AnnouncementOut), { onlyExisting: true }),
    )
  })
  onRealtime('resync', () => {
    if (loaded.value) void load()
  })
  registerReset(() => {
    items.value = []
    loaded.value = false
    error.value = null
  })

  return { items, top, loaded, loading, error, load, create, setPinned, remove }
})
