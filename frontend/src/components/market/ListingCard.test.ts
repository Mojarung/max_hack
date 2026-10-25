import { describe, expect, it } from 'vitest'
import type { ListingOut } from '@/api/types'
import { click, getByText, queryByText, textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import ListingCard from './ListingCard.vue'

function listing(patch: Partial<ListingOut> = {}): ListingOut {
  return {
    id: 5,
    title: 'Детская коляска',
    description: 'Почти новая',
    price: 1500,
    is_free: false,
    category: 'kids',
    category_title: 'Детское',
    status: 'active',
    photos: [],
    author: { id: 5, first_name: 'Ольга', apartment: '23' },
    is_mine: false,
    created_at: '2026-10-20T10:00:00+04:00',
    score: null,
    ...patch,
  }
}

function card(): HTMLAnchorElement {
  return document.querySelector('a.card-soft') as HTMLAnchorElement
}

describe('Карточка вещи', () => {
  it('показывает цену, название, категорию и квартиру соседа', async () => {
    await renderComponent(ListingCard, { props: { listing: listing() } })
    expect(textOf(card())).toContain('1 500 ₽')
    expect(getByText('Детская коляска')).toBeTruthy()
    expect(textOf(card())).toContain('Детское · кв. 23')
    expect(card().getAttribute('href')).toBe('/market/5')
    expect(card().getAttribute('aria-label')!.replace(/\s+/g, ' ')).toBe('Детская коляска, 1 500 ₽')
  })

  it('бесплатную вещь подписывает «Даром» с подарком', async () => {
    await renderComponent(ListingCard, { props: { listing: listing({ price: 0, is_free: true }) } })
    expect(textOf(card())).toContain('Даром')
    expect(card().querySelector('.mdi-gift-outline')).not.toBeNull()
  })

  it('у вещи в продаже нет чипа, у забронированной есть', async () => {
    await renderComponent(ListingCard, { props: { listing: listing({ status: 'reserved' }) } })
    expect(getByText('Забронировано')).toBeTruthy()
    expect(queryByText('В продаже')).toBeNull()
  })

  it('закрытую вещь помечает «Закрыто»', async () => {
    await renderComponent(ListingCard, { props: { listing: listing({ status: 'closed' }) } })
    expect(getByText('Закрыто')).toBeTruthy()
  })

  it('без фото рисует значок категории, без квартиры - только категорию', async () => {
    await renderComponent(ListingCard, {
      props: { listing: listing({ category: 'mystery', author: { id: 9, first_name: 'Тимур' } }) },
    })
    expect(card().querySelector('.mdi-shape-outline')).not.toBeNull()
    expect(textOf(card())).not.toContain('кв.')
  })

  it('с фото показывает ленту, нажатие открывает объявление', async () => {
    const { router } = await renderComponent(ListingCard, {
      props: { listing: listing({ photos: ['/demo/stroller.jpg'] }) },
    })
    expect(card().querySelector('img')!.getAttribute('src')).toBe('/demo/stroller.jpg')
    await click(card())
    await waitFor(() => router.currentRoute.value.path === '/market/5')
  })
})
