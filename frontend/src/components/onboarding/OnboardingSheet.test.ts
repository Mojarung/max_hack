import { describe, expect, it } from 'vitest'
import { useSessionStore } from '@/stores/session'
import { click, getButton, getByText, queryByText, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import OnboardingSheet from './OnboardingSheet.vue'

/** vaul не дожидается конца анимации в jsdom: закрытую шторку видно по data-state. */
function sheetState(): string | null {
  return document.querySelector('[role="dialog"]')?.getAttribute('data-state') ?? null
}

async function renderSheet(scenario: Record<string, unknown> = {}) {
  const rendered = await renderComponent(OnboardingSheet, {
    session: true,
    scenario: { onboarding: true, ...scenario },
  })
  await waitFor(() => sheetState() === 'open')
  return rendered
}

async function next(times = 1): Promise<void> {
  for (let i = 0; i < times; i++) await click('Дальше')
}

describe('Обучалка первого входа', () => {
  it('открывается сама, пока житель её не прошёл, и знакомит с Кузей', async () => {
    await renderSheet()
    expect(getByText('Привет! Я Кузя, домовой дома «Ленинского Комсомола, 5»')).toBeTruthy()
    expect(getByText('Шаг 1 из 4')).toBeTruthy()
    expect(getButton('Дальше')).toBeTruthy()
    expect(getButton('Пропустить')).toBeTruthy()
  })

  it('не открывается у жителя, который уже прошёл её', async () => {
    await renderComponent(OnboardingSheet, { session: true })
    expect(queryByText(/Привет! Я Кузя/)).toBeNull()
  })

  it('листается по шагам с лёгким откликом и рассказывает про заявки', async () => {
    const { max } = await renderSheet()
    await next()
    expect(getByText('Что-то сломалось? Напишите мне')).toBeTruthy()
    expect(getByText('Я отправляю обращение и слежу за сроком')).toBeTruthy()
    expect(getByText('Шаг 2 из 4')).toBeTruthy()
    expect(max.selection).toHaveBeenCalled()
    await next()
    expect(getByText('Всё о доме в одном месте')).toBeTruthy()
    expect(getByText('Укрытия рядом на случай тревоги')).toBeTruthy()
  })

  it('на последнем шаге «Понятно, начать» просто закрывает обучалку', async () => {
    const { router } = await renderSheet()
    await next(3)
    expect(getByText('Зовите меня в чате дома')).toBeTruthy()
    await click('Понятно, начать')
    await waitFor(() => sheetState() === 'closed')
    expect(useSessionStore().me?.user.onboarded).toBe(true)
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('на последнем шаге можно сразу сообщить о проблеме', async () => {
    const { router } = await renderSheet()
    await next(3)
    await click('Сообщить о проблеме')
    await waitFor(() => router.currentRoute.value.path === '/issues/new')
    expect(useSessionStore().me?.user.onboarded).toBe(true)
  })

  it('«Пропустить» закрывает обучалку и запоминает это на сервере', async () => {
    const { router } = await renderSheet()
    await click('Пропустить')
    await waitFor(() => sheetState() === 'closed')
    const session = useSessionStore()
    // после перезагрузки сессии обучалка не вернётся: мок тоже знает, что житель её прошёл
    await session.refreshMe()
    expect(session.needsOnboarding).toBe(false)
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('админу нового дома добавляет шаг про настройку и ведёт в настройки', async () => {
    const { router } = await renderSheet({ role: 'admin', setup: true })
    expect(getByText('Шаг 1 из 5')).toBeTruthy()
    await next(4)
    expect(getByText('Вы администратор дома')).toBeTruthy()
    await click('Настроить дом')
    await waitFor(() => router.currentRoute.value.path === '/more/house/edit')
  })

  it('админ может отложить настройку дома', async () => {
    const { router } = await renderSheet({ role: 'admin', setup: true })
    await next(4)
    await click('Настрою позже')
    await waitFor(() => sheetState() === 'closed')
    expect(router.currentRoute.value.path).toBe('/')
  })
})
