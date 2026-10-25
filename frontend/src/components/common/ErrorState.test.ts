import { describe, expect, it } from 'vitest'
import { click, getButton, getByText } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import ErrorState from './ErrorState.vue'

describe('Экран ошибки', () => {
  it('объясняет, что не загрузилось, и предлагает повторить', async () => {
    const { wrapper } = await renderComponent(ErrorState, {
      props: { message: 'Нет связи с сервером. Проверьте интернет' },
    })
    expect(document.querySelector('section[role="alert"]')).not.toBeNull()
    expect(getByText('Не получилось загрузить')).toBeTruthy()
    expect(getByText('Нет связи с сервером. Проверьте интернет')).toBeTruthy()

    await click('Попробовать ещё раз')
    expect(wrapper.findComponent(ErrorState).emitted('retry')).toHaveLength(1)
  })

  it('свой заголовок и крутилка, пока идёт повтор', async () => {
    await renderComponent(ErrorState, {
      props: { message: 'Ошибка 500', title: 'Кузя споткнулся', retrying: true },
    })
    expect(getByText('Кузя споткнулся')).toBeTruthy()
    const button = getButton('Попробовать ещё раз')
    expect(button.className).toContain('v-btn--loading')
    expect(button.querySelector('.v-btn__loader .v-progress-circular')).not.toBeNull()
  })
})
