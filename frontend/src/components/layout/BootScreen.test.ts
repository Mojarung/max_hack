import { describe, expect, it, vi } from 'vitest'
import { startBrowserDemo } from '@/api/mode'
import { useSessionStore } from '@/stores/session'
import { click, getButton, getByText, queryByText, settle, waitFor } from '@/test/dom'
import { renderComponent, useScenario } from '@/test/harness'
import { defineComponent, h } from 'vue'
import { Toaster } from '@/components/ui/sonner'
import BootScreen from './BootScreen.vue'

/** Компонент вместе с тостами: так видно, что житель прочтёт после действия. */
const WithToasts = defineComponent({
  inheritAttrs: false,
  setup:
    (_, { attrs }) =>
    () => [h(BootScreen, attrs), h(Toaster)],
})

// Настоящее включение демо перезагружает страницу: в тесте проверяем только, что его попросили
vi.mock('@/api/mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/mode')>()),
  startBrowserDemo: vi.fn(() => true),
}))

describe('Загрузочный экран', () => {
  it('пока загружаемся, Кузя «открывает дверь»', async () => {
    await renderComponent(WithToasts)
    expect(getByText('Кузя открывает дверь...').getAttribute('role')).toBe('status')
  })

  it('при ошибке объясняет, что случилось, и даёт попробовать ещё раз', async () => {
    useScenario({ name: 'boot-error' })
    await renderComponent(WithToasts)
    const session = useSessionStore()
    await session.init()
    await settle()
    expect(getByText('Кузя не смог открыть дверь')).toBeTruthy()
    expect(getByText('Нет связи с сервером. Проверьте интернет').getAttribute('role')).toBe('alert')

    // связь вернулась: повторная попытка пускает в приложение
    useScenario({})
    await click('Попробовать ещё раз')
    await waitFor(() => session.status === 'ready')
  })

  it('вне MAX ведёт в чат с Кузей по диплинку бота', async () => {
    await renderComponent(WithToasts)
    const session = useSessionStore()
    session.status = 'outside'
    session.botUsername = 'domovoy_kuzya_bot'
    await settle()
    expect(getByText('Кузя живёт в MAX')).toBeTruthy()
    const link = getButton('Открыть в MAX')
    expect(link.getAttribute('href')).toBe('https://max.ru/domovoy_kuzya_bot?startapp=home')
    expect(link.getAttribute('target')).toBe('_blank')
  })

  it('без ника бота ссылка ведёт просто в MAX', async () => {
    await renderComponent(WithToasts)
    useSessionStore().status = 'outside'
    await settle()
    expect(getButton('Открыть в MAX').getAttribute('href')).toBe('https://max.ru')
  })

  it('по кнопке демо включает демо в браузере', async () => {
    await renderComponent(WithToasts)
    useSessionStore().status = 'outside'
    await settle()
    await click('Посмотреть демо в браузере')
    expect(startBrowserDemo).toHaveBeenCalled()
    expect(queryByText('Браузер не дал включить демо')).toBeNull()
  })

  it('если браузер запретил хранилище, предупреждает, что демо не включится', async () => {
    vi.mocked(startBrowserDemo).mockReturnValueOnce(false)
    await renderComponent(WithToasts)
    useSessionStore().status = 'outside'
    await settle()
    await click('Посмотреть демо в браузере')
    await waitFor(() => getByText('Браузер не дал включить демо'))
  })
})
