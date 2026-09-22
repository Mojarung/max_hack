/**
 * Обёртка над MAX Bridge (`window.WebApp` из https://st.max.ru/js/max-web-app.js).
 *
 * Внутри MAX у `WebApp` непустой `initData`. В обычном браузере скрипт тоже
 * создаёт `window.WebApp`, но `initData` пустой, поэтому считаем это мок-режимом.
 */

export type ImpactStyle = 'soft' | 'light' | 'medium' | 'heavy' | 'rigid'
export type NotificationType = 'error' | 'success' | 'warning'

interface MaxBackButton {
  isVisible?: boolean
  show(): void
  hide(): void
  onClick(cb: () => void): void
  offClick(cb: () => void): void
}

interface MaxHaptic {
  impactOccurred(style: ImpactStyle, disableVibrationFallback?: boolean): void
  notificationOccurred(type: NotificationType, disableVibrationFallback?: boolean): void
  selectionChanged?(disableVibrationFallback?: boolean): void
}

export interface MaxWebApp {
  initData?: string
  initDataUnsafe?: {
    start_param?: string
    user?: { id: number; first_name?: string; last_name?: string; username?: string }
    chat?: { id: number; type?: string }
  }
  platform?: string
  version?: string
  ready?(): void
  close?(): void
  BackButton?: MaxBackButton
  HapticFeedback?: MaxHaptic
  openLink?(url: string): void
  openMaxLink?(url: string): void
  shareContent?(text: string, link?: string): void
  shareMaxContent?(text: string, link?: string): void
  enableClosingConfirmation?(): void
  disableClosingConfirmation?(): void
}

declare global {
  interface Window {
    WebApp?: MaxWebApp
  }
}

function webApp(): MaxWebApp | undefined {
  return typeof window === 'undefined' ? undefined : window.WebApp
}

/** true, если приложение открыто внутри MAX (есть подписанный initData). */
export function isInMax(): boolean {
  const app = webApp()
  return typeof app?.initData === 'string' && app.initData.trim().length > 0
}

export function getInitData(): string {
  return isInMax() ? (webApp()?.initData ?? '') : ''
}

/**
 * Параметр запуска для диплинка. В MAX берём `initDataUnsafe.start_param`,
 * в мок-режиме для удобства демо читаем `?startapp=` или `?start_param=` из адреса.
 */
export function getStartParam(): string | null {
  if (isInMax()) {
    const value = webApp()?.initDataUnsafe?.start_param
    return value ? String(value) : null
  }
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  return params.get('startapp') ?? params.get('start_param')
}

export function getPlatform(): string {
  return webApp()?.platform ?? 'web'
}

/** Вибро имеет смысл только на телефонах. */
function hapticAvailable(): boolean {
  const platform = getPlatform()
  return isInMax() && platform !== 'web' && platform !== 'desktop'
}

export function ready(): void {
  if (!isInMax()) return
  safe(() => webApp()?.ready?.())
}

export const haptic = {
  impact(style: ImpactStyle = 'light'): void {
    if (!hapticAvailable()) return
    safe(() => webApp()?.HapticFeedback?.impactOccurred(style))
  },
  notify(type: NotificationType): void {
    if (!hapticAvailable()) return
    safe(() => webApp()?.HapticFeedback?.notificationOccurred(type))
  },
  selection(): void {
    if (!hapticAvailable()) return
    safe(() => webApp()?.HapticFeedback?.selectionChanged?.())
  },
}

let backHandler: (() => void) | null = null

export const backButton = {
  show(onClick: () => void): void {
    const button = webApp()?.BackButton
    if (!isInMax() || !button) return
    safe(() => {
      if (backHandler) button.offClick(backHandler)
      backHandler = onClick
      button.onClick(onClick)
      button.show()
    })
  },
  hide(): void {
    const button = webApp()?.BackButton
    if (!isInMax() || !button) return
    safe(() => {
      if (backHandler) button.offClick(backHandler)
      backHandler = null
      button.hide()
    })
  },
}

export function openLink(url: string): void {
  const app = webApp()
  if (isInMax() && app?.openLink) {
    if (safe(() => app.openLink?.(url))) return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function openMaxLink(url: string): void {
  const app = webApp()
  if (isInMax() && app?.openMaxLink) {
    if (safe(() => app.openMaxLink?.(url))) return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

export type ShareResult = 'shared' | 'copied' | 'failed'

/** Поделиться: MAX -> Web Share API -> копирование в буфер. */
export async function shareContent(text: string, link?: string): Promise<ShareResult> {
  const app = webApp()
  if (isInMax() && app?.shareMaxContent) {
    if (safe(() => app.shareMaxContent?.(text, link))) return 'shared'
  }
  if (isInMax() && app?.shareContent) {
    if (safe(() => app.shareContent?.(text, link))) return 'shared'
  }
  if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
    try {
      await navigator.share({ text, url: link })
      return 'shared'
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return 'failed'
    }
  }
  return (await copyText(link ? `${text}\n${link}` : text)) ? 'copied' : 'failed'
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand('copy')
      area.remove()
      return ok
    } catch {
      return false
    }
  }
}

export function setClosingConfirmation(enabled: boolean): void {
  const app = webApp()
  if (!isInMax() || !app) return
  safe(() => (enabled ? app.enableClosingConfirmation?.() : app.disableClosingConfirmation?.()))
}

/** Выполняет вызов моста, не давая исключению уронить интерфейс. */
function safe(fn: () => void): boolean {
  try {
    fn()
    return true
  } catch (error) {
    console.warn('[max-bridge]', error)
    return false
  }
}
