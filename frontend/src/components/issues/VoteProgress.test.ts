import { gsap } from 'gsap'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import { getByText, queryByText, textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import VoteProgress from './VoteProgress.vue'

function bar(): HTMLElement {
  return document.querySelector('[role="progressbar"] > div') as HTMLElement
}

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
  gsap.globalTimeline.timeScale(1)
})

describe('Полоса голосов', () => {
  it('показывает, сколько голосов собрано из нужных', async () => {
    await renderComponent(VoteProgress, { props: { count: 3, needed: 6 } })
    const progress = document.querySelector('[role="progressbar"]')!
    expect(progress.getAttribute('aria-label')).toBe('Голосов: 3 из 6')
    expect(progress.getAttribute('aria-valuenow')).toBe('3')
    expect(progress.getAttribute('aria-valuemax')).toBe('6')
    expect(getByText('из 6 голосов')).toBeTruthy()
    expect(queryByText('Голосов хватает')).toBeNull()
    expect(gsap.getProperty(bar(), 'scaleX')).toBe(0.5)
    expect(bar().className).toContain('bg-primary')
  })

  it('когда голосов достаточно, полоса полная, зелёная и с подписью', async () => {
    await renderComponent(VoteProgress, { props: { count: 8, needed: 6 } })
    expect(getByText('Голосов хватает')).toBeTruthy()
    expect(gsap.getProperty(bar(), 'scaleX')).toBe(1)
    expect(bar().className).toContain('bg-success')
  })

  it('отправленная заявка считается набравшей голоса, даже если цифра меньше', async () => {
    await renderComponent(VoteProgress, { props: { count: 2, needed: 6, done: true } })
    expect(getByText('Голосов хватает')).toBeTruthy()
    expect(gsap.getProperty(bar(), 'scaleX')).toBe(1)
  })

  it('склоняет слово «голос» по числу', async () => {
    await renderComponent(VoteProgress, { props: { count: 1, needed: 21 } })
    expect(textOf(document.querySelector('.text-muted'))).toContain('1 из 21 голоса')
  })

  it('без порога полоса пустая', async () => {
    await renderComponent(VoteProgress, { props: { count: 4, needed: 0 } })
    expect(gsap.getProperty(bar(), 'scaleX')).toBe(0)
  })

  it('в компактном виде остаётся только полоса', async () => {
    await renderComponent(VoteProgress, { props: { count: 3, needed: 6, compact: true } })
    expect(document.querySelector('[role="progressbar"]')!.className).toContain('h-2')
    expect(queryByText('из 6 голосов')).toBeNull()
  })

  it('с анимацией полоса плавно доезжает до нового значения', async () => {
    delete document.documentElement.dataset.motion
    // GSAP считает время по Date: размораживаем часы и ускоряем анимацию
    vi.useRealTimers()
    gsap.globalTimeline.timeScale(20)
    const props = reactive({ count: 1, needed: 4 })
    await renderComponent(VoteProgress, { props })
    props.count = 4
    await nextTick()
    await waitFor(() => gsap.getProperty(bar(), 'scaleX') === 1, 3000)
    expect(getByText('Голосов хватает')).toBeTruthy()
  })
})
