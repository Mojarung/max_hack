import { beforeEach, describe, expect, it } from 'vitest'
import { click, getButton, getByText, queryByText, textOf, waitFor } from '@/test/dom'
import { renderRoute } from '@/test/harness'

// Выбранная вкладка запоминается на вкладку браузера: каждый тест начинает со «Скоро»
beforeEach(() => sessionStorage.removeItem('kuzya.eventsScope'))

/** Заголовки карточек событий в порядке показа. */
function cardTitles(): string[] {
  return Array.from(document.querySelectorAll('article h3')).map((el) => textOf(el))
}

describe('Список событий двора', () => {
  it('на вкладке «Скоро» показывает будущие события по дате, без прошедших', async () => {
    await renderRoute('/events')
    await waitFor(() => getByText('Осенний субботник'))
    expect(cardTitles()).toEqual([
      'Осенний субботник',
      'Собрание по капремонту кровли',
      'Праздник двора',
    ])
    expect(queryByText('Турнир по мини-футболу')).toBeNull()
    // на собрание житель уже записан, на субботник ещё нет
    expect(getByText('Вы идёте')).toBeTruthy()
    expect(getByText('4 участника из 20')).toBeTruthy()
  })

  it('вкладка «Прошедшие» показывает прошедшие события без кнопки «Иду»', async () => {
    await renderRoute('/events')
    await waitFor(() => getByText('Осенний субботник'))
    await click('Прошедшие')
    await waitFor(() => getByText('Турнир по мини-футболу'))
    expect(cardTitles()).toEqual(['Турнир по мини-футболу', 'Весенний субботник'])
    expect(queryByText('Осенний субботник')).toBeNull()
    expect(document.querySelector('[role="radio"][aria-checked="true"]')?.textContent).toContain(
      'Прошедшие',
    )
  })

  it('нажатие на карточку открывает страницу события', async () => {
    const { router } = await renderRoute('/events')
    await click(await waitFor(() => getByText('Праздник двора')))
    await waitFor(() => router.currentRoute.value.path === '/events/303')
  })

  it('кнопка «Иду» в карточке записывает жителя и вибрирует', async () => {
    const { max } = await renderRoute('/events')
    await waitFor(() => getByText('Осенний субботник'))
    const card = getByText('Осенний субботник').closest('article')!
    await click(getButton('Иду', card))
    await waitFor(() => getByText('Вы идёте! Кузя напомнит заранее'))
    expect(textOf(card)).toContain('5 участников из 20')
    expect(max.impact).toHaveBeenCalledWith('medium')
  })

  it('плавающая кнопка ведёт к созданию события', async () => {
    const { router } = await renderRoute('/events')
    await waitFor(() => getByText('Осенний субботник'))
    await click(getButton('Создать событие', document.getElementById('fab-layer')!))
    await waitFor(() => router.currentRoute.value.path === '/events/new')
  })

  it('без событий предлагает создать первое', async () => {
    const { router } = await renderRoute('/events', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('Пока ничего не запланировано'))
    expect(getByText('Предложите субботник, праздник двора или собрание')).toBeTruthy()
    const empty = document.querySelector('section[role="status"]')!
    await click(getButton('Создать событие', empty))
    await waitFor(() => router.currentRoute.value.path === '/events/new')
  })

  it('без прошедших событий так и говорит', async () => {
    await renderRoute('/events', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('Пока ничего не запланировано'))
    await click('Прошедшие')
    await waitFor(() => getByText('Прошедших событий нет'))
  })

  it('при ошибке сервера показывает причину и даёт повторить', async () => {
    await renderRoute('/events', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    await click('Попробовать ещё раз')
    expect(getByText('Не получилось загрузить')).toBeTruthy()
  })
})
