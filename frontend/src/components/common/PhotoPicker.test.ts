import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'
import { Toaster } from '@/components/ui/sonner'
import { click, getButton, getByText, settle, textOf, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import PhotoPicker from './PhotoPicker.vue'

function photo(name: string, type = 'image/jpeg'): File {
  return new File([`содержимое ${name}`], name, { type })
}

/** Выбор фото с v-model, как в форме заявки, и тосты рядом. */
async function renderPicker(options: { max?: number; files?: File[] } = {}) {
  const state = reactive({ files: options.files ?? [] })
  const rendered = await renderComponent(
    defineComponent({
      setup: () => () => [
        h(PhotoPicker, {
          max: options.max,
          modelValue: state.files,
          'onUpdate:modelValue': (v: File[]) => (state.files = v),
        }),
        h(Toaster),
      ],
    }),
  )
  return { ...rendered, state }
}

/** Житель выбрал файлы в системном окне: подставляем их в скрытое поле. */
async function choose(input: HTMLInputElement, files: File[]): Promise<void> {
  Object.defineProperty(input, 'files', { configurable: true, value: files })
  input.dispatchEvent(new Event('change'))
  await settle(5)
}

function cameraInput(): HTMLInputElement {
  return document.querySelector('input[capture="environment"]') as HTMLInputElement
}

function galleryInput(): HTMLInputElement {
  return document.querySelector('input[multiple]') as HTMLInputElement
}

function previews(): HTMLImageElement[] {
  return Array.from(document.querySelectorAll<HTMLImageElement>('img[alt^="Фото "]'))
}

describe('Выбор фото', () => {
  it('предлагает камеру и галерею и говорит, сколько ещё можно', async () => {
    await renderPicker()
    expect(getButton('Камера')).toBeTruthy()
    expect(getButton('Галерея')).toBeTruthy()
    expect(getByText(/0 из 5 фото/)).toBeTruthy()
    expect(cameraInput().getAttribute('accept')).toBe('image/*')
  })

  it('кнопки открывают системный выбор: камеру и галерею', async () => {
    await renderPicker()
    const camera = vi.spyOn(cameraInput(), 'click')
    const gallery = vi.spyOn(galleryInput(), 'click')
    await click('Камера')
    await click('Галерея')
    expect(camera).toHaveBeenCalledTimes(1)
    expect(gallery).toHaveBeenCalledTimes(1)
  })

  it('добавляет выбранные фото с превью и отзывается вибро', async () => {
    const { state, max } = await renderPicker()
    await choose(galleryInput(), [photo('a.jpg'), photo('b.png', 'image/png')])
    await waitFor(() => state.files.length === 2)
    expect(state.files.map((f) => f.name)).toEqual(['a.jpg', 'b.png'])
    expect(previews()).toHaveLength(2)
    expect(previews()[0]!.getAttribute('src')).toMatch(/^blob:/)
    expect(textOf(document.querySelector('p.text-muted'))).toContain('2 из 5 фото')
    expect(max.impact).toHaveBeenCalledWith('light')
    // поле очищено: то же фото можно выбрать ещё раз
    expect(galleryInput().value).toBe('')
  })

  it('не берёт файлы, которые не картинки', async () => {
    const { state, max } = await renderPicker()
    await choose(galleryInput(), [photo('протокол.pdf', 'application/pdf')])
    expect(state.files).toHaveLength(0)
    expect(max.impact).not.toHaveBeenCalled()
  })

  it('лишние фото не добавляет и предупреждает о лимите', async () => {
    const { state, max } = await renderPicker({ max: 2, files: [photo('old.jpg')] })
    await choose(cameraInput(), [photo('a.jpg'), photo('b.jpg')])
    await waitFor(() => getByText('Можно добавить не больше 2 фото'))
    expect(state.files.map((f) => f.name)).toEqual(['old.jpg', 'a.jpg'])
    expect(max.notify).toHaveBeenCalledWith('warning')
    // лимит набран: кнопки выключены
    expect(getButton('Камера').hasAttribute('disabled')).toBe(true)
    expect(getButton('Галерея').hasAttribute('disabled')).toBe(true)
  })

  it('крестик убирает фото и освобождает его превью', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL')
    const { state, max } = await renderPicker({ files: [photo('a.jpg'), photo('b.jpg')] })
    expect(previews()).toHaveLength(2)
    const firstUrl = previews()[0]!.getAttribute('src')

    await click('Убрать фото 1')
    await waitFor(() => state.files.length === 1)
    expect(state.files[0]!.name).toBe('b.jpg')
    expect(max.selection).toHaveBeenCalled()
    expect(revoke).toHaveBeenCalledWith(firstUrl)
    expect(previews()).toHaveLength(1)
  })

  it('при уходе с экрана освобождает все превью', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL')
    const { wrapper } = await renderPicker({ files: [photo('a.jpg'), photo('b.jpg')] })
    wrapper.unmount()
    expect(revoke).toHaveBeenCalledTimes(2)
  })
})
