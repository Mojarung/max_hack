import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { Toaster } from '@/components/ui/sonner'
import { SHELTERS } from '@/mock/fixtures'
import { useAlertsStore } from '@/stores/alerts'
import { click, getButton, getByText, queryButton, queryByText, settle, waitFor } from '@/test/dom'
import { renderComponent, useScenario, type RenderOptions } from '@/test/harness'
import DroneAlertOverlay from './DroneAlertOverlay.vue'
import { ALERT_INSTRUCTIONS } from './instructions'

/** Экран тревоги вместе с тостами: так видно подсказки после нажатий. */
const WithToasts = defineComponent({
  setup: () => () => [h(DroneAlertOverlay), h(Toaster)],
})

function dialog(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[role="alertdialog"]')
}

async function renderAlert(options: RenderOptions = {}) {
  const rendered = await renderComponent(WithToasts, {
    session: true,
    ...options,
    scenario: { name: 'alert', ...options.scenario },
  })
  await waitFor(() => getByText('Укрытие в подвале школы (демо)'))
  return rendered
}

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
})

describe('Экран тревоги', () => {
  it('занимает весь экран: что случилось, с какого времени и что делать', async () => {
    await renderAlert()
    const panel = dialog()!
    expect(panel.getAttribute('aria-modal')).toBe('true')
    expect(getByText('Беспилотная опасность', panel)).toBeTruthy()
    // тревога началась за 3 минуты до «сейчас» (10:00)
    expect(getByText('Внимание! С 09:57', panel)).toBeTruthy()
    expect(
      getByText('Внимание! Угроза атаки беспилотников. Отойдите от окон, пройдите в укрытие.'),
    ).toBeTruthy()
    for (const step of ALERT_INSTRUCTIONS) expect(getByText(step.text, panel)).toBeTruthy()
    expect(document.activeElement).toBe(panel)
  })

  it('показывает ближайшее укрытие из реестра с расстоянием', async () => {
    await renderAlert()
    expect(getByText('Подвал · пр-т Ленинского Комсомола, 9 · 180 м')).toBeTruthy()
    expect(getByText('Из реестра укрытий')).toBeTruthy()
  })

  it('для укрытия не из реестра называет источник', async () => {
    await renderAlert()
    useAlertsStore().nearest = SHELTERS[2]!
    await settle()
    expect(getByText('По данным: OpenStreetMap')).toBeTruthy()
  })

  it('пока ищет укрытие, так и пишет, а маршрут недоступен', async () => {
    await renderAlert()
    const alerts = useAlertsStore()
    alerts.nearest = null
    alerts.nearestLoading = true
    await settle()
    expect(getByText('Ищем укрытие рядом с вами...')).toBeTruthy()
    expect(getButton('Маршрут').hasAttribute('disabled')).toBe(true)
  })

  it('если укрытий нет, советует подвал и даёт поискать снова', async () => {
    await renderAlert()
    const alerts = useAlertsStore()
    alerts.nearest = null
    await settle()
    expect(getByText(/Рядом не нашлось укрытий в реестре и на карте/)).toBeTruthy()
    expect(getButton('Маршрут до укрытия в Яндекс Картах').hasAttribute('disabled')).toBe(true)
    await click('Повторить')
    await waitFor(() => getByText('Укрытие в подвале школы (демо)'))
  })

  it('«Маршрут» сворачивает тревогу и открывает укрытие на карте приложения', async () => {
    const { router } = await renderAlert()
    await click('Маршрут')
    await waitFor(() => router.currentRoute.value.fullPath === '/more/safety?shelter=1')
    expect(dialog()).toBeNull()
    expect(getButton(/Тревога: Беспилотная опасность/).textContent).toContain('Развернуть')
  })

  it('кнопка Яндекс Карт открывает маршрут через MAX и предупреждает, что карта грузится', async () => {
    const { max } = await renderAlert()
    await click('Маршрут до укрытия в Яндекс Картах')
    expect(max.openLink).toHaveBeenCalledWith(SHELTERS[0]!.yandex_url)
    await waitFor(() => getByText('Открываю Яндекс Карты с маршрутом...'))
  })

  it('свёрнутую тревогу можно развернуть обратно', async () => {
    await renderAlert()
    await click('Свернуть')
    expect(dialog()).toBeNull()
    await click(getButton(/Тревога: Беспилотная опасность/))
    await waitFor(() => dialog())
  })

  it('обычный житель в MAX отбой дать не может', async () => {
    await renderAlert()
    expect(queryButton('Отбой')).toBeNull()
  })

  it('администратор даёт отбой: экран тревоги уходит, соседям приходит «Отбой тревоги»', async () => {
    await renderAlert({ scenario: { role: 'admin' } })
    await click('Отбой')
    await waitFor(() => getByText('Отбой тревоги'))
    expect(getByText('Опасность миновала. Можно возвращаться домой')).toBeTruthy()
    expect(dialog()).toBeNull()
    expect(useAlertsStore().active).toBeNull()
  })

  it('если отбой не прошёл, говорит об этом и оставляет тревогу', async () => {
    await renderAlert({ scenario: { role: 'admin' } })
    useScenario({ name: 'error', role: 'admin' })
    await click('Отбой')
    await waitFor(() => getByText('Не удалось дать отбой'))
    expect(dialog()).not.toBeNull()
  })

  it('без текста от сервера даёт диктору короткое описание', async () => {
    await renderAlert()
    const alerts = useAlertsStore()
    alerts.active = { ...alerts.active!, message: '', kind_title: '' }
    await settle()
    expect(getByText('Инструкция на случай беспилотной опасности').className).toContain('sr-only')
    // без названия от сервера заголовок по умолчанию
    expect(getByText('Беспилотная опасность', dialog()!)).toBeTruthy()
  })

  it('с анимациями экран тоже появляется и прячется без ошибок', async () => {
    delete document.documentElement.dataset.motion
    await renderAlert()
    expect(dialog()).not.toBeNull()
    await click('Свернуть')
    expect(dialog()).toBeNull()
    expect(queryByText('Ищем укрытие рядом с вами...')).toBeNull()
  })
})
