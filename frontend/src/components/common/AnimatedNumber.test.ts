import { gsap } from 'gsap'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import { textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import AnimatedNumber from './AnimatedNumber.vue'

function shown(): string {
  return textOf(document.querySelector('.tabular-nums'))
}

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
  gsap.globalTimeline.timeScale(1)
})

describe('Анимированное число', () => {
  it('без анимаций сразу показывает новое значение', async () => {
    const props = reactive({ value: 12 })
    await renderComponent(AnimatedNumber, { props })
    expect(shown()).toBe('12')
    props.value = 40
    await nextTick()
    expect(shown()).toBe('40')
  })

  it('с анимацией досчитывает до нового значения', async () => {
    delete document.documentElement.dataset.motion
    // GSAP считает время по Date: размораживаем часы и ускоряем анимацию
    vi.useRealTimers()
    gsap.globalTimeline.timeScale(20)
    const props = reactive({ value: 0, duration: 0.3 })
    await renderComponent(AnimatedNumber, { props })
    props.value = 75
    await waitFor(() => shown() === '75', 3000)
  })
})
