import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { issuesApi } from '@/api/endpoints'
import {
  click,
  getButton,
  getByText,
  getField,
  queryByText,
  settle,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute } from '@/test/harness'

/** Описание без похожих заявок в мок-доме: категория «Другое». */
const OTHER_TEXT = 'Сломался домофон у входа, не открывается'
/** Описание про крышу: в доме уже есть заявка 101 «Течёт крыша над 9 этажом». */
const ROOF_TEXT = 'На девятом этаже течёт крыша после дождя'

// URL.createObjectURL из jsdom-окружения Vitest падает на файлах jsdom 30: подменяем адрес превью
beforeEach(() => {
  let seq = 0
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:test/${++seq}`)
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})

const description = () => getField('Описание проблемы')

/** Кнопка «Дальше» внизу первого шага. */
const nextButton = () => getButton(/^Дальше/)

/** Выбор фото из галереи: подставляем файлы в скрытый input и сообщаем об изменении. */
async function pickPhoto(name = 'roof.jpg'): Promise<void> {
  const input = document.querySelectorAll<HTMLInputElement>('input[type="file"]')[1]!
  const file = new File(['photo'], name, { type: 'image/jpeg' })
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  input.dispatchEvent(new Event('change'))
  await settle()
}

describe('Новая заявка: шаг описания', () => {
  it('без описания дальше не пускает и просит описать проблему', async () => {
    await renderRoute('/issues/new')
    expect(getByText('Что случилось?')).toBeTruthy()
    expect(getByText('Опишите проблему, чтобы продолжить')).toBeTruthy()
    expect(nextButton().hasAttribute('disabled')).toBe(true)
  })

  it('слишком короткое описание: подсказка, сколько букв не хватает', async () => {
    await renderRoute('/issues/new')
    await type(description(), 'течёт')
    await waitFor(() => getByText('Напишите чуть подробнее: ещё 5 букв'))
    expect(nextButton().hasAttribute('disabled')).toBe(true)
  })

  it('Кузя по описанию понимает, кто отвечает и какой срок', async () => {
    await renderRoute('/issues/new')
    await type(description(), ROOF_TEXT)
    await waitFor(() => getByText(/Похоже, это Кровля/), 3000)
    expect(getByText(/Отвечает управляющая компания «Уютный дом», срок 24 часа/)).toBeTruthy()
    expect(nextButton().hasAttribute('disabled')).toBe(false)
  })

  it('пока форма заполнена, MAX спрашивает подтверждение перед закрытием', async () => {
    const { max } = await renderRoute('/issues/new')
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(false)
    await type(description(), OTHER_TEXT)
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(true)
  })

  it('фото можно добавить и убрать', async () => {
    const { max } = await renderRoute('/issues/new')
    await pickPhoto()
    await waitFor(() => getByText(/1 из 5 фото/))
    expect(document.querySelector('img[alt="Фото 1"]')).not.toBeNull()
    expect(max.impact).toHaveBeenCalledWith('light')
    await click('Убрать фото 1')
    await waitFor(() => getByText(/0 из 5 фото/))
    expect(max.selection).toHaveBeenCalled()
  })
})

describe('Новая заявка: похожие заявки', () => {
  it('если о проблеме уже сообщили, предлагает поддержать соседа', async () => {
    const { router, max } = await renderRoute('/issues/new')
    await type(description(), ROOF_TEXT)
    await click(nextButton())
    await waitFor(() => getByText('Похоже, об этом уже сообщили'))
    expect(getByText('Течёт крыша над 9 этажом')).toBeTruthy()
    expect(getByText(/Собираем голоса · 4 из 6 голосов/)).toBeTruthy()

    await click('Поддержать эту заявку')
    await waitFor(() => router.currentRoute.value.path === '/issues/101')
    await waitFor(() => getByText('Голос учтён'))
    expect(max.impact).toHaveBeenCalledWith('medium')
  })

  it('если голос за похожую заявку не прошёл, остаётся на месте и сообщает', async () => {
    vi.spyOn(issuesApi, 'vote').mockRejectedValue(
      new ApiError('http', 409, 'Голосование уже закончилось'),
    )
    const { router } = await renderRoute('/issues/new')
    await type(description(), ROOF_TEXT)
    await click(nextButton())
    await waitFor(() => getButton('Поддержать эту заявку'))
    await click('Поддержать эту заявку')
    await waitFor(() => getByText('Не удалось проголосовать'))
    expect(router.currentRoute.value.path).toBe('/issues/new')
  })

  it('«у меня другая проблема» ведёт ко второму шагу', async () => {
    await renderRoute('/issues/new')
    await type(description(), ROOF_TEXT)
    await click(nextButton())
    await waitFor(() => getButton('Нет, у меня другая проблема'))
    await click('Нет, у меня другая проблема')
    await waitFor(() => getByText('Почти готово'))
  })

  it('если житель уже поддержал похожую заявку, новую создавать не предлагает', async () => {
    const { router } = await renderRoute('/issues/new')
    await type(description(), 'В подъезде темно, не горит свет')
    await click(nextButton())
    await waitFor(() => getByText(/Вы уже поддержали эту заявку, новую создавать не нужно/))
    expect(getByText('Не горит свет в подъезде 3')).toBeTruthy()
    await click('Открыть заявку')
    await waitFor(() => router.currentRoute.value.path === '/issues/102')
  })

  it('уже отправленную похожую заявку предлагает посмотреть', async () => {
    await renderRoute('/issues/new')
    await type(description(), 'Лифт застрял и не едет никуда')
    await click(nextButton())
    await waitFor(() => getButton('Посмотреть, что с заявкой'))
    expect(getByText('Не работает лифт в подъезде 1')).toBeTruthy()
  })
})

describe('Новая заявка: отправка', () => {
  it('без похожих заявок сразу второй шаг, после отправки - благодарность и ссылка на заявку', async () => {
    const { router, max } = await renderRoute('/issues/new')
    await type(description(), OTHER_TEXT)
    await click(nextButton())
    await waitFor(() => getByText('Почти готово'))
    expect(queryByText('Похоже, об этом уже сообщили')).toBeNull()
    expect(getByText(OTHER_TEXT)).toBeTruthy()

    await type('Где именно?', 'Подъезд 1')
    await type('Короткий заголовок', 'Сломан домофон')
    await click('Отправить')
    await waitFor(() => getByText('Спасибо! Кузя всё записал'))
    expect(
      getByText(/Нужно 6 голосов, и обращение уйдёт в управляющую компанию «Уютный дом»/),
    ).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('success')
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(false)

    await click('Открыть заявку')
    await waitFor(() => router.currentRoute.value.path === '/issues/1000')
    await waitFor(() => getByText('Сломан домофон'))
    expect(getByText('Подъезд 1')).toBeTruthy()
  })

  it('на втором шаге видно, сколько фото уйдёт, и можно вернуться к описанию', async () => {
    await renderRoute('/issues/new')
    await type(description(), OTHER_TEXT)
    await pickPhoto()
    await click(nextButton())
    await waitFor(() => getByText('Почти готово'))
    expect(getByText('1 фото')).toBeTruthy()
    await click('Назад к описанию')
    await waitFor(() => getByText('Что случилось?'))
    expect((description() as HTMLTextAreaElement).value).toBe(OTHER_TEXT)
  })

  it('заявка с фото уходит с фото и без заголовка получает его от Кузи', async () => {
    const create = vi.spyOn(issuesApi, 'create')
    await renderRoute('/issues/new')
    await type(description(), OTHER_TEXT)
    await pickPhoto('door.jpg')
    await click(nextButton())
    await waitFor(() => getByText('Почти готово'))
    await click('Отправить')
    await waitFor(() => getByText('Спасибо! Кузя всё записал'))
    const form = create.mock.calls[0]![0]
    expect(form.get('description')).toBe(OTHER_TEXT)
    expect(form.get('title')).toBeNull()
    expect((form.getAll('photos')[0] as File).name).toBe('door.jpg')
  })

  it('если отправка не удалась, сообщает и оставляет заполненную форму', async () => {
    vi.spyOn(issuesApi, 'create').mockRejectedValue(
      new ApiError('http', 500, 'Кузя споткнулся на сервере. Попробуйте ещё раз'),
    )
    await renderRoute('/issues/new')
    await type(description(), OTHER_TEXT)
    await click(nextButton())
    await waitFor(() => getByText('Почти готово'))
    await click('Отправить')
    await waitFor(() => getByText('Не удалось отправить'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    expect(getButton('Отправить')).toBeTruthy()
    expect(queryByText('Спасибо! Кузя всё записал')).toBeNull()
  })
})
