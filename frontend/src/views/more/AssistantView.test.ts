import { DOMWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { assistantApi } from '@/api/endpoints'
import {
  click,
  getButton,
  getByText,
  getField,
  queryButton,
  queryByText,
  textOf,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute } from '@/test/harness'

/** Сообщения переписки: кто и что написал. */
function messages(): { who: 'я' | 'Кузя'; text: string }[] {
  return Array.from(document.querySelectorAll('.msg:not(:has(.typing))')).map((el) => ({
    who: el.classList.contains('msg--me') ? 'я' : 'Кузя',
    text: textOf(el.querySelector('.pre-wrap')),
  }))
}

describe('Спросить Кузю', () => {
  it('на пустом экране Кузя здоровается и предлагает частые вопросы', async () => {
    await renderRoute('/more/assistant')
    expect(getByText('Привет! Я Кузя, домовой вашего дома')).toBeTruthy()
    for (const question of [
      'Какие заявки сейчас открыты?',
      'Когда ближайший субботник?',
      'Кто отвечает за лифт?',
      'Где ближайшее укрытие?',
    ]) {
      expect(getButton(question)).toBeTruthy()
    }
    expect(getButton('Отправить').hasAttribute('disabled')).toBe(true)
  })

  it('частый вопрос одним нажатием: Кузя отвечает и пишет, что смотрел', async () => {
    await renderRoute('/more/assistant')
    await click('Кто отвечает за лифт?')
    await waitFor(() => messages().length === 2)

    const [question, answer] = messages()
    expect(question).toEqual({ who: 'я', text: 'Кто отвечает за лифт?' })
    expect(answer!.who).toBe('Кузя')
    expect(answer!.text).toContain('Вы спросили: «Кто отвечает за лифт?»')
    expect(getByText('смотрел состояние дома')).toBeTruthy()
    expect(getByText('смотрел заявки дома')).toBeTruthy()
    // приветствие ушло, под полем появились подсказки
    expect(queryByText('Привет! Я Кузя, домовой вашего дома')).toBeNull()
    expect(getButton('Что отдают даром?')).toBeTruthy()
  })

  it('свой вопрос отправляется кнопкой и клавишей Enter, поле очищается', async () => {
    await renderRoute('/more/assistant')
    const field = getField('Сообщение Кузе')

    await type(field, '  Когда вывезут мусор?  ')
    expect(getButton('Отправить').hasAttribute('disabled')).toBe(false)
    await click('Отправить')
    await waitFor(() => messages().length === 2)
    expect(messages()[0]).toEqual({ who: 'я', text: 'Когда вывезут мусор?' })
    expect((field as HTMLTextAreaElement).value).toBe('')

    await type(field, 'А укрытие где?')
    await new DOMWrapper(field).trigger('keydown', { key: 'Enter' })
    await waitFor(() => messages().length === 4)
    expect(messages()[2]).toEqual({ who: 'я', text: 'А укрытие где?' })

    // подсказка под полем тоже задаёт вопрос
    await click('Что отдают даром?')
    await waitFor(() => messages().length === 6)
    expect(messages()[4]!.text).toBe('Что отдают даром?')
  })

  it('пустой вопрос не отправляется', async () => {
    const chat = vi.spyOn(assistantApi, 'chat')
    await renderRoute('/more/assistant')
    await type(getField('Сообщение Кузе'), '   ')
    await new DOMWrapper(getField('Сообщение Кузе')).trigger('keydown', { key: 'Enter' })
    expect(chat).not.toHaveBeenCalled()
    expect(messages()).toHaveLength(0)
  })

  it('пока Кузя думает, видно «печатает», а вопросы не нажимаются', async () => {
    let answer: (value: { reply: string; tools_used: string[] }) => void = () => undefined
    vi.spyOn(assistantApi, 'chat').mockImplementation(
      () => new Promise((resolve) => (answer = resolve)),
    )
    await renderRoute('/more/assistant')
    await click('Где ближайшее укрытие?')

    await waitFor(() => getByText('Кузя печатает'))
    expect(queryButton('Что отдают даром?')?.classList.contains('v-chip--disabled')).toBe(true)

    answer({ reply: 'Ближайшее укрытие в подвале школы', tools_used: ['find_shelters', 'weather'] })
    await waitFor(() => !queryByText('Кузя печатает'))
    expect(messages()[1]!.text).toBe('Ближайшее укрытие в подвале школы')
    expect(getByText('смотрел укрытия')).toBeTruthy()
    // незнакомый инструмент показываем как есть
    expect(getByText('смотрел weather')).toBeTruthy()
  })

  it('если сервер не ответил, Кузя честно пишет об ошибке', async () => {
    await renderRoute('/more/assistant', { scenario: { name: 'error' } })
    await click('Какие заявки сейчас открыты?')
    await waitFor(() => messages().length === 2)
    expect(messages()[1]!.text).toBe(
      'Не получилось ответить: Кузя споткнулся на сервере. Попробуйте ещё раз',
    )
    expect(document.querySelector('.msg--failed')).not.toBeNull()
  })
})
