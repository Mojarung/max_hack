import { gsap } from 'gsap'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import HealthRing from './HealthRing.vue'

const CIRCUMFERENCE = 2 * Math.PI * 44

function ring(): HTMLElement {
  return document.querySelector('[role="img"]') as HTMLElement
}

function arc(): SVGCircleElement {
  return ring().querySelectorAll('circle')[1] as SVGCircleElement
}

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
  gsap.globalTimeline.timeScale(1)
})

describe('Кольцо здоровья дома', () => {
  it('показывает оценку цифрой и словами для диктора', async () => {
    await renderComponent(HealthRing, { props: { score: 82, size: 96 } })
    expect(ring().getAttribute('aria-label')).toBe('Здоровье дома 82 из 100')
    expect(ring().style.width).toBe('96px')
    expect(textOf(ring().querySelector('strong'))).toBe('82')
    expect(textOf(ring())).toContain('из 100')
  })

  it.each([
    [82, 'success'],
    [60, 'warning'],
    [30, 'error'],
  ])('оценка %i окрашена цветом %s', async (score, color) => {
    await renderComponent(HealthRing, { props: { score } })
    expect(arc().getAttribute('stroke')).toBe(`rgb(var(--v-theme-${color}))`)
  })

  it('заполняет кольцо по оценке', async () => {
    await renderComponent(HealthRing, { props: { score: 25 } })
    const offset = Number(gsap.getProperty(arc(), 'strokeDashoffset'))
    expect(offset).toBeCloseTo(CIRCUMFERENCE * 0.75, 1)
  })

  it('оценку вне шкалы прижимает к 0..100', async () => {
    await renderComponent(HealthRing, { props: { score: 130 } })
    expect(ring().getAttribute('aria-label')).toBe('Здоровье дома 100 из 100')
  })

  it('с анимацией кольцо доезжает до оценки', async () => {
    delete document.documentElement.dataset.motion
    vi.useRealTimers()
    gsap.globalTimeline.timeScale(20)
    await renderComponent(HealthRing, { props: { score: -10 } })
    expect(ring().getAttribute('aria-label')).toBe('Здоровье дома 0 из 100')
    await waitFor(
      () => Math.abs(Number(gsap.getProperty(arc(), 'strokeDashoffset')) - CIRCUMFERENCE) < 0.5,
      3000,
    )
  })
})
