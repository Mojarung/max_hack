import { beforeEach, describe, expect, it, vi } from 'vitest'
import { scenario } from '@/mock/scenario'
import { click, getButton, getByText, getField, queryByText, type, waitFor } from '@/test/dom'
import { renderRoute } from '@/test/harness'

beforeEach(() => {
  // переключатель «Все / Администраторы» прокручивает к себе страницу, а jsdom этого не умеет
  vi.spyOn(window, 'scrollBy').mockImplementation(() => undefined)
})

/** Имена в списке соседей по порядку. */
function names(): string[] {
  return Array.from(document.querySelectorAll('.group-list li .font-semibold')).map((el) =>
    (el.textContent ?? '').trim(),
  )
}

describe('Соседи', () => {
  it('показывает всех жителей с квартирой, званием и значком администратора', async () => {
    await renderRoute('/people')
    await waitFor(() => getByText('Анна Петрова'))
    expect(names()).toEqual([
      'Анна Петрова',
      'Ильдар Хайруллин',
      'Марина Соколова',
      'Рустем Галиев',
      'Ольга Смирнова',
      'Тимур Зарипов',
    ])
    expect(getByText('кв. 12 · Добрый сосед')).toBeTruthy()
    expect(getByText('кв. 45 · Хранитель дома')).toBeTruthy()
    const ildar = getByText('Ильдар Хайруллин').closest('li')!
    expect(ildar.textContent).toContain('администратор')
    expect(getButton('Все 6')).toBeTruthy()
    expect(getButton('Администраторы 1')).toBeTruthy()
  })

  it('ищет соседа по имени', async () => {
    await renderRoute('/people')
    await waitFor(() => getByText('Анна Петрова'))
    await type(getField('Поиск соседей'), 'марина')
    expect(names()).toEqual(['Марина Соколова'])
  })

  it('ищет соседа по номеру квартиры', async () => {
    await renderRoute('/people')
    await waitFor(() => getByText('Анна Петрова'))
    await type(getField('Поиск соседей'), '88')
    expect(names()).toEqual(['Рустем Галиев'])
  })

  it('если никого не нашли, так и говорит', async () => {
    await renderRoute('/people')
    await waitFor(() => getByText('Анна Петрова'))
    await type(getField('Поиск соседей'), 'Евлампий')
    expect(getByText('Никого не нашли')).toBeTruthy()
    expect(getByText(/Соседи появляются здесь/)).toBeTruthy()
  })

  it('вкладка «Администраторы» оставляет только администраторов', async () => {
    await renderRoute('/people')
    await waitFor(() => getByText('Анна Петрова'))
    await click('Администраторы 1')
    expect(names()).toEqual(['Ильдар Хайруллин'])
  })

  it('нажатие на соседа открывает его профиль', async () => {
    const { router } = await renderRoute('/people')
    await click(await waitFor(() => getByText('Марина Соколова').closest('a')!))
    await waitFor(() => router.currentRoute.value.path === '/people/3')
  })

  it('ошибка загрузки: показывает причину и загружает заново по кнопке', async () => {
    await renderRoute('/people', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    expect(queryByText('Анна Петрова')).toBeNull()
    scenario.name = 'default'
    await click('Попробовать ещё раз')
    await waitFor(() => getByText('Анна Петрова'))
  })
})
