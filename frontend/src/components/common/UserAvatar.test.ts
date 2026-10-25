import { describe, expect, it } from 'vitest'
import { nextTick, reactive } from 'vue'
import type { UserShort } from '@/api/types'
import { textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import UserAvatar from './UserAvatar.vue'

const ANNA: UserShort = { id: 1, first_name: 'Анна', last_name: 'Петрова' }

function avatar(): HTMLElement {
  return document.querySelector('.v-avatar') as HTMLElement
}

function image(): HTMLImageElement | null {
  return avatar().querySelector('img')
}

describe('Аватар жителя', () => {
  it('ставит фото из MAX и подписывает его именем', async () => {
    await renderComponent(UserAvatar, {
      props: { user: { ...ANNA, photo_url: 'https://max.example/anna.jpg' }, size: 48 },
    })
    await waitFor(() => image())
    expect(image()!.getAttribute('src')).toBe('https://max.example/anna.jpg')
    expect(image()!.getAttribute('alt')).toBe('Анна Петрова')
    expect(avatar().getAttribute('title')).toBe('Анна Петрова')
  })

  it('житель без фото получает свой войлочный шарик по id', async () => {
    await renderComponent(UserAvatar, { props: { user: { ...ANNA, id: 4 } } })
    await waitFor(() => image())
    expect(image()!.getAttribute('src')).toBe('/avatars/5.webp')
  })

  it('если картинка не загрузилась, показывает инициалы', async () => {
    const props = reactive<{ user: UserShort; size: number }>({ user: ANNA, size: 48 })
    await renderComponent(UserAvatar, { props })
    await waitFor(() => image())
    image()!.dispatchEvent(new Event('error'))
    await waitFor(() => textOf(avatar()) === 'АП')
    const letters = avatar().querySelector('span[aria-hidden="true"]') as HTMLElement
    expect(letters.style.fontSize).toBe('19px')

    // другой житель - снова пробуем картинку
    props.user = { id: 2, first_name: 'Ильдар', last_name: 'Хайруллин' }
    await nextTick()
    await waitFor(() => image())
  })

  it('в маленьком аватаре оставляет одну букву не мельче 14px', async () => {
    const { wrapper } = await renderComponent(UserAvatar, { props: { user: ANNA, size: 28 } })
    await waitFor(() => image())
    image()!.dispatchEvent(new Event('error'))
    await waitFor(() => textOf(avatar()) === 'А')
    const letters = wrapper.find('span[aria-hidden="true"]').element as HTMLElement
    expect(letters.style.fontSize).toBe('14px')
  })

  it('без жителя показывает знак вопроса и подпись «Житель»', async () => {
    await renderComponent(UserAvatar, { props: { user: null } })
    expect(image()).toBeNull()
    expect(textOf(avatar())).toBe('?')
    expect(avatar().getAttribute('title')).toBe('Житель')
  })
})
