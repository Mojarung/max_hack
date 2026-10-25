import { describe, expect, it } from 'vitest'
import { renderComponent } from '@/test/harness'
import RefreshBar from './RefreshBar.vue'

describe('Полоса фоновой загрузки', () => {
  it('во время загрузки показывает бегущую полосу', async () => {
    await renderComponent(RefreshBar, { props: { active: true } })
    const bar = document.querySelector('.refresh-bar')!
    expect(bar.className).toContain('refresh-bar--on')
    expect(bar.querySelector('.v-progress-linear')).not.toBeNull()
    expect(bar.getAttribute('aria-hidden')).toBe('true')
  })

  it('в покое место занято, но полосы нет', async () => {
    await renderComponent(RefreshBar, { props: { active: false } })
    const bar = document.querySelector('.refresh-bar')!
    expect(bar.className).not.toContain('refresh-bar--on')
    expect(bar.querySelector('.v-progress-linear')).toBeNull()
  })
})
