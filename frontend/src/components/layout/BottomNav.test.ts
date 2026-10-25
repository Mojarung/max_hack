import { describe, expect, it } from 'vitest'
import { click, getByText, settle, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import { usePulseStore } from '@/stores/pulse'
import BottomNav from './BottomNav.vue'

function nav(): HTMLElement {
  return document.querySelector<HTMLElement>('nav[aria-label="Разделы"]')!
}

function tab(title: string): HTMLAnchorElement {
  const link = Array.from(nav().querySelectorAll<HTMLAnchorElement>('a')).find((a) =>
    a.textContent?.includes(title),
  )
  if (!link) throw new Error(`Нет вкладки «${title}»`)
  return link
}

describe('Нижнее меню', () => {
  it('показывает пять разделов и отмечает текущий', async () => {
    await renderComponent(BottomNav, { session: true, path: '/' })
    const titles = Array.from(nav().querySelectorAll('.bottom-nav__label')).map((el) =>
      el.textContent?.trim(),
    )
    expect(titles).toEqual(['Дом', 'Заявки', 'Вещи', 'События', 'Ещё'])
    expect(tab('Дом').getAttribute('aria-current')).toBe('page')
    expect(tab('Заявки').getAttribute('aria-current')).toBeNull()
  })

  it('на «Заявках» цифра: сколько заявок ждут голоса жителя', async () => {
    await renderComponent(BottomNav, { session: true, path: '/' })
    // в фикстурах житель ещё не поддержал только «Течёт крыша над 9 этажом»
    const badge = await waitFor(() => nav().querySelector('[aria-label="Ждут вашего голоса: 1"]'))
    expect(badge!.textContent).toContain('1')
  })

  it('больше 99 заявок пишет как «99+»', async () => {
    await renderComponent(BottomNav, { session: true, path: '/' })
    const pulse = usePulseStore()
    pulse.pulse = { ...pulse.pulse!, stats: { ...pulse.pulse!.stats, awaiting_my_vote: 120 } }
    await settle()
    expect(getByText('99+')).toBeTruthy()
  })

  it('без заявок, ждущих голоса, цифры нет', async () => {
    await renderComponent(BottomNav, { session: true, path: '/', scenario: { name: 'empty' } })
    expect(nav().querySelector('[aria-label^="Ждут вашего голоса"]')).toBeNull()
  })

  it('нажатие на раздел открывает его и даёт лёгкий отклик', async () => {
    const { max, router } = await renderComponent(BottomNav, { session: true, path: '/' })
    await click(tab('События'))
    await waitFor(() => router.currentRoute.value.path === '/events')
    expect(max.selection).toHaveBeenCalled()
    await waitFor(() => tab('События').getAttribute('aria-current') === 'page')
  })

  it('на внутреннем экране меню прячется и недоступно для фокуса', async () => {
    await renderComponent(BottomNav, { session: true, path: '/issues/new' })
    expect(nav().classList.contains('bottom-nav--hidden')).toBe(true)
    expect(nav().hasAttribute('inert')).toBe(true)
    expect(tab('Заявки').getAttribute('aria-current')).toBe('page')
  })
})
