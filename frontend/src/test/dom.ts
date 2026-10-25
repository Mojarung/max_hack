/**
 * Поиск по тому, что видит житель: текст, подписи кнопок и полей. Ищем во всём document.body,
 * потому что диалоги, шторки и тосты Vuetify рисуются вне корня приложения.
 */
import { DOMWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'

export type TextMatch = string | RegExp

/** Текст без лишних пробелов и переносов. */
export function textOf(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim()
}

function matches(value: string, match: TextMatch): boolean {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return typeof match === 'string' ? normalized.includes(match) : match.test(normalized)
}

function describe(match: TextMatch): string {
  return typeof match === 'string' ? `«${match}»` : String(match)
}

/** Элемент скрыт, если он или предок помечен hidden / aria-hidden / display:none через стиль. */
function isHidden(el: Element): boolean {
  for (let node: Element | null = el; node; node = node.parentElement) {
    if (node instanceof HTMLElement) {
      if (node.hidden || node.style.display === 'none') return true
    }
  }
  return false
}

/** Самые глубокие элементы, текст которых содержит искомое. */
export function queryAllByText(match: TextMatch, root: ParentNode = document.body): HTMLElement[] {
  const all = Array.from(root.querySelectorAll<HTMLElement>('*')).filter(
    (el) => !['SCRIPT', 'STYLE'].includes(el.tagName) && matches(el.textContent ?? '', match),
  )
  return all.filter((el) => !all.some((other) => other !== el && el.contains(other)))
}

export function queryByText(match: TextMatch, root?: ParentNode): HTMLElement | null {
  return queryAllByText(match, root)[0] ?? null
}

export function getByText(match: TextMatch, root?: ParentNode): HTMLElement {
  const found = queryByText(match, root)
  if (!found) {
    const snippet = textOf(root instanceof Element ? root : document.body).slice(0, 600)
    throw new Error(`Не нашли текст ${describe(match)}. На экране: ${snippet}`)
  }
  return found
}

const CLICKABLE = 'button, a, [role="button"], [role="tab"], [role="link"], .v-btn, .v-chip'

/** Имя кнопки, как его прочтёт диктор: aria-label или видимый текст. */
export function accessibleName(el: Element): string {
  const label = el.getAttribute('aria-label')
  if (label) return label
  const labelledBy = el.getAttribute('aria-labelledby')
  if (labelledBy) {
    const names = labelledBy.split(/\s+/).map((id) => textOf(document.getElementById(id)))
    if (names.some(Boolean)) return names.join(' ')
  }
  return textOf(el) || el.getAttribute('title') || ''
}

export function queryAllButtons(match: TextMatch, root: ParentNode = document.body): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(CLICKABLE)).filter(
    (el) => !isHidden(el) && matches(accessibleName(el), match),
  )
}

export function queryButton(match: TextMatch, root?: ParentNode): HTMLElement | null {
  const list = queryAllButtons(match, root)
  // точное совпадение важнее частичного: «Иду» не должен найти «Не иду»
  const exact = list.find((el) =>
    typeof match === 'string' ? accessibleName(el).replace(/\s+/g, ' ').trim() === match : false,
  )
  return exact ?? list[0] ?? null
}

export function getButton(match: TextMatch, root?: ParentNode): HTMLElement {
  const found = queryButton(match, root)
  if (!found) {
    const names = Array.from((root ?? document.body).querySelectorAll(CLICKABLE))
      .map(accessibleName)
      .filter(Boolean)
      .slice(0, 40)
    throw new Error(`Не нашли кнопку ${describe(match)}. Есть: ${names.join(' | ')}`)
  }
  return found
}

/** Поле ввода по подписи (label Vuetify), aria-label или placeholder. */
export function queryField(
  match: TextMatch,
  root: ParentNode = document.body,
): HTMLInputElement | HTMLTextAreaElement | null {
  const fields = Array.from(
    root.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea'),
  )
  for (const field of fields) {
    const own = [field.getAttribute('aria-label'), field.getAttribute('placeholder')]
    if (own.some((v) => v && matches(v, match))) return field
    if (field.id) {
      const label = document.querySelector(`label[for="${field.id}"]`)
      if (label && matches(textOf(label), match)) return field
    }
    const wrapper = field.closest('.v-input, .v-field')
    const label = wrapper?.querySelector('.v-label')
    if (label && matches(textOf(label), match)) return field
  }
  return null
}

export function getField(
  match: TextMatch,
  root?: ParentNode,
): HTMLInputElement | HTMLTextAreaElement {
  const found = queryField(match, root)
  if (!found) throw new Error(`Не нашли поле ${describe(match)}`)
  return found
}

/** Дать отработать промисам, таймерам с нулевой задержкой и перерисовке Vue. */
export async function settle(rounds = 3): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await nextTick()
  }
}

/** Ждём, пока проверка перестанет падать (ответ мока, перерисовка, переход роутера). */
export async function waitFor<T>(check: () => T, timeoutMs = 2000): Promise<T> {
  const started = performance.now()
  let lastError: unknown = null
  for (;;) {
    try {
      const value = check()
      if (value !== false && value !== null && value !== undefined) return value
      lastError = new Error('waitFor: условие не выполнилось')
    } catch (error) {
      lastError = error
    }
    if (performance.now() - started > timeoutMs) throw lastError
    await new Promise((resolve) => setTimeout(resolve, 5))
    await nextTick()
  }
}

export async function click(target: Element | TextMatch, root?: ParentNode): Promise<void> {
  const el = target instanceof Element ? target : getButton(target, root)
  await new DOMWrapper(el).trigger('click')
  await settle()
}

export async function type(
  target: HTMLInputElement | HTMLTextAreaElement | TextMatch,
  value: string,
): Promise<void> {
  const el = typeof target === 'string' || target instanceof RegExp ? getField(target) : target
  await new DOMWrapper(el).setValue(value)
  await settle()
}

/** Касание пальцем: touchstart в одной точке, touchend в другой. */
export async function swipe(
  el: Element,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  const touch = (x: number, y: number) => ({ clientX: x, clientY: y, identifier: 0, target: el })
  el.dispatchEvent(
    Object.assign(new Event('touchstart', { bubbles: true }), {
      touches: [touch(from.x, from.y)],
      changedTouches: [touch(from.x, from.y)],
    }),
  )
  el.dispatchEvent(
    Object.assign(new Event('touchend', { bubbles: true }), {
      touches: [],
      changedTouches: [touch(to.x, to.y)],
    }),
  )
  await settle()
}
