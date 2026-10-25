import { describe, expect, it, vi } from 'vitest'
import { stopBrowserDemo } from '@/api/mode'
import { click, getByText, waitFor } from '@/test/dom'
import { renderApp, renderComponent } from '@/test/harness'
import BrowserDemoBar from './BrowserDemoBar.vue'

// Демо в браузере: полоса видна, а выход из демо (с перезагрузкой страницы) только записываем
vi.mock('@/api/mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/mode')>()),
  BROWSER_DEMO: true,
  stopBrowserDemo: vi.fn(),
}))

describe('Полоса демо-режима', () => {
  it('предупреждает, что дом вымышленный, и выводит из демо', async () => {
    await renderComponent(BrowserDemoBar)
    expect(getByText('Демо: дом и соседи вымышленные').closest('[role="note"]')).not.toBeNull()
    await click('Выйти')
    expect(stopBrowserDemo).toHaveBeenCalledTimes(1)
  })

  it('в демо из браузера видна под шапкой на всех экранах', async () => {
    await renderApp('/more', { scenario: { inMax: false } })
    await waitFor(() => getByText('Демо: дом и соседи вымышленные'))
  })
})
