import { describe, expect, it } from 'vitest'
import type { IssueOut } from '@/api/types'
import { click, getByText, queryByText, textOf, waitFor } from '@/test/dom'
import { NOW, renderComponent } from '@/test/harness'
import IssueCard from './IssueCard.vue'

const HOUR = 3_600_000

function issue(patch: Partial<IssueOut> = {}): IssueOut {
  return {
    id: 101,
    title: 'Течёт крыша над 9 этажом',
    description: 'После дождя течёт с потолка',
    category: 'roof',
    category_title: 'Кровля',
    status: 'voting',
    status_title: 'Голосование',
    votes_count: 4,
    votes_needed: 6,
    voted_by_me: false,
    photos: [],
    author: { id: 3, first_name: 'Марина', last_name: 'Соколова' },
    responsible_org: { name: 'УК «Уютный дом»', kind: 'uk', kind_title: 'Управляющая компания' },
    created_at: new Date(NOW.getTime() - 5 * HOUR).toISOString(),
    sent_at: null,
    deadline_at: null,
    is_overdue: false,
    score: null,
    ...patch,
  }
}

function card(): HTMLAnchorElement {
  return document.querySelector('a.card-soft') as HTMLAnchorElement
}

describe('Карточка заявки', () => {
  it('для сбора голосов показывает статус, полосу и сколько ещё нужно', async () => {
    await renderComponent(IssueCard, { props: { issue: issue() } })
    expect(getByText('Течёт крыша над 9 этажом')).toBeTruthy()
    expect(getByText('Собираем голоса')).toBeTruthy()
    expect(textOf(card())).toContain('Кровля · 4 из 6 голосов')
    expect(document.querySelector('[role="progressbar"]')).not.toBeNull()
    expect(queryByText('вы поддержали')).toBeNull()
    expect(card().getAttribute('aria-label')).toBe('Течёт крыша над 9 этажом. Собираем голоса')
    expect(card().getAttribute('href')).toBe('/issues/101')
  })

  it('отмечает, что житель уже поддержал заявку', async () => {
    await renderComponent(IssueCard, { props: { issue: issue({ voted_by_me: true }) } })
    expect(getByText('вы поддержали')).toBeTruthy()
  })

  it('для отправленной заявки пишет, кому ушло обращение и когда создана', async () => {
    await renderComponent(IssueCard, {
      props: { issue: issue({ status: 'sent', status_title: 'Отправлено' }) },
    })
    expect(getByText('Отправлено')).toBeTruthy()
    expect(textOf(card())).toContain('Кровля · Управляющая компания «Уютный дом» · 5 ч назад')
    expect(document.querySelector('[role="progressbar"]')).toBeNull()
  })

  it('без ответственной организации строка короче', async () => {
    await renderComponent(IssueCard, {
      props: { issue: issue({ status: 'resolved', responsible_org: null }) },
    })
    expect(textOf(card())).toContain('Кровля · 5 ч назад')
    expect(textOf(card())).not.toContain('Управляющая')
  })

  it('просроченную заявку видно сразу: чип, красная полоса и подпись для диктора', async () => {
    await renderComponent(IssueCard, {
      props: { issue: issue({ status: 'sent', is_overdue: true }) },
    })
    expect(getByText('Просрочено')).toBeTruthy()
    expect(card().className).toContain('issue-card--overdue')
    expect(card().getAttribute('aria-label')).toBe('Течёт крыша над 9 этажом. Просрочено')
  })

  it('без фото показывает значок категории', async () => {
    await renderComponent(IssueCard, { props: { issue: issue() } })
    expect(card().querySelector('img')).toBeNull()
    expect(card().querySelector('.mdi-home-roof')).not.toBeNull()
    expect(card().querySelector('.issue-thumb--empty')).not.toBeNull()
  })

  it('фото, которое не загрузилось, заменяется значком категории', async () => {
    await renderComponent(IssueCard, {
      props: { issue: issue({ category: 'unknown', photos: ['/demo/roof-drip.jpg'] }) },
    })
    const img = card().querySelector('img')!
    expect(img.getAttribute('src')).toBe('/demo/roof-drip.jpg')
    img.dispatchEvent(new Event('error'))
    await waitFor(() => card().querySelector('img') === null)
    expect(card().querySelector('.mdi-alert-circle-outline')).not.toBeNull()
  })

  it('нажатие открывает заявку', async () => {
    const { router } = await renderComponent(IssueCard, { props: { issue: issue() } })
    await click(card())
    await waitFor(() => router.currentRoute.value.path === '/issues/101')
  })
})
