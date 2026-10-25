import { describe, expect, it, vi } from 'vitest'
import { click, getButton, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import AppFab from './AppFab.vue'

function fab(): HTMLElement {
  return document.querySelector('#fab-layer .fab') as HTMLElement
}

async function scrollTo(y: number): Promise<void> {
  vi.stubGlobal('scrollY', y)
  window.dispatchEvent(new Event('scroll'))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

describe('Плавающая кнопка «создать»', () => {
  it('рисуется в отдельном слое над страницей и ведёт куда сказано', async () => {
    const { router } = await renderComponent(AppFab, {
      props: { icon: 'mdi-plus', label: 'Новая заявка', to: '/issues/new' },
    })
    await waitFor(() => fab())
    expect(fab().closest('#fab-layer')).not.toBeNull()
    expect(fab().getAttribute('aria-label')).toBe('Новая заявка')
    expect(fab().querySelector('.mdi-plus')).not.toBeNull()

    await click(getButton('Новая заявка'))
    await waitFor(() => router.currentRoute.value.path === '/issues/new')
  })

  it('своя подпись для диктора, если на кнопке короткий текст', async () => {
    await renderComponent(AppFab, {
      props: { icon: 'mdi-plus', label: 'Создать', ariaLabel: 'Создать объявление' },
    })
    await waitFor(() => fab())
    expect(fab().getAttribute('aria-label')).toBe('Создать объявление')
  })

  it('при прокрутке вниз сворачивается в круг, при прокрутке вверх разворачивается', async () => {
    vi.stubGlobal('scrollY', 0)
    await renderComponent(AppFab, { props: { icon: 'mdi-plus', label: 'Новая заявка' } })
    await waitFor(() => fab())

    await scrollTo(300)
    await waitFor(() => fab().classList.contains('fab--compact'))

    // мелкое дрожание пальца ничего не меняет
    await scrollTo(295)
    expect(fab().classList.contains('fab--compact')).toBe(true)

    await scrollTo(200)
    await waitFor(() => !fab().classList.contains('fab--compact'))

    // у самого верха подпись видна всегда
    await scrollTo(250)
    await scrollTo(40)
    expect(fab().classList.contains('fab--compact')).toBe(false)
  })
})
