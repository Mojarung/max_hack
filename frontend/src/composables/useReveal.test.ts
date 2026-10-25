import { gsap } from 'gsap'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { staggerIn } from './useMotion'
import { installAutoReveal } from './useReveal'

/** Наблюдатель, который ничего не сообщает: блоки остаются ниже экрана. */
class SilentObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

function page(html: string): HTMLElement {
  const root = document.createElement('main')
  root.innerHTML = html
  document.body.appendChild(root)
  return root
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  delete document.documentElement.dataset.motion
})

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
  document.body.innerHTML = ''
})

describe('появление блоков при прокрутке', () => {
  it('без анимаций ничего не прячет', () => {
    document.documentElement.dataset.motion = 'off'
    const root = page('<div class="card-soft">Карточка</div>')
    const stop = installAutoReveal(root)
    expect(root.querySelector<HTMLElement>('.card-soft')!.style.opacity).toBe('')
    stop()
  })

  it('без IntersectionObserver ничего не прячет', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const root = page('<div class="card-soft">Карточка</div>')
    installAutoReveal(root)()
    expect(root.querySelector<HTMLElement>('.card-soft')!.style.opacity).toBe('')
  })

  it('проявляет видимые карточки одной лесенкой, вложенные отдельно не трогает', async () => {
    const fromTo = vi.spyOn(gsap, 'fromTo').mockReturnValue({} as gsap.core.Tween)
    const root = page(`
      <div class="card-soft" id="a"><div class="v-card" id="nested"></div></div>
      <div data-reveal id="b"></div>
      <div data-no-reveal><div class="card-soft" id="skip-inner"></div></div>
      <div class="card-soft" data-no-reveal id="skip"></div>
      <p>Текст</p>
    `)
    const stop = installAutoReveal(root)
    expect(root.querySelector('#a')!.getAttribute('data-revealed')).toBe('1')
    expect(root.querySelector('#nested')!.hasAttribute('data-revealed')).toBe(false)
    expect(root.querySelector('#skip')!.hasAttribute('data-revealed')).toBe(false)
    expect(root.querySelector('#skip-inner')!.hasAttribute('data-revealed')).toBe(false)
    await tick()
    const animated = fromTo.mock.calls.flatMap(([targets]) => targets as HTMLElement[])
    expect(animated.map((el) => el.id).sort()).toEqual(['a', 'b'])
    stop()
  })

  it('подхватывает блоки, которые появились позже', async () => {
    vi.spyOn(gsap, 'fromTo').mockReturnValue({} as gsap.core.Tween)
    const root = page('')
    const stop = installAutoReveal(root)
    const card = document.createElement('div')
    card.className = 'v-card'
    root.appendChild(card)
    await tick()
    expect(card.dataset.revealed).toBe('1')
    stop()
  })

  it('пока механизм включён, списки не анимируются дважды', () => {
    const fromTo = vi.spyOn(gsap, 'fromTo').mockReturnValue({} as gsap.core.Tween)
    vi.stubGlobal('IntersectionObserver', SilentObserver)
    const root = page('<div data-stagger></div>')
    const stop = installAutoReveal(root)
    staggerIn(root)
    expect(fromTo).not.toHaveBeenCalled()
    stop()
  })

  it('при снятии не оставляет невидимых блоков', () => {
    vi.stubGlobal('IntersectionObserver', SilentObserver)
    const root = page('<div class="card-soft"></div>')
    const stop = installAutoReveal(root)
    const card = root.querySelector<HTMLElement>('.card-soft')!
    expect(card.style.opacity).toBe('0')
    stop()
    expect(card.style.opacity).toBe('')
  })
})
