import { describe, expect, it } from 'vitest'
import { click, getButton, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import PhotoGallery from './PhotoGallery.vue'

const PHOTOS = ['/demo/a.jpg', '/demo/b.jpg']

function frame(): HTMLElement | null {
  return document.querySelector('.gallery__frame')
}

function dialogOpen(): boolean {
  return !!document.querySelector('.v-overlay--active .v-carousel')
}

describe('Галерея фото', () => {
  it('без фото ничего не рисует', async () => {
    await renderComponent(PhotoGallery, { props: { photos: [], alt: 'Лифт' } })
    expect(document.querySelector('.gallery')).toBeNull()
  })

  it('показывает кадр нужной высоты с лентой фото', async () => {
    await renderComponent(PhotoGallery, { props: { photos: PHOTOS, alt: 'Лифт', height: 200 } })
    expect(frame()!.style.height).toBe('200px')
    expect(frame()!.querySelector('.photo-carousel')!.getAttribute('tabindex')).toBe('0')
  })

  it('по умолчанию кадр высотой 240px', async () => {
    await renderComponent(PhotoGallery, { props: { photos: PHOTOS, alt: 'Лифт' } })
    expect(frame()!.style.height).toBe('240px')
  })

  it('нажатие на фото открывает его на весь экран, крестик закрывает', async () => {
    await renderComponent(PhotoGallery, { props: { photos: PHOTOS, alt: 'Течёт крыша' } })
    expect(dialogOpen()).toBe(false)

    await click(frame()!.querySelectorAll('img')[1]!)
    await waitFor(() => dialogOpen())
    // открылось именно второе фото
    await waitFor(() => document.querySelector('.v-window-item--active'))
    const items = Array.from(document.querySelectorAll('.v-carousel .v-window-item'))
    expect(items).toHaveLength(2)
    expect(items.indexOf(document.querySelector('.v-window-item--active')!)).toBe(1)
    await waitFor(() => document.querySelector('.v-window-item--active img'))
    expect(document.querySelector('.v-window-item--active img')!.getAttribute('alt')).toBe(
      'Течёт крыша, фото 2',
    )

    await click(getButton('Закрыть фото'))
    await waitFor(() => !dialogOpen())
  })
})
