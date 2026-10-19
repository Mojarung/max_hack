import { gsap } from 'gsap'
import { nextTick, onMounted, watch, type Ref, type WatchSource } from 'vue'
import { autoRevealActive } from './useReveal'

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  // мок-режим выключает анимации (?motion=0), чтобы скриншоты были стабильными
  if (document.documentElement.dataset.motion === 'off') return true
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/** Появление новых элементов списка «лесенкой». Уже показанные не трогаем. */
export function staggerIn(container: HTMLElement | null, selector = '[data-stagger]'): void {
  if (!container) return
  const fresh = Array.from(container.querySelectorAll<HTMLElement>(selector)).filter(
    (el) => !el.dataset.shown,
  )
  if (fresh.length === 0) return
  fresh.forEach((el) => (el.dataset.shown = '1'))
  // карточки списков проявляет общий механизм при входе в экран (useReveal)
  if (prefersReducedMotion() || (autoRevealActive && selector === '[data-stagger]')) return
  gsap.fromTo(
    fresh,
    { opacity: 0, y: 18, scale: 0.98 },
    {
      opacity: 1,
      y: 0,
      scale: 1,
      duration: 0.42,
      ease: 'power2.out',
      stagger: 0.05,
      clearProps: 'transform,opacity',
    },
  )
}

export function useStagger(container: Ref<HTMLElement | null>, source: WatchSource): void {
  const run = () => nextTick(() => staggerIn(container.value))
  onMounted(run)
  watch(source, run, { flush: 'post' })
}

/**
 * Как сменился экран: вглубь (push), назад (pop) или между вкладками (tab).
 * Ставит роутер перед каждым переходом, читают pageEnter/pageLeave.
 */
export type NavDirection = 'push' | 'pop' | 'tab'
let navDirection: NavDirection = 'tab'
export function setNavDirection(direction: NavDirection): void {
  navDirection = direction
}

/**
 * Переход между страницами как в iOS: внутренний экран въезжает справа, при возврате
 * предыдущий появляется слева, вкладки сменяются мягким растворением.
 */
export function pageEnter(el: Element, done: () => void): void {
  // Без анимации переключаем сразу: переход не должен зависеть от кадров (фоновая вкладка их не рисует).
  // done() откладываем на микрозадачу: синхронный вызов посреди патча ломает <Transition mode="out-in">.
  if (prefersReducedMotion()) {
    gsap.set(el, { opacity: 1, clearProps: 'transform' })
    queueMicrotask(done)
    return
  }
  const from =
    navDirection === 'push'
      ? { opacity: 0, x: 48 }
      : navDirection === 'pop'
        ? { opacity: 0, x: -36 }
        : { opacity: 0, scale: 0.985 }
  gsap.fromTo(el, from, {
    opacity: 1,
    x: 0,
    scale: 1,
    duration: navDirection === 'tab' ? 0.24 : 0.34,
    ease: 'power3.out',
    clearProps: 'transform',
    onComplete: done,
  })
}

export function pageLeave(el: Element, done: () => void): void {
  if (prefersReducedMotion()) {
    queueMicrotask(done)
    return
  }
  const to =
    navDirection === 'push'
      ? { opacity: 0, x: -28 }
      : navDirection === 'pop'
        ? { opacity: 0, x: 40 }
        : { opacity: 0 }
  gsap.to(el, { ...to, duration: 0.12, ease: 'power2.in', onComplete: done })
}

/** Небольшой «пульс» элемента после успешного действия. */
export function pop(el: Element | null | undefined): void {
  if (!el || prefersReducedMotion()) return
  gsap.fromTo(el, { scale: 0.92 }, { scale: 1, duration: 0.5, ease: 'elastic.out(1, 0.45)' })
}

const CONFETTI_COLORS = ['#1F5FAF', '#0F766E', '#7B4FA0', '#1E7B45', '#F4C15D', '#7FB3F5']

/** Конфетти из центра контейнера. Элементы удаляются после анимации. */
export function confetti(container: HTMLElement | null, count = 42): void {
  if (!container || prefersReducedMotion()) return
  const rect = container.getBoundingClientRect()
  const pieces: HTMLElement[] = []
  for (let i = 0; i < count; i++) {
    const piece = document.createElement('span')
    piece.className = 'confetti-piece'
    piece.style.background = CONFETTI_COLORS[i % CONFETTI_COLORS.length]!
    piece.style.left = `${rect.width / 2}px`
    piece.style.top = `${rect.height / 3}px`
    if (i % 3 === 0) piece.style.borderRadius = '50%'
    container.appendChild(piece)
    pieces.push(piece)
  }
  gsap.to(pieces, {
    x: () => gsap.utils.random(-rect.width / 1.6, rect.width / 1.6),
    y: () => gsap.utils.random(-rect.height / 3, rect.height / 1.4),
    rotation: () => gsap.utils.random(-540, 540),
    opacity: 0,
    duration: () => gsap.utils.random(1.1, 1.9),
    ease: 'power2.out',
    onComplete: () => pieces.forEach((p) => p.remove()),
  })
}
