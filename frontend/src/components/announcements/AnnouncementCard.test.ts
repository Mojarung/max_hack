import { describe, expect, it } from 'vitest'
import { h } from 'vue'
import type { AnnouncementOut } from '@/api/types'
import { click, getByText, queryByText, textOf, waitFor } from '@/test/dom'
import { NOW, renderComponent } from '@/test/harness'
import AnnouncementCard from './AnnouncementCard.vue'

function item(patch: Partial<AnnouncementOut> = {}): AnnouncementOut {
  return {
    id: 901,
    title: 'Отключение горячей воды',
    text: 'Плановые работы на теплотрассе.\nВоду дадут к 18:00.',
    pinned: false,
    event_id: null,
    author: null,
    is_mine: false,
    created_at: new Date(NOW.getTime() - 3 * 3_600_000).toISOString(),
    ...patch,
  }
}

function card(): HTMLElement {
  return document.querySelector('article') as HTMLElement
}

describe('Карточка объявления', () => {
  it('показывает заголовок, текст и когда опубликовано', async () => {
    await renderComponent(AnnouncementCard, { props: { item: item() } })
    expect(getByText('Отключение горячей воды')).toBeTruthy()
    expect(getByText(/Плановые работы на теплотрассе/)).toBeTruthy()
    expect(textOf(card())).toContain('3 ч назад')
    expect(textOf(card())).not.toContain('закреплено')
    expect(card().querySelector('.mdi-bullhorn-variant-outline')).not.toBeNull()
    expect(card().querySelector('.line-clamp-3')).toBeNull()
  })

  it('закреплённое объявление отмечено значком и словами для диктора', async () => {
    await renderComponent(AnnouncementCard, { props: { item: item({ pinned: true }) } })
    expect(card().className).toContain('announcement--pinned')
    expect(card().querySelector('.mdi-pin')).not.toBeNull()
    expect(textOf(card().querySelector('h3'))).toBe('Закреплено. Отключение горячей воды')
    expect(textOf(card())).toContain('· закреплено')
  })

  it('называет автора, если объявление от соседа', async () => {
    await renderComponent(AnnouncementCard, {
      props: { item: item({ author: { id: 1, first_name: 'Анна', last_name: 'Петрова' } }) },
    })
    expect(textOf(card())).toContain('Анна Петрова · 3 ч назад')
  })

  it('на главной длинный текст обрезается', async () => {
    await renderComponent(AnnouncementCard, { props: { item: item(), clamp: true } })
    expect(card().querySelector('.line-clamp-3')).not.toBeNull()
  })

  it('без текста показывает только заголовок', async () => {
    await renderComponent(AnnouncementCard, { props: { item: item({ text: '' }) } })
    expect(card().querySelector('p')).toBeNull()
  })

  it('объявление о событии ведёт к записи', async () => {
    const { router } = await renderComponent(AnnouncementCard, {
      props: { item: item({ event_id: 301 }) },
    })
    await click(getByText('Записаться на событие').closest('a')!)
    await waitFor(() => router.currentRoute.value.path === '/events/301')
  })

  it('под текстом рисует кнопки из слота', async () => {
    await renderComponent(AnnouncementCard, {
      props: { item: item() },
      slots: { default: () => h('button', 'Открепить') },
    })
    expect(getByText('Открепить')).toBeTruthy()
    expect(queryByText('Записаться на событие')).toBeNull()
  })
})
