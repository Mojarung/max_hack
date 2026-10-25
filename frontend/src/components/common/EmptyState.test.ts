import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import { getButton, getByText } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import EmptyState from './EmptyState.vue'

describe('Пустой экран', () => {
  it('показывает Кузю, заголовок, пояснение и кнопки из слота', async () => {
    await renderComponent(EmptyState, {
      props: { title: 'Заявок пока нет', text: 'Сообщите о проблеме, соседи поддержат' },
      slots: { default: () => h('button', 'Сообщить о проблеме') },
    })
    const section = document.querySelector('section[role="status"]')!
    expect(section).not.toBeNull()
    expect(getByText('Заявок пока нет').tagName).toBe('H3')
    expect(getByText('Сообщите о проблеме, соседи поддержат')).toBeTruthy()
    expect(getButton('Сообщить о проблеме')).toBeTruthy()
  })

  it('без пояснения и слота остаётся только заголовок', async () => {
    await renderComponent(EmptyState, { props: { title: 'Пусто' } })
    const section = document.querySelector('section[role="status"]')!
    expect(section.querySelector('p')).toBeNull()
    expect(section.querySelector('.flex-wrap')).toBeNull()
  })
})
