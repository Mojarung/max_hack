import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { toast } from 'vue-sonner'
import { ApiError } from '@/api/client'
import { notify } from './notify'

vi.mock('vue-sonner', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn() }),
}))

let vibrate: Mock<(type: string) => void>

beforeEach(() => {
  vibrate = vi.fn()
  window.WebApp = {
    initData: 'signed',
    platform: 'ios',
    HapticFeedback: { impactOccurred: vi.fn(), notificationOccurred: vibrate },
  }
})

afterEach(() => {
  vi.clearAllMocks()
  delete window.WebApp
})

describe('обратная связь жителю', () => {
  it('успех: зелёный тост и короткое вибро', () => {
    notify.success('Голос учтён', 'Спасибо!')
    expect(toast.success).toHaveBeenCalledWith('Голос учтён', { description: 'Спасибо!' })
    expect(vibrate).toHaveBeenCalledWith('success')
  })

  it('подсказка: обычный тост без вибро', () => {
    notify.info('Скопировано')
    expect(toast).toHaveBeenCalledWith('Скопировано', { description: undefined })
    expect(vibrate).not.toHaveBeenCalled()
  })

  it('предупреждение с вибро', () => {
    notify.warning('Нет интернета')
    expect(toast.warning).toHaveBeenCalledWith('Нет интернета', { description: undefined })
    expect(vibrate).toHaveBeenCalledWith('warning')
  })

  it('ошибка с заголовком: текст ошибки сервера в описании', () => {
    notify.error(new ApiError('http', 409, 'Вы уже голосовали'), 'Не получилось')
    expect(toast.error).toHaveBeenCalledWith('Не получилось', { description: 'Вы уже голосовали' })
    expect(vibrate).toHaveBeenCalledWith('error')
  })

  it('ошибка без заголовка: только понятный текст', () => {
    notify.error('что-то странное')
    expect(toast.error).toHaveBeenCalledWith('Что-то пошло не так')
  })
})
