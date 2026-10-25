import { describe, expect, it } from 'vitest'
import { click, getButton, getByText, queryByText, type, waitFor } from '@/test/dom'
import { renderRoute, type RenderOptions } from '@/test/harness'

/** Названия вещей на экране: подпись карточки «Название, цена». */
function titles(): string[] {
  return Array.from(document.querySelectorAll('a.card-soft[href^="/market/"]')).map(
    (a) => a.getAttribute('aria-label')!.split(',')[0]!,
  )
}

async function openMarket(options: RenderOptions = {}) {
  const rendered = await renderRoute('/market', options)
  if (!options.scenario) await waitFor(() => titles().length > 0)
  return rendered
}

describe('Вещи соседей', () => {
  it('показывает все объявления в продаже с ценой и отметкой брони', async () => {
    await openMarket()
    expect(titles()).toEqual([
      'Детская коляска 2 в 1',
      'Диван-книжка',
      'Рассада томатов',
      'Шуруповёрт Makita',
      'Телевизор Samsung 32"',
      'Помогу настроить телефон',
    ])
    expect(getByText('Забронировано')).toBeTruthy()
    const sofa = document.querySelector('a[href="/market/202"]')!
    expect(sofa.getAttribute('aria-label')).toMatch(/Диван-книжка, 3\s500 ₽/)
  })

  it('поиск оставляет только подходящие вещи', async () => {
    await openMarket()
    await type('Поиск по объявлениям', 'диван')
    await waitFor(() => titles().length === 1)
    expect(titles()).toEqual(['Диван-книжка'])
  })

  it('если по запросу ничего нет, советует поменять слова', async () => {
    await openMarket()
    await type('Поиск по объявлениям', 'вертолёт')
    await waitFor(() => getByText('Ничего не нашлось'))
    expect(getByText('Попробуйте другую категорию или слова')).toBeTruthy()
  })

  it('категория фильтрует список, повторное нажатие её снимает', async () => {
    const { max } = await openMarket()
    const plants = getButton('Растения')
    await click(plants)
    await waitFor(() => titles().length === 1)
    expect(titles()).toEqual(['Рассада томатов'])
    expect(plants.getAttribute('aria-pressed')).toBe('true')
    expect(max.selection).toHaveBeenCalled()

    await click(plants)
    await waitFor(() => titles().length === 6)
    expect(getButton('Все').getAttribute('aria-pressed')).toBe('true')
  })

  it('«Только даром» показывает бесплатные вещи и услуги', async () => {
    await openMarket()
    await click('Только даром')
    await waitFor(() => titles().length === 3)
    expect(titles()).toEqual([
      'Детская коляска 2 в 1',
      'Рассада томатов',
      'Помогу настроить телефон',
    ])
  })

  it('вкладка «Мои» показывает только объявления жителя', async () => {
    await openMarket()
    await click('Мои')
    await waitFor(() => titles().length === 1)
    expect(titles()).toEqual(['Телевизор Samsung 32"'])
  })

  it('вкладка «Закрытые» без закрытых объявлений объясняет, что там появится', async () => {
    await openMarket()
    await click('Закрытые')
    await waitFor(() => getByText('Пока пусто'))
    expect(
      getByText('Когда соседи отдадут или продадут вещи, объявления появятся здесь'),
    ).toBeTruthy()
  })

  it('нажатие на карточку открывает объявление', async () => {
    const { router } = await openMarket()
    await click(document.querySelector('a[href="/market/203"]')!)
    await waitFor(() => router.currentRoute.value.path === '/market/203')
  })

  it('без объявлений предлагает отдать или продать вещь', async () => {
    const { router } = await openMarket({ scenario: { name: 'empty' } })
    await waitFor(() => getByText('Пока пусто'))
    expect(
      getByText('Отдайте ненужное соседям или продайте: Кузя расскажет всему дому'),
    ).toBeTruthy()
    const empty = document.querySelector('section[role="status"]')!
    await click(getButton('Отдать или продать', empty))
    await waitFor(() => router.currentRoute.value.path === '/market/new')
  })

  it('в пустой вкладке «Мои» напоминает, что закрытые тоже будут здесь', async () => {
    await openMarket({ scenario: { name: 'empty' } })
    await waitFor(() => getByText('Пока пусто'))
    await click('Мои')
    await waitFor(() =>
      getByText('Вы ещё ничего не размещали. Закрытые объявления тоже будут здесь'),
    )
  })

  it('при ошибке сервера показывает причину и кнопку повтора', async () => {
    await openMarket({ scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    await click('Попробовать ещё раз')
    expect(queryByText('Диван-книжка')).toBeNull()
  })

  it('плавающая кнопка ведёт к новому объявлению', async () => {
    const { router } = await openMarket()
    await click(getButton('Отдать или продать', document.getElementById('fab-layer')!))
    await waitFor(() => router.currentRoute.value.path === '/market/new')
  })
})
