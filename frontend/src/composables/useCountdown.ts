import { computed, onScopeDispose, ref, type Ref } from 'vue'
import { formatCountdown, type Countdown } from '@/utils/format'

const now = ref(Date.now())
let subscribers = 0
let timer: ReturnType<typeof setInterval> | null = null

/** Общие «часы» на всё приложение: тикают раз в 30 секунд, пока есть подписчики. */
function useNow(): Ref<number> {
  subscribers += 1
  if (!timer) {
    now.value = Date.now()
    timer = setInterval(() => (now.value = Date.now()), 30_000)
  }
  onScopeDispose(() => {
    subscribers -= 1
    if (subscribers === 0 && timer) {
      clearInterval(timer)
      timer = null
    }
  })
  return now
}

export function useCountdown(deadline: Ref<string | null | undefined>): Ref<Countdown | null> {
  const clock = useNow()
  return computed(() => {
    if (!deadline.value) return null
    const target = Date.parse(deadline.value)
    if (Number.isNaN(target)) return null
    return formatCountdown(target - clock.value)
  })
}
