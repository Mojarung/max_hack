import { describe, expect, it } from 'vitest'
import { defineComponent, h, type PropType } from 'vue'
import type { EventOut } from '@/api/types'
import { Toaster } from '@/components/ui/sonner'
import { useEventsStore } from '@/stores/events'
import { click, getButton, getByText, queryButton, textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import EventCard from './EventCard.vue'

/**
 * Карточка и тосты рядом: житель видит ответ после «Иду». С storeId событие берётся из стора,
 * как в списке событий, и карточка видит, что запись сохранилась.
 */
const Host = defineComponent({
  props: { event: { type: Object as PropType<EventOut>, default: null }, storeId: Number },
  setup(props) {
    const store = useEventsStore()
    return () => {
      const item = props.storeId
        ? store.scopes.upcoming.items.find((e) => e.id === props.storeId)
        : props.event
      return [item ? h(EventCard, { event: item }) : null, h(Toaster)]
    }
  },
})

function event(patch: Partial<EventOut> = {}): EventOut {
  return {
    id: 777,
    title: 'Чаепитие во дворе',
    description: '',
    kind: 'holiday',
    kind_title: 'Праздник',
    starts_at: '2026-10-24T17:00:00+04:00',
    place: 'Беседка',
    photos: [],
    max_participants: null,
    participants_count: 3,
    joined_by_me: false,
    comments_count: 0,
    author: { id: 2, first_name: 'Ильдар' },
    created_at: '2026-10-20T10:00:00+04:00',
    score: null,
    ...patch,
  }
}

async function renderFromStore(id: number) {
  const rendered = await renderComponent(Host, { props: { storeId: id } })
  await useEventsStore().load('upcoming')
  await waitFor(() => document.querySelector('article'))
  return rendered
}

describe('Карточка события', () => {
  it('показывает дату, название, место и сколько идёт', async () => {
    await renderComponent(EventCard, {
      props: { event: event({ max_participants: 10 }) },
    })
    const card = document.querySelector('article')!
    expect(getByText('Чаепитие во дворе')).toBeTruthy()
    expect(textOf(card)).toContain('24 октября')
    expect(textOf(card)).toContain('17:00')
    expect(textOf(card)).toContain('Беседка')
    expect(textOf(card)).toContain('3 участника из 10')
    expect(card.querySelector('a')!.getAttribute('href')).toBe('/events/777')
    // без фото обложка - значок типа события
    expect(card.querySelector('.mdi-party-popper')).not.toBeNull()
    expect(getButton('Иду')).toBeTruthy()
  })

  it('фото организатора становится обложкой', async () => {
    await renderComponent(EventCard, { props: { event: event({ photos: ['/demo/tea.jpg'] }) } })
    expect(document.querySelector('article img')!.getAttribute('src')).toBe('/demo/tea.jpg')
  })

  it('у прошедшего события нет кнопки записи', async () => {
    await renderComponent(EventCard, { props: { event: event(), past: true } })
    expect(queryButton('Иду')).toBeNull()
    expect(queryButton('Не смогу')).toBeNull()
  })

  it('записанный житель видит «Вы идёте» и отдельную кнопку отмены', async () => {
    await renderComponent(EventCard, { props: { event: event({ joined_by_me: true }) } })
    expect(getByText('Вы идёте')).toBeTruthy()
    expect(getButton('Не смогу')).toBeTruthy()
    expect(queryButton('Иду')).toBeNull()
  })

  it('«Иду» записывает на событие, «Не смогу» отменяет запись', async () => {
    const { max } = await renderFromStore(301)
    expect(textOf(document.querySelector('article'))).toContain('4 участника из 20')

    await click('Иду')
    expect(max.impact).toHaveBeenCalledWith('medium')
    await waitFor(() => getByText('Вы идёте! Кузя напомнит заранее'))
    expect(getByText('Вы идёте')).toBeTruthy()
    expect(textOf(document.querySelector('article'))).toContain('5 участников из 20')
    expect(max.notify).toHaveBeenCalledWith('success')

    await click('Не смогу')
    await waitFor(() => getByText(/Запись отменена/))
    await waitFor(() => getButton('Иду'))
    expect(textOf(document.querySelector('article'))).toContain('4 участника из 20')
  })

  it('если событие не удалось сохранить, житель видит причину', async () => {
    const { max } = await renderComponent(Host, { props: { event: event() } })
    await click('Иду')
    await waitFor(() => getByText('Не удалось сохранить'))
    expect(getByText('Событие не найдено')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('error')
    expect(getButton('Иду')).toBeTruthy()
  })
})
