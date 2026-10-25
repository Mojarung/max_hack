import { describe, expect, it } from 'vitest'
import { click, getButton, getByText, queryByText, waitFor } from '@/test/dom'
import { renderApp } from '@/test/harness'

function nav(): HTMLElement | null {
  return document.querySelector<HTMLElement>('nav[aria-label="Разделы"]')
}

function main(): HTMLElement {
  return document.querySelector<HTMLElement>('main')!
}

/**
 * Недоступен ли блок для фокуса и диктора. В jsdom нет свойства inert, поэтому Vue пишет
 * атрибут строкой и для false оставляет inert="false"; в браузере это свойство, и атрибута нет.
 */
function isInert(el: Element): boolean {
  return el.hasAttribute('inert') && el.getAttribute('inert') !== 'false'
}

describe('Приложение целиком', () => {
  it('после загрузки показывает главный экран с меню разделов', async () => {
    const { max } = await renderApp('/')
    await waitFor(() => getByText('Нужны голоса'))
    expect(nav()?.textContent).toContain('Заявки')
    expect(document.querySelector('.app-header')?.textContent).toContain('Ленинского Комсомола, 5')
    // MAX узнаёт, что приложение готово, а системная кнопка «Назад» на главной не нужна
    expect(max.ready).toHaveBeenCalled()
    expect(max.backHide).toHaveBeenCalled()
  })

  it('если сервер недоступен, показывает экран ошибки вместо приложения', async () => {
    await renderApp('/', { scenario: { name: 'boot-error' } })
    expect(getByText('Кузя не смог открыть дверь')).toBeTruthy()
    expect(getByText('Нет связи с сервером. Проверьте интернет')).toBeTruthy()
    expect(getButton('Попробовать ещё раз')).toBeTruthy()
    expect(nav()).toBeNull()
  })

  it('открытое по ссылке из чата приложение сразу ведёт к заявке', async () => {
    const { router } = await renderApp('/', { max: { startParam: 'issue_101' } })
    await waitFor(() => router.currentRoute.value.path === '/issues/101')
    await waitFor(() => getByText('Течёт крыша над 9 этажом'))
  })

  it('ссылка на неизвестный раздел оставляет житель на главной', async () => {
    const { router } = await renderApp('/', { max: { startParam: 'hack_me' } })
    await waitFor(() => getByText('Нужны голоса'))
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('ссылка из чата не уводит с экрана, который житель уже открыл', async () => {
    const { router } = await renderApp('/events', { max: { startParam: 'issue_101' } })
    await waitFor(() => getByText('События двора'))
    expect(router.currentRoute.value.path).toBe('/events')
  })

  it('на внутреннем экране включает «Назад» MAX и прячет меню, кнопка возвращает обратно', async () => {
    const { router, max } = await renderApp('/more')
    await waitFor(() => getByText('Награды и рейтинг'))
    expect(document.documentElement.classList.contains('nav-hidden')).toBe(false)

    await router.push('/more/achievements')
    await waitFor(() => max.backShow.mock.calls.length > 0)
    expect(document.documentElement.classList.contains('nav-hidden')).toBe(true)
    expect(nav()?.classList.contains('bottom-nav--hidden')).toBe(true)

    max.backHide.mockClear()
    max.pressBack()
    await waitFor(() => router.currentRoute.value.path === '/more')
    await waitFor(() => max.backHide.mock.calls.length > 0)
    expect(document.documentElement.classList.contains('nav-hidden')).toBe(false)
  })

  it('кнопка «Назад» в шапке без истории ведёт в родительский раздел', async () => {
    const { router } = await renderApp('/more/achievements')
    // как при входе по диплинку: в истории вкладки нет предыдущего экрана
    window.history.replaceState({ ...window.history.state, back: null }, '')
    await click(getButton('Назад'))
    await waitFor(() => router.currentRoute.value.path === '/more')
  })

  it('во время тревоги поверх всего экран тревоги, а приложение под ним недоступно', async () => {
    await renderApp('/', { scenario: { name: 'alert' } })
    const dialog = await waitFor(() => document.querySelector('[role="alertdialog"]'))
    expect(dialog!.textContent).toContain('Беспилотная опасность')
    expect(isInert(main())).toBe(true)
    expect(isInert(document.querySelector('.app-header')!)).toBe(true)

    await click('Свернуть')
    expect(isInert(main())).toBe(false)
    expect(getButton(/Тревога: Беспилотная опасность/)).toBeTruthy()
  })

  it('новому жителю показывает обучалку', async () => {
    await renderApp('/', { scenario: { onboarding: true } })
    await waitFor(() => getByText('Привет! Я Кузя, домовой дома «Ленинского Комсомола, 5»'))
  })

  it('во время тревоги обучалка не мешает', async () => {
    await renderApp('/', { scenario: { onboarding: true, name: 'alert' } })
    await waitFor(() => document.querySelector('[role="alertdialog"]'))
    expect(queryByText(/Привет! Я Кузя/)).toBeNull()
  })

  it('эмулятор чата рисует свою шапку: без меню и шапки приложения', async () => {
    await renderApp('/dev/chat', { scenario: { inMax: false } })
    expect(document.querySelector('.app-header')).toBeNull()
    expect(nav()).toBeNull()
  })
})
