import { describe, expect, it } from 'vitest'
import { click, getButton, getByText, queryByText, type, waitFor } from '@/test/dom'
import { renderRoute } from '@/test/harness'

/** Заголовки заявок из фикстур мока (src/mock/fixtures.ts). */
const ROOF = 'Течёт крыша над 9 этажом'
const LIGHT = 'Не горит свет в подъезде 3'
const LIFT = 'Не работает лифт в подъезде 1'
const WATER = 'Нет горячей воды'
const GARBAGE = 'Переполнены мусорные баки'
const BENCH = 'Сломана лавочка у 3 подъезда'
const ROAD = 'Яма на въезде во двор'

/** Чип фильтра по видимому тексту (кнопка в ряду «Фильтр по статусу»). */
function chip(title: string): HTMLElement {
  const toolbar = document.querySelector('[aria-label="Фильтр по статусу"]')
  if (!toolbar) throw new Error('Нет ряда фильтров')
  return getButton(title, toolbar)
}

describe('Список заявок', () => {
  it('показывает все заявки дома и подсказку о заявке, которая ждёт голоса', async () => {
    await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    for (const title of [LIGHT, LIFT, WATER, GARBAGE, BENCH, ROAD]) {
      expect(getByText(title)).toBeTruthy()
    }
    expect(getByText('1 заявка ждёт')).toBeTruthy()
    expect(getButton('Сообщить о проблеме')).toBeTruthy()
  })

  it('фильтр по статусу оставляет только решённые заявки и даёт отклик вибро', async () => {
    const { max } = await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    await click(chip('Решено'))
    await waitFor(() => queryByText(ROOF) === null)
    expect(getByText(BENCH)).toBeTruthy()
    expect(queryByText(LIFT)).toBeNull()
    expect(chip('Решено').getAttribute('aria-pressed')).toBe('true')
    expect(max.selection).toHaveBeenCalled()

    await click(chip('Все'))
    await waitFor(() => getByText(ROOF))
    expect(getByText(BENCH)).toBeTruthy()
  })

  it('повторное нажатие на выбранный статус ничего не перезапрашивает', async () => {
    const { max } = await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    await click(chip('Все'))
    expect(max.selection).not.toHaveBeenCalled()
    expect(getByText(ROOF)).toBeTruthy()
  })

  it('поиск по словам находит заявку про лифт', async () => {
    await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    await type('Поиск по заявкам', 'лифт')
    await waitFor(() => queryByText(ROOF) === null)
    expect(getByText(LIFT)).toBeTruthy()
  })

  it('если поиск ничего не нашёл, предлагает другие слова', async () => {
    await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    await type('Поиск по заявкам', 'слон в подъезде')
    await waitFor(() => getByText('Ничего не нашлось'))
    expect(getByText('Попробуйте другой статус или слова для поиска')).toBeTruthy()
  })

  it('по ссылке ?vote=1 показывает только заявки, которые ждут моего голоса', async () => {
    const { router, max } = await renderRoute('/issues?vote=1')
    await waitFor(() => getByText(ROOF))
    expect(queryByText(LIGHT)).toBeNull()
    expect(queryByText(LIFT)).toBeNull()
    expect(getByText('Только заявки, которые ждут вашего голоса')).toBeTruthy()

    await click(getButton(/Показать все/))
    await waitFor(() => router.currentRoute.value.query.vote === undefined)
    await waitFor(() => getByText(LIFT))
    expect(max.selection).toHaveBeenCalled()
  })

  it('подсказка «ждут вашего голоса» включает и выключает этот фильтр', async () => {
    const { router } = await renderRoute('/issues')
    await waitFor(() => getByText('1 заявка ждёт'))
    await click(getButton(/1 заявка ждёт/))
    await waitFor(() => router.currentRoute.value.query.vote === '1')
    await waitFor(() => queryByText(LIFT) === null)
    expect(getByText(ROOF)).toBeTruthy()
  })

  it('когда все заявки поддержаны, ?vote=1 благодарит и предлагает показать все', async () => {
    const { router } = await renderRoute('/issues?vote=1', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('Вы поддержали все заявки'))
    await click('Показать все заявки')
    await waitFor(() => router.currentRoute.value.query.vote === undefined)
    await waitFor(() => getByText('Заявок пока нет'))
  })

  it('по ссылке ?overdue=1 показывает только просроченные заявки', async () => {
    const { router } = await renderRoute('/issues?overdue=1')
    await waitFor(() => getByText(GARBAGE))
    expect(queryByText(ROOF)).toBeNull()
    expect(chip('Просрочено').getAttribute('aria-pressed')).toBe('true')

    await click(chip('Просрочено'))
    await waitFor(() => router.currentRoute.value.query.overdue === undefined)
    await waitFor(() => getByText(ROOF))
  })

  it('выбор статуса снимает особый фильтр из адреса', async () => {
    const { router } = await renderRoute('/issues?overdue=1')
    await waitFor(() => getByText(GARBAGE))
    await click(chip('Отправлено'))
    await waitFor(() => router.currentRoute.value.query.overdue === undefined)
    await waitFor(() => getByText(LIFT))
    expect(queryByText(ROOF)).toBeNull()
  })

  it('чип «Просрочено» включает фильтр просрочки', async () => {
    const { router } = await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    await click(chip('Просрочено'))
    await waitFor(() => router.currentRoute.value.query.overdue === '1')
    await waitFor(() => queryByText(ROOF) === null)
    expect(getByText(GARBAGE)).toBeTruthy()
  })

  it('без просрочек фильтр говорит, что всё в срок', async () => {
    await renderRoute('/issues?overdue=1', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('Просрочек нет'))
  })

  it('в пустом доме зовёт сообщить о первой проблеме и не показывает плавающую кнопку', async () => {
    const { router } = await renderRoute('/issues', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('Заявок пока нет'))
    expect(document.querySelector('#fab-layer .v-btn')).toBeNull()
    await click('Сообщить о проблеме')
    await waitFor(() => router.currentRoute.value.path === '/issues/new')
  })

  it('при ошибке сервера показывает текст и кнопку повтора', async () => {
    await renderRoute('/issues', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    expect(getButton('Попробовать ещё раз')).toBeTruthy()
    await click('Попробовать ещё раз')
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
  })

  it('нажатие на карточку открывает заявку', async () => {
    const { router } = await renderRoute('/issues')
    await waitFor(() => getByText(LIFT))
    await click(getButton(new RegExp(`^${LIFT}`)))
    await waitFor(() => router.currentRoute.value.path === '/issues/103')
  })

  it('плавающая кнопка ведёт к новой заявке', async () => {
    const { router } = await renderRoute('/issues')
    await waitFor(() => getByText(ROOF))
    const fab = document.querySelector<HTMLElement>('#fab-layer .v-btn')
    expect(fab?.getAttribute('aria-label')).toBe('Сообщить о проблеме')
    await click(fab!)
    await waitFor(() => router.currentRoute.value.path === '/issues/new')
  })
})
