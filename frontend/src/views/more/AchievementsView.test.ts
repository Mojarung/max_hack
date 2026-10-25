import { describe, expect, it, vi } from 'vitest'
import { achievementsApi } from '@/api/endpoints'
import {
  accessibleName,
  click,
  getButton,
  getByText,
  queryByText,
  textOf,
  waitFor,
} from '@/test/dom'
import { renderRoute, useScenario } from '@/test/harness'

/** Подписи наград в сетке по порядку, как их прочтёт диктор. */
function badges(): string[] {
  return Array.from(document.querySelectorAll('button.badge')).map(accessibleName)
}

function leaders(): string[] {
  return Array.from(document.querySelectorAll('a.leader')).map(textOf)
}

describe('Награды и рейтинг', () => {
  it('показывает уровень жителя и сколько очков до следующего', async () => {
    await renderRoute('/more/achievements')
    await waitFor(() => getByText('Ваш уровень'))
    expect(getByText('Добрый сосед')).toBeTruthy()
    expect(getByText('145')).toBeTruthy()
    expect(getByText('До следующего уровня: 105 очков')).toBeTruthy()
  })

  it('сначала полученные награды, у закрытых сразу видно условие', async () => {
    await renderRoute('/more/achievements')
    await waitFor(() => getButton('Награды 4 из 11'))
    const list = badges()
    expect(list).toHaveLength(11)
    expect(list.slice(0, 4)).toEqual([
      'Глаза дома. Получено',
      'Голос соседа. Получено',
      'Добрая рука. Получено',
      'Чистый двор. Получено',
    ])
    expect(list[4]).toBe('Активист. Ещё не получено')
    expect(getByText('Поддержать 10 заявок')).toBeTruthy()
    expect(getByText('+10')).toBeTruthy()
  })

  it('по нажатию на награду показывает подробности', async () => {
    await renderRoute('/more/achievements')
    await click(await waitFor(() => getButton('Глаза дома. Получено')))
    await waitFor(() => getByText('Получено 17 октября'))
    expect(getByText('Сообщить о первой проблеме')).toBeTruthy()
    await click('Понятно')
    await waitFor(() => !queryByText('Получено 17 октября'))

    await click(getButton('Хранитель. Ещё не получено'))
    await waitFor(() => getByText('Ещё не получено · +50 очков'))
  })

  it('рейтинг соседей по очкам, житель отмечен и строка ведёт в профиль', async () => {
    // переключатель подкручивает страницу к себе, в jsdom прокрутки нет
    vi.spyOn(window, 'scrollBy').mockImplementation(() => undefined)
    const { router } = await renderRoute('/more/achievements')
    await click(await waitFor(() => getButton('Рейтинг соседей')))
    await waitFor(() => leaders().length === 6)
    const rows = leaders()
    expect(rows[0]).toMatch(/Ильдар Хайруллин.*420/)
    expect(rows[2]).toMatch(/Анна Петрова \(вы\).*145/)
    // с четвёртого места вместо медали номер
    expect(textOf(document.querySelectorAll('.leader__rank')[3])).toBe('4')
    expect(rows[3]).toContain('Рустем Галиев')
    expect(document.querySelector('a.leader--me')?.getAttribute('href')).toBe('/people/1')

    await click(document.querySelectorAll('a.leader')[1]!)
    await waitFor(() => router.currentRoute.value.path === '/people/3')
  })

  it('у нового жителя ни одной награды', async () => {
    await renderRoute('/more/achievements', { scenario: { name: 'empty' } })
    await waitFor(() => getButton('Награды 0 из 11'))
    expect(getByText('Новосёл')).toBeTruthy()
    expect(getByText('До следующего уровня: 50 очков')).toBeTruthy()
    expect(badges().every((b) => b.endsWith('Ещё не получено'))).toBe(true)
  })

  it('при ошибке загрузки даёт повторить', async () => {
    await renderRoute('/more/achievements', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    expect(queryByText('Рейтинг соседей')).toBeNull()

    useScenario({})
    await click('Попробовать ещё раз')
    await waitFor(() => getButton('Награды 4 из 11'))
  })

  it('во время загрузки виден каркас сетки наград', async () => {
    // ответ сервера придержан, пока не проверим экран загрузки
    let release = () => undefined as void
    const gate = new Promise<void>((resolve) => (release = resolve))
    const original = achievementsApi.list
    vi.spyOn(achievementsApi, 'list').mockImplementation(async () => {
      await gate
      return original()
    })
    await renderRoute('/more/achievements')
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    release()
    await waitFor(() => getButton('Награды 4 из 11'))
    expect(document.querySelector('[aria-busy="true"]')).toBeNull()
  })
})
