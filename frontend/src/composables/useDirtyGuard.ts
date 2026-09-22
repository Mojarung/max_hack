import { onBeforeUnmount, watch, type Ref } from 'vue'
import { setClosingConfirmation } from '@/max/bridge'

/** Пока форма заполнена, MAX спросит подтверждение перед закрытием мини-приложения. */
export function useDirtyGuard(dirty: Ref<boolean>): void {
  watch(dirty, (value) => setClosingConfirmation(value), { immediate: true })
  onBeforeUnmount(() => setClosingConfirmation(false))
}
