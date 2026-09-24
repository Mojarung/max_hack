/**
 * Объективные проверки экрана для агента и разработчика (только мок-режим).
 * В консоли браузера:
 *   await __ui.audit()   тач-зоны, мелкий текст, горизонтальный скролл, обрезанный текст + axe
 *   await __ui.axe()     только axe-core (WCAG 2.1 AA)
 */

interface Finding {
  rule: string
  target: string
  detail: string
}

const MIN_TAP = 44
const MIN_FONT = 14

function describe(el: Element): string {
  const text = (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().replace(/\s+/g, ' ')
  const cls = [...el.classList].slice(0, 2).join('.')
  return `${el.tagName.toLowerCase()}${cls ? `.${cls}` : ''}${text ? ` «${text.slice(0, 40)}»` : ''}`
}

function visible(el: Element): boolean {
  const r = el.getBoundingClientRect()
  const s = getComputedStyle(el)
  return (
    r.width > 0 &&
    r.height > 0 &&
    s.visibility !== 'hidden' &&
    s.display !== 'none' &&
    Number(s.opacity) > 0
  )
}

function layoutChecks(): Finding[] {
  const out: Finding[] = []
  const vw = document.documentElement.clientWidth
  if (document.documentElement.scrollWidth > vw + 1) {
    out.push({
      rule: 'horizontal-scroll',
      target: 'document',
      detail: `ширина ${document.documentElement.scrollWidth}px > ${vw}px`,
    })
  }

  const interactive = document.querySelectorAll<HTMLElement>(
    'a[href], button, [role="button"], [role="tab"], input:not([type="hidden"]), select, textarea, .v-chip--link',
  )
  for (const el of interactive) {
    if (!visible(el) || el.closest('[aria-hidden="true"]')) continue
    // Поле ввода Vuetify кликабельно целиком: меряем обёртку
    const box = (el.closest('.v-field') ?? el).getBoundingClientRect()
    if (box.height < MIN_TAP - 4 || box.width < MIN_TAP - 4) {
      out.push({
        rule: 'tap-target',
        target: describe(el),
        detail: `${Math.round(box.width)}×${Math.round(box.height)}px < ${MIN_TAP}px`,
      })
    }
  }

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  const seen = new Set<Element>()
  while (walker.nextNode()) {
    const node = walker.currentNode
    const el = node.parentElement
    if (!el || seen.has(el) || !node.textContent?.trim() || !visible(el)) continue
    seen.add(el)
    if (el.closest('.sr-only, [aria-hidden="true"], svg')) continue
    const size = parseFloat(getComputedStyle(el).fontSize)
    if (size < MIN_FONT)
      out.push({ rule: 'small-text', target: describe(el), detail: `${size}px < ${MIN_FONT}px` })
    if (
      el.scrollWidth > el.clientWidth + 1 &&
      getComputedStyle(el).overflow === 'visible' &&
      el.clientWidth > 0
    ) {
      out.push({
        rule: 'text-overflow',
        target: describe(el),
        detail: `текст ${el.scrollWidth}px не влезает в ${el.clientWidth}px`,
      })
    }
  }
  return out
}

async function axe(): Promise<Finding[]> {
  const { default: axeCore } = await import('axe-core')
  const result = await axeCore.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
  })
  return result.violations.flatMap((v) =>
    v.nodes.slice(0, 5).map((n) => ({
      rule: `axe:${v.id}`,
      target: String(n.target[0] ?? ''),
      detail: n.failureSummary?.split('\n').slice(1).join(' ').trim() || v.help,
    })),
  )
}

async function audit(): Promise<{ ok: boolean; count: number; findings: Finding[] }> {
  const findings = [...layoutChecks(), ...(await axe())]
  return { ok: findings.length === 0, count: findings.length, findings }
}

export function installAudit(): void {
  ;(window as unknown as { __ui: object }).__ui = { audit, axe, layout: layoutChecks }
}
