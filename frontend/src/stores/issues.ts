import { defineStore } from 'pinia'
import { ref } from 'vue'
import { errorMessage } from '@/api/client'
import { issuesApi } from '@/api/endpoints'
import type { IssueDetail, IssueOut, IssueStatus } from '@/api/types'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { registerReset, upsertById } from './helpers'

/** Поля, посчитанные сервером для конкретного жителя: из SSE их не берём. */
const PERSONAL_KEYS: (keyof IssueOut)[] = ['voted_by_me']

export const useIssuesStore = defineStore('issues', () => {
  const items = ref<IssueOut[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const status = ref<IssueStatus | null>(null)
  const query = ref('')
  const details = ref<Record<number, IssueDetail>>({})
  let listController: AbortController | null = null

  async function load(): Promise<void> {
    listController?.abort()
    const controller = new AbortController()
    listController = controller
    loading.value = true
    error.value = null
    try {
      const data = await issuesApi.list(
        { status: status.value, q: query.value.trim() || undefined },
        controller.signal,
      )
      if (controller.signal.aborted) return
      items.value = data
      loaded.value = true
    } catch (e) {
      if (controller.signal.aborted) return
      error.value = errorMessage(e)
    } finally {
      if (listController === controller) loading.value = false
    }
  }

  async function fetchDetail(id: number): Promise<IssueDetail> {
    const data = await issuesApi.get(id)
    storeDetail(data)
    return data
  }

  function storeDetail(data: IssueDetail): void {
    details.value = { ...details.value, [data.id]: data }
    items.value = upsertById(items.value, data, { onlyExisting: true })
  }

  /** Голос с оптимистичным обновлением и откатом при ошибке. */
  async function toggleVote(id: number): Promise<IssueDetail> {
    const before = details.value[id]
    const beforeItem = items.value.find((i) => i.id === id)
    const base = before ?? beforeItem
    if (!base) throw new Error('Проблема не найдена')
    const voting = !base.voted_by_me
    const optimistic = {
      voted_by_me: voting,
      votes_count: Math.max(0, base.votes_count + (voting ? 1 : -1)),
    }
    if (before) details.value = { ...details.value, [id]: { ...before, ...optimistic } }
    if (beforeItem) items.value = upsertById(items.value, { ...beforeItem, ...optimistic })
    try {
      const data = voting ? await issuesApi.vote(id) : await issuesApi.unvote(id)
      storeDetail(data)
      return data
    } catch (e) {
      if (before) details.value = { ...details.value, [id]: before }
      if (beforeItem) items.value = upsertById(items.value, beforeItem)
      throw e
    }
  }

  async function setStatus(
    id: number,
    next: 'in_progress' | 'resolved' | 'rejected',
    note: string,
  ): Promise<IssueDetail> {
    const data = await issuesApi.setStatus(id, next, note)
    storeDetail(data)
    return data
  }

  function matchesFilter(issue: IssueOut): boolean {
    if (status.value && issue.status !== status.value) return false
    const q = query.value.trim().toLowerCase()
    if (!q) return true
    return `${issue.title} ${issue.description}`.toLowerCase().includes(q)
  }

  onRealtime('issue.created', (data) => {
    if (!hasNumericId(data) || !loaded.value) return
    const issue = data as IssueOut
    if (matchesFilter(issue)) items.value = upsertById(items.value, issue, { prepend: true })
  })

  onRealtime('issue.updated', (data) => {
    if (!hasNumericId(data)) return
    const issue = data as IssueOut
    const exists = items.value.some((i) => i.id === issue.id)
    if (exists && !matchesFilter(issue)) {
      items.value = items.value.filter((i) => i.id !== issue.id)
    } else {
      items.value = upsertById(items.value, issue, {
        keep: PERSONAL_KEYS,
        onlyExisting: !loaded.value,
      })
    }
    const cached = details.value[issue.id]
    if (cached) {
      details.value = {
        ...details.value,
        [issue.id]: { ...cached, ...issue, voted_by_me: cached.voted_by_me },
      }
      // Таймлайн и текст обращения приходят только в детальной карточке
      fetchDetail(issue.id).catch(() => undefined)
    }
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
    status,
    query,
    details,
    load,
    fetchDetail,
    storeDetail,
    toggleVote,
    setStatus,
  }
})
