import { DOMWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { devChatApi } from '@/api/endpoints'
import type { ChatMessage, DevChat } from '@/api/types'
import { scenario } from '@/mock/scenario'
import { useDevChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import {
  click,
  getButton,
  getByText,
  getField,
  queryButton,
  queryByText,
  settle,
  type,
  waitFor,
} from '@/test/dom'
import { NOW, renderApp, renderRoute } from '@/test/harness'

const HOUR = 3_600_000
const at = (ms: number) => new Date(NOW.getTime() + ms).toISOString()

const GROUP: DevChat = { chat_id: 1, title: 'Ленинского Комсомола, 5 - домовой чат', type: 'chat' }
const DIALOG: DevChat = { chat_id: 1001, title: 'Личка с Кузей', type: 'dialog' }

function message(patch: Partial<ChatMessage> & Pick<ChatMessage, 'id'>): ChatMessage {
  return {
    chat_id: 1,
    from: null,
    text: '',
    buttons: null,
    deleted: false,
    notice: null,
    created_at: at(-HOUR),
    ...patch,
  }
}

/** Переписка в чате дома: сосед вчера, ответ Кузи с кнопками, удалённый спам и моё сообщение. */
const HISTORY: ChatMessage[] = [
  message({
    id: 'm1',
    from: { user_id: 1003, name: 'Марина' },
    text: 'Опять не горит свет в подъезде',
    created_at: at(-15 * HOUR),
  }),
  message({
    id: 'm2',
    text: 'Записал заявку **Не горит свет в подъезде 3**. Поддержите голосом',
    buttons: [
      [
        { type: 'callback', text: 'Поддержать', payload: 'vote:102' },
        { type: 'open_app', text: 'Открыть заявку', payload: 'issue_102' },
      ],
      [
        { type: 'link', text: 'Правила дома', url: 'https://example.org/rules' },
        { type: 'open_app', text: 'Куда-то не туда', payload: 'nowhere' },
      ],
    ],
    created_at: at(-30 * 60_000),
  }),
  message({
    id: 'm3',
    from: { user_id: 1006, name: 'Тимур' },
    text: 'Заработок от 100000 в день',
    deleted: true,
    notice: 'Кузя удалил рекламу',
    buttons: [[{ type: 'callback', text: 'Скрытая кнопка', payload: 'x' }]],
    created_at: at(-20 * 60_000),
  }),
  message({
    id: 'm4',
    from: { user_id: 1001, name: 'Анна' },
    text: 'Спасибо, Кузя!',
    created_at: at(-10 * 60_000),
  }),
]

let history: Record<number, ChatMessage[]>

beforeEach(() => {
  history = { [GROUP.chat_id]: HISTORY, [DIALOG.chat_id]: [] }
  vi.spyOn(devChatApi, 'chats').mockImplementation(async () => [GROUP, DIALOG])
  vi.spyOn(devChatApi, 'messages').mockImplementation(async (id) => history[id] ?? [])
  vi.spyOn(devChatApi, 'send').mockResolvedValue({ ok: true })
  vi.spyOn(devChatApi, 'callback').mockResolvedValue({ ok: true })
})

async function openChat() {
  const rendered = await renderRoute('/dev/chat')
  await waitFor(() => getByText('Спасибо, Кузя!'))
  return rendered
}

function keyButton(text: string): HTMLElement {
  return getButton(text, document.querySelector('.max-chat')!)
}

describe('Эмулятор чата MAX: переписка', () => {
  it('шапка группового чата и сообщения с подписями дней', async () => {
    await openChat()
    expect(getByText('Ленинского Комсомола, 5 - домовой чат')).toBeTruthy()
    expect(getByText('Чат дома · Кузя в чате')).toBeTruthy()
    const days = Array.from(document.querySelectorAll('.max-chat__inner > .max-sys')).map((el) =>
      el.textContent?.trim(),
    )
    expect(days).toEqual(['Вчера', 'Сегодня'])
    // имя соседа над чужим сообщением, первая буква в кружке
    expect(getByText('Марина')).toBeTruthy()
    expect(document.querySelector('.max-avatar--letter')?.textContent?.trim()).toBe('М')
  })

  it('свои сообщения справа, жирный текст бота выделен, время подписано', async () => {
    await openChat()
    const mine = getByText('Спасибо, Кузя!').closest('.max-row')!
    expect(mine.classList.contains('max-row--out')).toBe(true)
    const bold = document.querySelector('.max-msg b')
    expect(bold?.textContent).toBe('Не горит свет в подъезде 3')
    expect(getByText('09:30')).toBeTruthy()
  })

  it('удалённое модератором сообщение скрывает текст и кнопки, но оставляет пометку', async () => {
    await openChat()
    expect(getByText('Сообщение удалено модератором Кузей')).toBeTruthy()
    expect(getByText('Кузя удалил рекламу')).toBeTruthy()
    expect(queryByText('Заработок от 100000 в день')).toBeNull()
    expect(queryButton('Скрытая кнопка')).toBeNull()
  })

  it('пустой чат дома: «Сообщений пока нет»', async () => {
    history[GROUP.chat_id] = []
    await renderRoute('/dev/chat')
    await waitFor(() => getByText('Сообщений пока нет'))
  })

  it('пока история грузится, показывает заглушки сообщений', async () => {
    vi.spyOn(devChatApi, 'messages').mockReturnValue(new Promise(() => undefined))
    await renderRoute('/dev/chat')
    await waitFor(() => document.querySelectorAll('.max-chat .rounded-2xl').length === 4)
  })

  it('старое сообщение подписывает датой, а не «Вчера»', async () => {
    history[GROUP.chat_id] = [
      message({ id: 'old', text: 'Собрание жильцов', created_at: '2026-10-01T12:00:00+04:00' }),
    ]
    await renderRoute('/dev/chat')
    await waitFor(() => getByText('Собрание жильцов'))
    expect(getByText('1 октября')).toBeTruthy()
  })

  it('новое сообщение из чата появляется без перезагрузки', async () => {
    await openChat()
    const store = useDevChatStore()
    store.messages = {
      ...store.messages,
      [GROUP.chat_id]: [
        ...HISTORY,
        message({ id: 'm5', from: { user_id: 1002, name: 'Ильдар' }, text: 'Завтра поменяют' }),
      ],
    }
    await settle()
    expect(getByText('Завтра поменяют')).toBeTruthy()
  })

  it('ошибка загрузки чатов: показывает причину и пробует снова', async () => {
    vi.spyOn(devChatApi, 'chats').mockRestore()
    vi.spyOn(devChatApi, 'messages').mockRestore()
    await renderRoute('/dev/chat', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    scenario.name = 'default'
    await click('Попробовать ещё раз')
    // в мок-бэкенде один чат дома и пустая история
    await waitFor(() => getByText('Сообщений пока нет'))
    expect(getByText('Ленинского Комсомола, 5 - домовой чат')).toBeTruthy()
  })

  it('кнопка «Назад» возвращает на предыдущий экран', async () => {
    const { router } = await renderRoute('/more')
    await router.push('/dev/chat')
    await waitFor(() => getByText('Спасибо, Кузя!'))
    await click('Назад')
    await waitFor(() => router.currentRoute.value.path === '/more')
  })
})

describe('Эмулятор чата MAX: отправка', () => {
  it('отправляет сообщение от имени жителя, очищает поле и вибрирует', async () => {
    const { max } = await openChat()
    const send = getButton('Отправить')
    expect(send.hasAttribute('disabled')).toBe(true)
    await type(getField('Текст сообщения'), '  Свет так и не починили  ')
    await click(getButton('Отправить'))
    await waitFor(() => vi.mocked(devChatApi.send).mock.calls.length === 1)
    expect(devChatApi.send).toHaveBeenCalledWith(1, 1001, 'Свет так и не починили', [])
    await waitFor(() => getField('Текст сообщения').value === '')
    expect(max.impact).toHaveBeenCalledWith('light')
  })

  it('Enter отправляет сообщение', async () => {
    await openChat()
    const field = getField('Текст сообщения')
    await type(field, 'Кто тут?')
    await new DOMWrapper(field).trigger('keydown', { key: 'Enter' })
    await waitFor(() => vi.mocked(devChatApi.send).mock.calls.length === 1)
    expect(devChatApi.send).toHaveBeenCalledWith(1, 1001, 'Кто тут?', [])
  })

  it('если ответ не пришёл сам, через полторы секунды добирает историю', async () => {
    const delayed: (() => void)[] = []
    const realTimeout = globalThis.setTimeout
    vi.spyOn(globalThis, 'setTimeout').mockImplementation(((fn: () => void, ms?: number) => {
      if (ms === 1500) {
        delayed.push(fn)
        return 0
      }
      return realTimeout(fn, ms)
    }) as typeof setTimeout)
    await openChat()
    await type(getField('Текст сообщения'), 'Ау')
    await click(getButton('Отправить'))
    await waitFor(() => delayed.length === 1)
    // считаем загрузки прямо перед срабатыванием таймера: под нагрузкой первая загрузка может прийти позже
    await settle()
    const loads = vi.mocked(devChatApi.messages).mock.calls.length
    delayed[0]!()
    await waitFor(() => vi.mocked(devChatApi.messages).mock.calls.length > loads)
    expect(devChatApi.messages).toHaveBeenLastCalledWith(GROUP.chat_id)
  })

  it('неудачная отправка: текст остаётся, житель видит ошибку', async () => {
    vi.mocked(devChatApi.send).mockRejectedValue(new Error('Бот не отвечает'))
    await openChat()
    await type(getField('Текст сообщения'), 'Тест')
    await click(getButton('Отправить'))
    await waitFor(() => getByText('Сообщение не отправлено'))
    expect(getByText('Бот не отвечает')).toBeTruthy()
    expect(getField('Текст сообщения').value).toBe('Тест')
  })

  it('меню бота отправляет готовую команду', async () => {
    await openChat()
    const menu = getButton('Меню бота: готовые команды')
    expect(menu.getAttribute('aria-expanded')).toBe('false')
    await click(menu)
    expect(menu.getAttribute('aria-expanded')).toBe('true')
    await click(getButton('Новая заявка'))
    await waitFor(() => vi.mocked(devChatApi.send).mock.calls.length === 1)
    expect(devChatApi.send).toHaveBeenCalledWith(1, 1001, '/новая', [])
    // после отправки меню закрывается
    await waitFor(() => !queryButton('Заявки дома'))
  })
})

describe('Эмулятор чата MAX: фото', () => {
  /** Картинка «загружается» сразу; файл с broken в имени не читается. */
  class FakeImage {
    width = 2560
    height = 1280
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    private url = ''
    get src(): string {
      return this.url
    }
    set src(value: string) {
      this.url = value
      queueMicrotask(() => (value.includes('broken') ? this.onerror?.() : this.onload?.()))
    }
  }

  beforeEach(() => {
    vi.stubGlobal('Image', FakeImage)
    vi.spyOn(URL, 'createObjectURL').mockImplementation((f) => `blob:test/${(f as File).name}`)
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,AA')
  })

  async function attach(...names: string[]): Promise<void> {
    const input = document.querySelector<HTMLInputElement>('.max-composer input[type="file"]')!
    const files = names.map((n) => new File(['x'], n, { type: 'image/jpeg' }))
    Object.defineProperty(input, 'files', { configurable: true, value: files })
    input.dispatchEvent(new Event('change'))
    await settle()
  }

  it('прикладывает фото и отправляет его без текста', async () => {
    await openChat()
    await attach('yama.jpg', 'luzha.jpg')
    await waitFor(() => getByText('Фото: 2'))
    await click(getButton('Отправить'))
    await waitFor(() => vi.mocked(devChatApi.send).mock.calls.length === 1)
    expect(devChatApi.send).toHaveBeenCalledWith(1, 1001, '', [
      'data:image/jpeg;base64,AA',
      'data:image/jpeg;base64,AA',
    ])
    await waitFor(() => !queryByText('Фото: 2'))
  })

  it('больше трёх фото приложить нельзя', async () => {
    await openChat()
    await attach('1.jpg', '2.jpg', '3.jpg', '4.jpg')
    await waitFor(() => getByText('Фото: 3'))
    expect(getButton('Приложить фото').hasAttribute('disabled')).toBe(true)
  })

  it('нечитаемое фото не добавляется, житель видит почему', async () => {
    await openChat()
    await attach('broken.heic')
    await waitFor(() => getByText('Фото не добавлено'))
    expect(getByText('Не удалось прочитать фото')).toBeTruthy()
  })
})

describe('Эмулятор чата MAX: кнопки под сообщением', () => {
  it('кнопка-ответ уходит боту с id сообщения', async () => {
    const { max } = await openChat()
    await click(keyButton('Поддержать'))
    await waitFor(() => vi.mocked(devChatApi.callback).mock.calls.length === 1)
    expect(devChatApi.callback).toHaveBeenCalledWith(1, 1001, 'm2', 'vote:102')
    expect(max.impact).toHaveBeenCalledWith('light')
  })

  it('пока бот обрабатывает нажатие, кнопка недоступна', async () => {
    let finish: () => void = () => undefined
    vi.mocked(devChatApi.callback).mockReturnValue(
      new Promise((resolve) => (finish = () => resolve({ ok: true }))),
    )
    await openChat()
    await click(keyButton('Поддержать'))
    expect(keyButton('Поддержать').hasAttribute('disabled')).toBe(true)
    finish()
    await waitFor(() => !keyButton('Поддержать').hasAttribute('disabled'))
  })

  it('если кнопка не сработала, говорит об этом', async () => {
    vi.mocked(devChatApi.callback).mockRejectedValue(new Error('Бот упал'))
    await openChat()
    await click(keyButton('Поддержать'))
    await waitFor(() => getByText('Кнопка не сработала'))
  })

  it('кнопка-ссылка открывает адрес через MAX', async () => {
    const { max } = await openChat()
    await click(keyButton('Правила дома'))
    expect(max.openLink).toHaveBeenCalledWith('https://example.org/rules')
    expect(devChatApi.callback).not.toHaveBeenCalled()
  })

  it('кнопка мини-приложения открывает нужный экран', async () => {
    const { router } = await openChat()
    await click(keyButton('Открыть заявку'))
    await waitFor(() => router.currentRoute.value.path === '/issues/102')
  })

  it('кнопка мини-приложения с непонятным адресом не уводит с экрана', async () => {
    const { router } = await openChat()
    await click(keyButton('Куда-то не туда'))
    await waitFor(() => getByText('Не знаю, какой раздел открыть'))
    expect(router.currentRoute.value.path).toBe('/dev/chat')
  })
})

describe('Эмулятор чата MAX: меню эмулятора', () => {
  it('переключает на личку с ботом', async () => {
    const { max } = await openChat()
    await click('Меню эмулятора: выбрать чат и жителя')
    await waitFor(() => getByText('личные сообщения с ботом'))
    await click(getByText('Личка с Кузей').closest('.v-list-item')!)
    await waitFor(() => getByText('Вы начали общение с ботом'))
    expect(getByText('Бот')).toBeTruthy()
    expect(useDevChatStore().currentChatId).toBe(DIALOG.chat_id)
    expect(max.selection).toHaveBeenCalled()
  })

  it('внутри MAX не предлагает писать от имени других жителей', async () => {
    await openChat()
    await click('Меню эмулятора: выбрать чат и жителя')
    await waitFor(() => getByText('групповой чат дома'))
    expect(queryByText('Писать как (демо)')).toBeNull()
  })

  it('в браузерном демо пишет от имени выбранного соседа', async () => {
    await renderApp('/dev/chat', { scenario: { inMax: false } })
    await waitFor(() => getByText('Спасибо, Кузя!'))
    await click('Меню эмулятора: выбрать чат и жителя')
    await waitFor(() => getByText('Писать как (демо)'))
    expect(getByText('кв. 45 · администратор')).toBeTruthy()
    await click(getByText('Ильдар Хайруллин').closest('.v-list-item')!)
    await waitFor(() => getByText('Теперь вы: Ильдар'))
    expect(useSessionStore().devUserId).toBe(1002)

    // экран перерисовался под нового жителя: сообщение уходит от его имени
    await waitFor(() => getByText('Спасибо, Кузя!'))
    await type(getField('Текст сообщения'), 'Это Ильдар')
    await click(getButton('Отправить'))
    await waitFor(() => vi.mocked(devChatApi.send).mock.calls.length === 1)
    expect(devChatApi.send).toHaveBeenCalledWith(1, 1002, 'Это Ильдар', [])
  })
})
