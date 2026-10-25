import { afterEach, describe, expect, it, vi } from 'vitest'
import { compressImage } from './image'

const drawImage = vi.fn()

/** Холст, который «сжимает» фото в блоб заданного размера (null - браузер не смог). */
function stubCanvas(blobSize: number | null, withContext = true): void {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () =>
      (withContext
        ? { fillStyle: '', fillRect: vi.fn(), drawImage }
        : null) as unknown as RenderingContext,
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function toBlob(callback) {
    callback(
      blobSize === null ? null : new Blob([new Uint8Array(blobSize)], { type: 'image/jpeg' }),
    )
  })
}

function stubBitmap(width: number, height: number): ReturnType<typeof vi.fn> {
  const close = vi.fn()
  vi.stubGlobal(
    'createImageBitmap',
    vi.fn(async () => ({ width, height, close })),
  )
  return close
}

const photo = (name: string, type: string, size = 1000) =>
  new File([new Uint8Array(size)], name, { type })

afterEach(() => {
  drawImage.mockClear()
})

describe('сжатие фото перед отправкой', () => {
  it('не трогает файлы, которые не картинки', async () => {
    const pdf = photo('akt.pdf', 'application/pdf')
    await expect(compressImage(pdf)).resolves.toBe(pdf)
  })

  it('большое фото уменьшает до 1600 px по длинной стороне и делает JPEG', async () => {
    const close = stubBitmap(4000, 3000)
    stubCanvas(500)
    const result = await compressImage(photo('roof.png', 'image/png'))
    expect(result.name).toBe('roof.jpg')
    expect(result.type).toBe('image/jpeg')
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 1600, 1200)
    expect(close).toHaveBeenCalled()
  })

  it('маленький JPEG, который не стал легче, отдаёт как есть', async () => {
    stubBitmap(800, 600)
    stubCanvas(5000)
    const original = photo('small.jpeg', 'image/jpeg', 1000)
    await expect(compressImage(original)).resolves.toBe(original)
  })

  it('если браузер не смог сжать, отдаёт исходный файл', async () => {
    const heic = photo('IMG_1.heic', 'image/heic')
    vi.stubGlobal(
      'createImageBitmap',
      vi.fn(async () => {
        throw new Error('формат не поддерживается')
      }),
    )
    await expect(compressImage(heic)).resolves.toBe(heic)

    stubBitmap(100, 100)
    stubCanvas(null)
    const png = photo('a.png', 'image/png')
    await expect(compressImage(png)).resolves.toBe(png)
  })

  it('без 2D-контекста холста отдаёт исходный файл', async () => {
    stubBitmap(100, 100)
    stubCanvas(10, false)
    const png = photo('a.png', 'image/png')
    await expect(compressImage(png)).resolves.toBe(png)
  })

  it('файл без имени получает имя photo.jpg', async () => {
    stubBitmap(100, 100)
    stubCanvas(10)
    const result = await compressImage(photo('.png', 'image/png'))
    expect(result.name).toBe('photo.jpg')
  })
})
