import { toast } from 'vue-sonner'
import { errorMessage } from '@/api/client'
import { haptic } from '@/max/bridge'

/** Единая обратная связь: тост + вибро на телефоне. */
export const notify = {
  success(message: string, description?: string): void {
    haptic.notify('success')
    toast.success(message, { description })
  },
  info(message: string, description?: string): void {
    toast(message, { description })
  },
  warning(message: string, description?: string): void {
    haptic.notify('warning')
    toast.warning(message, { description })
  },
  error(error: unknown, fallbackTitle?: string): void {
    haptic.notify('error')
    const text = errorMessage(error)
    if (fallbackTitle) toast.error(fallbackTitle, { description: text })
    else toast.error(text)
  },
}
