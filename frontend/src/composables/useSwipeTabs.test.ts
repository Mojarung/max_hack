import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { swipe } from '@/test/dom'
import { useSwipeTabs } from './useSwipeTabs'

afterEach(() => {
  document.body.innerHTML = ''
})

function mountArea(withArea = true) {
  const onSwipe = vi.fn()
  const wrapper = mount(
    defineComponent({
      setup() {
        const area = ref<HTMLElement | null>(null)
        useSwipeTabs(() => (withArea ? area.value : null), onSwipe)
        return () =>
          h('div', { ref: area, class: 'page' }, [
            h('div', { class: 'chips-scroll' }, 'чипы'),
            h('input', { type: 'text' }),
            h('p', 'текст'),
          ])
      },
    }),
    { attachTo: document.body },
  )
  return { wrapper, onSwipe, page: wrapper.find('p').element }
}

describe('свайп между вкладками', () => {
  it('палец влево открывает следующую вкладку, вправо - предыдущую', async () => {
    const { page, onSwipe } = mountArea()
    await swipe(page, { x: 300, y: 200 }, { x: 150, y: 210 })
    expect(onSwipe).toHaveBeenLastCalledWith(1)
    await swipe(page, { x: 100, y: 200 }, { x: 260, y: 190 })
    expect(onSwipe).toHaveBeenLastCalledWith(-1)
  })

  it('короткое и вертикальное движение - не свайп', async () => {
    const { page, onSwipe } = mountArea()
    await swipe(page, { x: 200, y: 200 }, { x: 160, y: 200 })
    await swipe(page, { x: 200, y: 100 }, { x: 120, y: 400 })
    expect(onSwipe).not.toHaveBeenCalled()
  })

  it('в ленте чипов и в поле ввода палец листает своё', async () => {
    const { wrapper, onSwipe } = mountArea()
    await swipe(wrapper.find('.chips-scroll').element, { x: 300, y: 0 }, { x: 0, y: 0 })
    await swipe(wrapper.find('input').element, { x: 300, y: 0 }, { x: 0, y: 0 })
    expect(onSwipe).not.toHaveBeenCalled()
  })

  it('прерванный жест и два пальца не переключают вкладку', async () => {
    const { page, onSwipe } = mountArea()
    const touch = (x: number) => ({ clientX: x, clientY: 0, identifier: 0, target: page })
    page.dispatchEvent(
      Object.assign(new Event('touchstart', { bubbles: true }), { touches: [touch(300)] }),
    )
    page.dispatchEvent(new Event('touchcancel', { bubbles: true }))
    page.dispatchEvent(
      Object.assign(new Event('touchend', { bubbles: true }), { changedTouches: [touch(0)] }),
    )
    page.dispatchEvent(
      Object.assign(new Event('touchstart', { bubbles: true }), {
        touches: [touch(300), touch(310)],
      }),
    )
    page.dispatchEvent(
      Object.assign(new Event('touchend', { bubbles: true }), { changedTouches: [touch(0)] }),
    )
    page.dispatchEvent(Object.assign(new Event('touchstart', { bubbles: true }), { touches: [] }))
    expect(onSwipe).not.toHaveBeenCalled()
  })

  it('после ухода с экрана жесты не слушает', async () => {
    const { wrapper, page, onSwipe } = mountArea()
    wrapper.unmount()
    await swipe(page, { x: 300, y: 0 }, { x: 0, y: 0 })
    expect(onSwipe).not.toHaveBeenCalled()
  })

  it('без области экрана ничего не ломается', () => {
    const { wrapper } = mountArea(false)
    expect(() => wrapper.unmount()).not.toThrow()
  })
})
