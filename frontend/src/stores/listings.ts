import { defineStore } from 'pinia'
import { ref } from 'vue'
import { errorMessage } from '@/api/client'
import { listingsApi, normalizeCategories } from '@/api/endpoints'
import type { Category, ListingOut, ListingStatus } from '@/api/types'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { LISTING_CATEGORY_TITLES } from '@/utils/labels'
import { registerReset, removeById, upsertById } from './helpers'
import { useSessionStore } from './session'

export const useListingsStore = defineStore('listings', () => {
  const items = ref<ListingOut[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const query = ref('')
  const category = ref<string | null>(null)
  const freeOnly = ref(false)
  const categories = ref<Category[]>(normalizeCategories(null, LISTING_CATEGORY_TITLES))
  const details = ref<Record<number, ListingOut>>({})
  let categoriesLoaded = false
  let controller: AbortController | null = null

  async function load(): Promise<void> {
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = null
    try {
      const data = await listingsApi.list(
        { q: query.value.trim() || undefined, category: category.value, free: freeOnly.value },
        current.signal,
      )
      if (current.signal.aborted) return
      items.value = data
      loaded.value = true
    } catch (e) {
      if (current.signal.aborted) return
      error.value = errorMessage(e)
    } finally {
      if (controller === current) loading.value = false
    }
  }

  async function loadCategories(): Promise<void> {
    if (categoriesLoaded) return
    try {
      const raw = await listingsApi.categories()
      const list = normalizeCategories(raw, LISTING_CATEGORY_TITLES)
      if (list.length > 0) categories.value = list
      categoriesLoaded = true
    } catch {
      // остаются категории из контракта
    }
  }

  function withMine(listing: ListingOut): ListingOut {
    const me = useSessionStore().me
    return me ? { ...listing, is_mine: listing.author?.id === me.user.id } : listing
  }

  function storeDetail(listing: ListingOut): void {
    details.value = { ...details.value, [listing.id]: listing }
    items.value = upsertById(items.value, listing, { onlyExisting: true })
  }

  async function fetchDetail(id: number): Promise<ListingOut> {
    const data = await listingsApi.get(id)
    storeDetail(data)
    return data
  }

  async function setStatus(id: number, status: ListingStatus): Promise<ListingOut> {
    const data = await listingsApi.setStatus(id, status)
    storeDetail(data)
    return data
  }

  async function remove(id: number): Promise<void> {
    await listingsApi.remove(id)
    items.value = removeById(items.value, id)
    const next = { ...details.value }
    delete next[id]
    details.value = next
  }

  function matchesFilter(listing: ListingOut): boolean {
    if (listing.status === 'closed') return false
    if (category.value && listing.category !== category.value) return false
    if (freeOnly.value && !listing.is_free) return false
    const q = query.value.trim().toLowerCase()
    return !q || `${listing.title} ${listing.description}`.toLowerCase().includes(q)
  }

  onRealtime('listing.created', (data) => {
    if (!hasNumericId(data) || !loaded.value) return
    const listing = withMine(data as ListingOut)
    if (matchesFilter(listing)) items.value = upsertById(items.value, listing, { prepend: true })
  })

  onRealtime('listing.updated', (data) => {
    if (!hasNumericId(data)) return
    if ((data as { deleted?: boolean }).deleted) {
      // сервер присылает {id, deleted: true}, когда автор удалил объявление
      const { id } = data as { id: number }
      items.value = items.value.filter((item) => item.id !== id)
      if (details.value[id]) {
        const rest = { ...details.value }
        delete rest[id]
        details.value = rest
      }
      return
    }
    const listing = withMine(data as ListingOut)
    items.value = upsertById(items.value, listing, { onlyExisting: true })
    if (details.value[listing.id]) details.value = { ...details.value, [listing.id]: listing }
  })

  onRealtime('resync', () => {
    if (loaded.value) void load()
  })

  registerReset(() => {
    items.value = []
    details.value = {}
    loaded.value = false
    error.value = null
  })

  return {
    items,
    loaded,
    loading,
    error,
    query,
    category,
    freeOnly,
    categories,
    details,
    load,
    loadCategories,
    fetchDetail,
    storeDetail,
    setStatus,
    remove,
  }
})
