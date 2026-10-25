import { DOMWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { listingsApi } from '@/api/endpoints'
import {
  click,
  getByText,
  getField,
  queryByText,
  queryField,
  settle,
  textOf,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute } from '@/test/harness'

/** Открыть список категорий и выбрать пункт, как пальцем. */
async function chooseCategory(title: string): Promise<void> {
  const select = getField('Категория').closest('.v-select')!
  await new DOMWrapper(select.querySelector('.v-field')!).trigger('mousedown')
  await settle()
  const item = await waitFor(() =>
    Array.from(document.querySelectorAll('.v-list-item')).find((el) => textOf(el) === title),
  )
  await click(item!)
}

async function pickPhoto(): Promise<void> {
  const input = document.querySelector<HTMLInputElement>('input[type="file"][multiple]')!
  const file = new File(['jpeg'], 'stroller.jpg', { type: 'image/jpeg' })
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  await new DOMWrapper(input).trigger('change')
  await settle()
}

describe('Новое объявление', () => {
  it('пустая форма не публикуется и подсказывает, что заполнить', async () => {
    const { router, max } = await renderRoute('/market/new')
    await click('Опубликовать')
    await waitFor(() => getByText('Проверьте поля формы'))
    expect(getByText('Напишите, что отдаёте или продаёте')).toBeTruthy()
    expect(getByText('Выберите категорию')).toBeTruthy()
    expect(getByText('Укажите цену или включите «Отдам даром»')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('warning')
    expect(router.currentRoute.value.path).toBe('/market/new')
  })

  it('«Отдам даром» убирает цену и обещает метку «Даром»', async () => {
    await renderRoute('/market/new')
    expect(queryField('Цена, ₽')).not.toBeNull()
    await click(getField('Отдам даром'))
    expect(queryField('Цена, ₽')).toBeNull()
    expect(getByText('Соседи увидят метку «Даром». Спасибо за доброе дело!')).toBeTruthy()
  })

  it('публикует вещь с ценой и открывает её страницу', async () => {
    const { router, max } = await renderRoute('/market/new')
    await type('Название', 'Велосипед детский')
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(true)
    await chooseCategory('Детское')
    await type('Цена, ₽', '2 500')
    await type('Описание', 'Колёса 16 дюймов')
    await click('Опубликовать')
    await waitFor(() => router.currentRoute.value.path === '/market/1000')
    await waitFor(() => getByText('Объявление опубликовано'))
    await waitFor(() => getByText('Велосипед детский'))
    expect(getByText(/2\s500 ₽/)).toBeTruthy()
    expect(getByText('Колёса 16 дюймов')).toBeTruthy()
    expect(getByText('Ваше объявление')).toBeTruthy()
    expect(max.closingConfirmation).toHaveBeenLastCalledWith(false)
  })

  it('отдаёт вещь даром вместе с фото', async () => {
    const create = vi.spyOn(listingsApi, 'create')
    const { router } = await renderRoute('/market/new')
    await pickPhoto()
    expect(getByText('1 из 5 фото')).toBeTruthy()
    await type('Название', 'Коляска')
    await chooseCategory('Детское')
    await click(getField('Отдам даром'))
    await click('Опубликовать')
    await waitFor(() => router.currentRoute.value.path === '/market/1000')
    const form = create.mock.calls[0]![0]
    expect(form.get('price')).toBe('0')
    expect(form.get('category')).toBe('kids')
    expect(form.getAll('photos')).toHaveLength(1)
    await waitFor(() => getByText('Даром'))
  })

  it('неверная цена не проходит проверку', async () => {
    await renderRoute('/market/new')
    await type('Название', 'Стол')
    await chooseCategory('Мебель')
    await type('Цена, ₽', 'дорого')
    await click('Опубликовать')
    await waitFor(() => getByText('Укажите цену или включите «Отдам даром»'))
    expect(queryByText('Напишите, что отдаёте или продаёте')).toBeNull()
    expect(queryByText('Выберите категорию')).toBeNull()
  })

  it('если сервер не принял объявление, форма остаётся с введённым', async () => {
    vi.spyOn(listingsApi, 'create').mockRejectedValue(
      new ApiError('http', 413, 'Файл слишком большой'),
    )
    const { router } = await renderRoute('/market/new')
    await type('Название', 'Шкаф')
    await chooseCategory('Мебель')
    await type('Цена, ₽', '1000')
    await click('Опубликовать')
    await waitFor(() => getByText('Не удалось опубликовать'))
    expect(getByText('Файл слишком большой')).toBeTruthy()
    expect(router.currentRoute.value.path).toBe('/market/new')
    expect(getField('Название').value).toBe('Шкаф')
  })
})
