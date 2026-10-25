import { describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { click, getByText, settle, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import PhotoCarousel from './PhotoCarousel.vue'

const PHOTOS = ['/demo/a.jpg', '/demo/b.jpg', '/demo/c.jpg']

function track(): HTMLElement {
  return document.querySelector('.photo-carousel') as HTMLElement
}

function images(): HTMLImageElement[] {
  return Array.from(document.querySelectorAll<HTMLImageElement>('.photo-carousel img'))
}

function dots(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('.photo-carousel__dot'))
}

/** В jsdom у ленты нет размеров: задаём ширину кадра вручную. */
function giveWidth(el: HTMLElement, width: number): void {
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: width })
}

describe('Лента фото', () => {
  it('подписывает каждое фото для диктора и грузит первое сразу', async () => {
    await renderComponent(PhotoCarousel, { props: { photos: PHOTOS, alt: 'Течёт крыша' } })
    expect(track().getAttribute('role')).toBe('list')
    expect(track().getAttribute('aria-label')).toBe('Фото: Течёт крыша')
    expect(track().hasAttribute('tabindex')).toBe(false)
    expect(images().map((i) => i.getAttribute('alt'))).toEqual([
      'Течёт крыша, фото 1 из 3',
      'Течёт крыша, фото 2 из 3',
      'Течёт крыша, фото 3 из 3',
    ])
    expect(images().map((i) => i.getAttribute('loading'))).toEqual(['eager', 'lazy', 'lazy'])
    expect(dots()).toHaveLength(3)
    expect(dots()[0]!.className).toContain('photo-carousel__dot--on')
  })

  it('в галерее ленту можно листать с клавиатуры', async () => {
    await renderComponent(PhotoCarousel, {
      props: { photos: PHOTOS, alt: 'Субботник', focusable: true },
    })
    expect(track().getAttribute('tabindex')).toBe('0')
  })

  it('одно фото показывает без точек', async () => {
    await renderComponent(PhotoCarousel, { props: { photos: ['/demo/a.jpg'], alt: 'Лифт' } })
    expect(images()).toHaveLength(1)
    expect(dots()).toHaveLength(0)
  })

  it('без фото показывает то, что передали вместо них', async () => {
    await renderComponent(PhotoCarousel, {
      props: { photos: [], alt: 'Коляска' },
      slots: { default: () => h('span', 'Значок категории') },
    })
    expect(track()).toBeNull()
    expect(getByText('Значок категории')).toBeTruthy()
  })

  it('нажатие на фото сообщает его номер в исходном списке', async () => {
    const { wrapper } = await renderComponent(PhotoCarousel, {
      props: { photos: PHOTOS, alt: 'Крыша' },
    })
    await click(images()[2]!)
    expect(wrapper.findComponent(PhotoCarousel).emitted('open')).toEqual([[2]])
  })

  it('пропускает фото, которые не загрузились, а без единого - показывает замену', async () => {
    const { wrapper } = await renderComponent(PhotoCarousel, {
      props: { photos: PHOTOS, alt: 'Крыша' },
      slots: { default: () => h('span', 'Значок категории') },
    })
    images()[0]!.dispatchEvent(new Event('error'))
    await waitFor(() => images().length === 2)
    expect(images()[0]!.getAttribute('alt')).toBe('Крыша, фото 1 из 2')
    // номер для открытия считается по исходному списку
    await click(images()[1]!)
    expect(wrapper.findComponent(PhotoCarousel).emitted('open')).toEqual([[2]])

    images().forEach((img) => img.dispatchEvent(new Event('error')))
    await waitFor(() => getByText('Значок категории'))
  })

  it('при перелистывании подсвечивает точку открытого фото', async () => {
    await renderComponent(PhotoCarousel, { props: { photos: PHOTOS, alt: 'Крыша' } })
    // пока ширина неизвестна, ничего не считаем
    track().dispatchEvent(new Event('scroll'))
    await settle()
    expect(dots()[0]!.className).toContain('photo-carousel__dot--on')

    giveWidth(track(), 300)
    track().scrollLeft = 610
    track().dispatchEvent(new Event('scroll'))
    await waitFor(() => dots()[2]!.className.includes('photo-carousel__dot--on'))
    expect(dots()[0]!.className).not.toContain('photo-carousel__dot--on')
  })

  it('нажатие на точку плавно листает к фото', async () => {
    await renderComponent(PhotoCarousel, { props: { photos: PHOTOS, alt: 'Крыша' } })
    giveWidth(track(), 320)
    const scrollTo = vi.fn()
    track().scrollTo = scrollTo
    await click(dots()[1]!)
    expect(scrollTo).toHaveBeenCalledWith({ left: 320, behavior: 'smooth' })
  })
})
