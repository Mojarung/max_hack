import { describe, expect, it } from 'vitest'
import { click, getButton, getByText, queryButton, queryByText, waitFor } from '@/test/dom'
import { renderRoute } from '@/test/harness'

describe('Экран «О доме»', () => {
  it('показывает адрес, число участников чата и информацию от администратора', async () => {
    await renderRoute('/more/house')
    expect(getByText('Ульяновск, пр-т Ленинского Комсомола, 5')).toBeTruthy()
    expect(getByText('40 участников чата дома')).toBeTruthy()
    expect(getByText(/Диспетчерская УК: \+7 \(8422\) 00-00-01/)).toBeTruthy()
  })

  it('называет управляющую компанию словами жителя и показывает телефон', async () => {
    await renderRoute('/more/house')
    expect(getByText('Управляющая компания «Уютный дом»')).toBeTruthy()
    expect(getByText('+7 (8422) 00-00-01')).toBeTruthy()
  })

  it('кнопка «Позвонить» открывает номер диспетчерской через MAX', async () => {
    const { max } = await renderRoute('/more/house')
    await click('Позвонить')
    expect(max.openLink).toHaveBeenCalledWith('tel:+78422000001')
  })

  it('кнопка «Написать на почту» открывает письмо в управляющую компанию', async () => {
    const { max } = await renderRoute('/more/house')
    await click('Написать на почту')
    expect(max.openLink).toHaveBeenCalledWith('mailto:uk@example.org')
  })

  it('житель не видит кнопку редактирования и пометку о тестовом режиме', async () => {
    await renderRoute('/more/house')
    expect(queryButton('Изменить данные дома')).toBeNull()
    expect(queryByText('Сейчас тестовый режим')).toBeNull()
  })

  it('администратор видит пометку о тестовом режиме и переходит в настройки дома', async () => {
    const { router } = await renderRoute('/more/house', { scenario: { role: 'admin' } })
    expect(getByText(/Сейчас тестовый режим: письма уходят на проверочный адрес/)).toBeTruthy()
    await click(getButton('Изменить данные дома'))
    await waitFor(() => router.currentRoute.value.path === '/more/house/edit')
  })

  it('дом без адреса и УК: подсказывает, что данных ещё нет, и не предлагает звонить', async () => {
    await renderRoute('/more/house', { scenario: { setup: true } })
    expect(getByText('Адрес ещё не указан')).toBeTruthy()
    expect(getByText('Управляющая компания не указана')).toBeTruthy()
    expect(getByText(/Администратор ещё не добавил информацию о доме/)).toBeTruthy()
    // заголовок карточки - название дома, раз адреса нет
    expect(getByText('Ленинского Комсомола, 5')).toBeTruthy()
  })
})
