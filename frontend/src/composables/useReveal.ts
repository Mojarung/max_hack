import { gsap } from 'gsap'
import { prefersReducedMotion } from './useMotion'

/**
 * Анимация появления блоков при прокрутке для всего приложения.
 *
 * Подключается один раз к <main>: следит за карточками и блоками (в том числе
 * подгруженными позже) и проявляет их лесенкой, когда они входят в экран. Карточки
 * списков (data-stagger) тоже идут через этот механизм, поэтому то, что ниже экрана,
 * анимируется при прокрутке, а не впустую при загрузке. Вложенные цели не
 * анимируются отдельно от родителя, чтобы не было «двойного» движения.
 */
const TARGETS = '[data-stagger], .card-soft, .v-card, [data-reveal]'
const SKIP = '[data-no-reveal]'

/** Включён ли общий механизм: тогда staggerIn не анимирует сам. */
export let autoRevealActive = false
const ENTER_OFFSET_PX = 16
const BATCH_STAGGER = 0.06

export function installAutoReveal(root: HTMLElement): () => void {
  if (prefersReducedMotion() || typeof IntersectionObserver === 'undefined') return () => undefined

  autoRevealActive = true
  const pending = new Set<HTMLElement>()

  const io = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((e) => e.isIntersecting).map((e) => e.target as HTMLElement)
      if (visible.length === 0) return
      visible.forEach((el) => {
        io.unobserve(el)
        pending.delete(el)
      })
      gsap.fromTo(
        visible,
        { opacity: 0, y: ENTER_OFFSET_PX },
        {
          opacity: 1,
          y: 0,
          duration: 0.45,
          ease: 'power2.out',
          stagger: BATCH_STAGGER,
          clearProps: 'opacity,transform',
        },
      )
    },
    { rootMargin: '0px', threshold: 0.01 },
  )

  function isTarget(el: Element): el is HTMLElement {
    if (!(el instanceof HTMLElement) || !el.matches(TARGETS) || el.matches(SKIP)) return false
    if (el.dataset.revealed || el.closest(SKIP)) return false
    // родительская цель уже анимирует этот блок целиком
    const parentTarget = el.parentElement?.closest(TARGETS)
    return !parentTarget || !root.contains(parentTarget)
  }

  function register(el: HTMLElement): void {
    el.dataset.revealed = '1'
    el.style.opacity = '0'
    pending.add(el)
    io.observe(el)
  }

  function scan(node: Element): void {
    if (isTarget(node)) register(node)
    node.querySelectorAll(TARGETS).forEach((el) => {
      if (isTarget(el)) register(el)
    })
  }

  scan(root)
  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((n) => {
        if (n instanceof Element) scan(n)
      })
    }
  })
  mo.observe(root, { childList: true, subtree: true })

  return () => {
    autoRevealActive = false
    mo.disconnect()
    io.disconnect()
    // не оставляем невидимых блоков, если наблюдатель сняли раньше анимации
    pending.forEach((el) => (el.style.opacity = ''))
    pending.clear()
  }
}
