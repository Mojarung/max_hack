/**
 * Общая подготовка jsdom для всех тестов: заглушки браузерных API, без которых
 * Vuetify, GSAP и экраны падают или пишут «not implemented» в консоль.
 * Мок-бэкенд и монтирование экранов - в `src/test/harness.ts`.
 */

// Мок-бэкенд без задержки ответов и без анимаций (читается при загрузке src/mock/scenario.ts)
try {
  sessionStorage.setItem('kuzya.mockScenario', JSON.stringify({ latency: 0, motion: false }))
} catch {
  // хранилище недоступно: сценарий возьмёт значения по умолчанию
}
document.documentElement.dataset.motion = 'off'

class FakeResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

/** Наблюдатель, который сразу считает элемент видимым: так ленивые блоки отрисуются. */
class FakeIntersectionObserver {
  readonly root = null
  readonly rootMargin = '0px'
  readonly thresholds = [0]
  private readonly callback: IntersectionObserverCallback

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
  }

  observe(target: Element): void {
    const entry = {
      target,
      isIntersecting: true,
      intersectionRatio: 1,
      boundingClientRect: target.getBoundingClientRect(),
      intersectionRect: target.getBoundingClientRect(),
      rootBounds: null,
      time: 0,
    } as IntersectionObserverEntry
    queueMicrotask(() => this.callback([entry], this as unknown as IntersectionObserver))
  }

  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

function define(target: object, key: string, value: unknown): void {
  Object.defineProperty(target, key, { configurable: true, writable: true, value })
}

if (!window.matchMedia) {
  define(window, 'matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }))
}
if (!('ResizeObserver' in window)) define(window, 'ResizeObserver', FakeResizeObserver)
if (!('IntersectionObserver' in window))
  define(window, 'IntersectionObserver', FakeIntersectionObserver)
define(window, 'scrollTo', () => undefined)
define(Element.prototype, 'scrollTo', function scrollTo(this: Element) {})
define(Element.prototype, 'scrollIntoView', function scrollIntoView(this: Element) {})
if (!('CSS' in window)) define(window, 'CSS', {})
if (typeof window.CSS.supports !== 'function') define(window.CSS, 'supports', () => false)
if (!window.visualViewport) {
  define(window, 'visualViewport', {
    width: 390,
    height: 844,
    offsetTop: 0,
    offsetLeft: 0,
    scale: 1,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })
}
define(window, 'scrollBy', () => undefined)
define(HTMLCanvasElement.prototype, 'getContext', () => null)
// createObjectURL из Node не принимает Blob и File из jsdom: подменяем всегда
let blobSeq = 0
define(URL, 'createObjectURL', () => `blob:test/${++blobSeq}`)
define(URL, 'revokeObjectURL', () => undefined)
if (!Element.prototype.animate) {
  define(Element.prototype, 'animate', function animate(this: Element) {
    return {
      finished: Promise.resolve(),
      cancel: () => undefined,
      finish: () => undefined,
      play: () => undefined,
      pause: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      onfinish: null,
    }
  })
}
