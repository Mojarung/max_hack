/**
 * Имитация MAX Bridge: приложение ведёт себя как внутри MAX (без демо-переключателя
 * жителей), а вызовы моста пишутся в консоль, чтобы их было видно при проверке.
 */
import type { MaxWebApp } from '@/max/bridge'
import { scenario } from './scenario'

export function installMockBridge(): void {
  if (!scenario.motion) document.documentElement.dataset.motion = 'off'
  if (!scenario.inMax) {
    // Браузерный демо-режим: как в обычном браузере, initData пустой
    window.WebApp = { initData: '' }
    return
  }
  // eslint-disable-next-line no-console -- видимые в консоли вызовы моста и есть смысл мока
  const log = (...args: unknown[]) => console.info('[mock-bridge]', ...args)
  const clicks = new Set<() => void>()
  const app: MaxWebApp = {
    initData: 'mock-init-data',
    initDataUnsafe: { user: { id: 1001, first_name: 'Анна' }, chat: { id: 1, type: 'chat' } },
    platform: 'ios',
    version: 'mock',
    ready: () => log('ready'),
    close: () => log('close'),
    BackButton: {
      isVisible: false,
      show() {
        this.isVisible = true
      },
      hide() {
        this.isVisible = false
      },
      onClick: (cb) => clicks.add(cb),
      offClick: (cb) => clicks.delete(cb),
    },
    HapticFeedback: {
      impactOccurred: (style) => log('haptic', style),
      notificationOccurred: (type) => log('haptic', type),
      selectionChanged: () => log('haptic', 'selection'),
    },
    openLink: (url) => log('openLink', url),
    openMaxLink: (url) => log('openMaxLink', url),
    shareContent: (text) => log('share', text),
    shareMaxContent: (text) => log('shareMax', text),
    enableClosingConfirmation: () => log('closingConfirmation', true),
    disableClosingConfirmation: () => log('closingConfirmation', false),
  }
  window.WebApp = app
  // Системная кнопка «Назад» MAX: в мок-режиме её можно нажать из консоли
  ;(window as unknown as { __maxBack: () => void }).__maxBack = () => clicks.forEach((cb) => cb())
}
