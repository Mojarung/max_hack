import { mount } from '@vue/test-utils'
import { gsap } from 'gsap'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import {
  confetti,
  pageEnter,
  pageLeave,
  pop,
  prefersReducedMotion,
  setNavDirection,
  staggerIn,
  useStagger,
} from './useMotion'

/** Анимации включены (в тестах по умолчанию они выключены через data-motion). */
function motionOn(): void {
  delete document.documentElement.dataset.motion
}

function list(count: number): HTMLElement {
  const root = document.createElement('div')
  for (let i = 0; i < count; i++) {
    const item = document.createElement('div')
    item.dataset.stagger = ''
    root.appendChild(item)
  }
  document.body.appendChild(root)
  return root
}

beforeEach(() => {
  document.documentElement.dataset.motion = 'off'
})

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
  document.body.innerHTML = ''
  setNavDirection('tab')
})

describe('уважение к настройке «уменьшить движение»', () => {
  it('мок-режим без анимаций считается «меньше движения»', () => {
    expect(prefersReducedMotion()).toBe(true)
  })

  it('иначе слушается системной настройки', () => {
    motionOn()
    const media = vi.spyOn(window, 'matchMedia')
    media.mockReturnValue({ matches: true } as MediaQueryList)
    expect(prefersReducedMotion()).toBe(true)
    media.mockReturnValue({ matches: false } as MediaQueryList)
    expect(prefersReducedMotion()).toBe(false)
  })
})

describe('появление списка лесенкой', () => {
  it('без анимаций только помечает карточки показанными', () => {
    const fromTo = vi.spyOn(gsap, 'fromTo')
    const root = list(3)
    staggerIn(root)
    expect(root.querySelectorAll('[data-shown="1"]')).toHaveLength(3)
    expect(fromTo).not.toHaveBeenCalled()
  })

  it('с анимациями проявляет только новые карточки', () => {
    motionOn()
    const fromTo = vi.spyOn(gsap, 'fromTo').mockReturnValue({} as gsap.core.Tween)
    const root = list(2)
    staggerIn(root, '[data-stagger]')
    expect(fromTo).toHaveBeenCalledTimes(1)
    expect((fromTo.mock.calls[0]![0] as HTMLElement[]).length).toBe(2)
    staggerIn(root)
    expect(fromTo).toHaveBeenCalledTimes(1)
  })

  it('без контейнера ничего не делает', () => {
    expect(() => staggerIn(null)).not.toThrow()
  })

  it('useStagger проявляет список при монтировании и при изменении данных', async () => {
    const items = ref([1])
    const wrapper = mount(
      defineComponent({
        setup() {
          const root = ref<HTMLElement | null>(null)
          useStagger(root, () => items.value.length)
          return () =>
            h(
              'div',
              { ref: root },
              items.value.map((i) => h('div', { key: i, 'data-stagger': '' })),
            )
        },
      }),
      { attachTo: document.body },
    )
    await nextTick()
    await nextTick()
    expect(wrapper.findAll('[data-shown="1"]')).toHaveLength(1)
    items.value = [1, 2]
    await nextTick()
    await nextTick()
    expect(wrapper.findAll('[data-shown="1"]')).toHaveLength(2)
  })
})

describe('переходы между экранами', () => {
  it('без анимаций переключает сразу, но не посреди отрисовки', async () => {
    const el = document.createElement('div')
    const enterDone = vi.fn()
    const leaveDone = vi.fn()
    pageEnter(el, enterDone)
    pageLeave(el, leaveDone)
    expect(enterDone).not.toHaveBeenCalled()
    await Promise.resolve()
    expect(enterDone).toHaveBeenCalled()
    expect(leaveDone).toHaveBeenCalled()
  })

  it.each([
    ['push', { opacity: 0, x: 48 }, { opacity: 0, x: -28 }],
    ['pop', { opacity: 0, x: -36 }, { opacity: 0, x: 40 }],
    ['tab', { opacity: 0, scale: 0.985 }, { opacity: 0 }],
  ] as const)('направление %s: экран въезжает с нужной стороны', (direction, from, to) => {
    motionOn()
    const fromTo = vi.spyOn(gsap, 'fromTo').mockReturnValue({} as gsap.core.Tween)
    const tween = vi.spyOn(gsap, 'to').mockReturnValue({} as gsap.core.Tween)
    setNavDirection(direction)
    const el = document.createElement('div')
    const done = vi.fn()
    pageEnter(el, done)
    pageLeave(el, done)
    expect(fromTo.mock.calls[0]![1]).toEqual(from)
    expect(tween.mock.calls[0]![1]).toMatchObject(to)
    const vars = fromTo.mock.calls[0]![2] as gsap.TweenVars
    expect(vars.duration).toBe(direction === 'tab' ? 0.24 : 0.34)
    ;(vars.onComplete as () => void)()
    expect(done).toHaveBeenCalled()
  })
})

describe('отклик на действие', () => {
  it('«пульс» элемента только с анимациями', () => {
    const fromTo = vi.spyOn(gsap, 'fromTo').mockReturnValue({} as gsap.core.Tween)
    const el = document.createElement('button')
    pop(el)
    pop(null)
    expect(fromTo).not.toHaveBeenCalled()
    motionOn()
    pop(el)
    expect(fromTo).toHaveBeenCalledWith(el, { scale: 0.92 }, expect.any(Object))
  })

  it('конфетти появляется и убирается после анимации', () => {
    const tween = vi.spyOn(gsap, 'to').mockReturnValue({} as gsap.core.Tween)
    const box = document.createElement('div')
    confetti(box, 6)
    expect(box.children).toHaveLength(0)

    motionOn()
    confetti(box, 6)
    expect(box.querySelectorAll('.confetti-piece')).toHaveLength(6)
    const vars = tween.mock.calls[0]![1] as gsap.TweenVars
    // каждый кусочек летит в свою сторону и гаснет за 1-2 секунды
    const value = (key: keyof gsap.TweenVars) => (vars[key] as () => number)()
    expect(value('duration')).toBeGreaterThanOrEqual(1.1)
    expect(value('duration')).toBeLessThanOrEqual(1.9)
    expect(Math.abs(value('rotation'))).toBeLessThanOrEqual(540)
    expect(Number.isFinite(value('x') + value('y'))).toBe(true)
    ;(vars.onComplete as () => void)()
    expect(box.children).toHaveLength(0)
  })

  it('конфетти без контейнера не падает', () => {
    motionOn()
    expect(() => confetti(null)).not.toThrow()
  })
})
