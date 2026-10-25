import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { installDragScroll } from './useDragScroll'

beforeAll(() => {
  installDragScroll()
})

afterEach(() => {
  document.body.innerHTML = ''
})

/** Лента шире своего окна: scrollWidth и clientWidth jsdom не считает, задаём сами. */
function strip(className = 'chips-scroll', scrollWidth = 600, clientWidth = 300): HTMLElement {
  const el = document.createElement('div')
  el.className = className
  const chip = document.createElement('button')
  chip.textContent = 'Чип'
  el.appendChild(chip)
  Object.defineProperty(el, 'scrollWidth', { value: scrollWidth })
  Object.defineProperty(el, 'clientWidth', { value: clientWidth })
  Object.defineProperty(el, 'scrollLeft', { value: 0, writable: true })
  document.body.appendChild(el)
  return el
}

function pointer(
  target: Element,
  type: string,
  clientX: number,
  pointerType = 'mouse',
  button = 0,
): void {
  target.dispatchEvent(
    Object.assign(new Event(type, { bubbles: true }), { clientX, pointerType, button }),
  )
}

function wheel(target: Element, deltaY: number, deltaX = 0): Event {
  const event = Object.assign(new Event('wheel', { bubbles: true, cancelable: true }), {
    deltaX,
    deltaY,
  })
  target.dispatchEvent(event)
  return event
}

describe('перетаскивание лент мышью', () => {
  it('лента листается за мышью, а клик после перетаскивания не нажимает чип', () => {
    const el = strip()
    const chip = el.querySelector('button')!
    const onClick = vi.fn()
    chip.addEventListener('click', onClick)

    pointer(chip, 'pointerdown', 200)
    pointer(chip, 'pointermove', 198)
    expect(el.scrollLeft).toBe(0)
    pointer(chip, 'pointermove', 120)
    expect(el.scrollLeft).toBe(80)
    expect(el.classList.contains('chips-scroll--dragging')).toBe(true)
    pointer(chip, 'pointerup', 120)
    expect(el.classList.contains('chips-scroll--dragging')).toBe(false)
    chip.click()
    expect(onClick).not.toHaveBeenCalled()
    // следующий обычный клик уже работает
    chip.click()
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('палец, правая кнопка и лента без прокрутки не перехватываются', () => {
    const el = strip()
    pointer(el, 'pointerdown', 200, 'touch')
    pointer(el, 'pointermove', 50, 'touch')
    pointer(el, 'pointerdown', 200, 'mouse', 2)
    pointer(el, 'pointermove', 50)
    expect(el.scrollLeft).toBe(0)

    const short = strip('chips-scroll', 300, 300)
    pointer(short, 'pointerdown', 200)
    pointer(short, 'pointermove', 50)
    pointer(short, 'pointercancel', 50)
    expect(short.scrollLeft).toBe(0)
  })
})

describe('колесо мыши над лентой чипов', () => {
  it('листает ленту вбок, пока есть куда', () => {
    const el = strip()
    const event = wheel(el, 100)
    expect(event.defaultPrevented).toBe(true)
    expect(el.scrollLeft).toBe(100)
    wheel(el, 500)
    expect(el.scrollLeft).toBe(300)
  })

  it('на краю ленты отдаёт колесо странице', () => {
    const el = strip()
    expect(wheel(el, -50).defaultPrevented).toBe(false)
    el.scrollLeft = 300
    expect(wheel(el, 50).defaultPrevented).toBe(false)
  })

  it('горизонтальную прокрутку, фото и короткие ленты не трогает', () => {
    expect(wheel(strip(), 10, 40).defaultPrevented).toBe(false)
    expect(wheel(strip('photo-carousel'), 100).defaultPrevented).toBe(false)
    expect(wheel(strip('chips-scroll', 300, 300), 100).defaultPrevented).toBe(false)
  })
})
