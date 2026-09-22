export const MAX_PHOTOS = 5
const MAX_SIDE = 1600
const JPEG_QUALITY = 0.82

/**
 * Сжимает фото до ~1600 px по длинной стороне в JPEG.
 * Если браузер не справился (HEIC и т.п.), отдаёт исходный файл.
 */
export async function compressImage(file: File): Promise<File> {
  if (!file.type.startsWith('image/')) return file
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
    const width = Math.round(bitmap.width * scale)
    const height = Math.round(bitmap.height * scale)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, width, height)
    ctx.drawImage(bitmap, 0, 0, width, height)
    bitmap.close()
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY),
    )
    if (!blob) return file
    if (blob.size >= file.size && scale === 1 && file.type === 'image/jpeg') return file
    const name = file.name.replace(/\.[^.]+$/, '') || 'photo'
    return new File([blob], `${name}.jpg`, { type: 'image/jpeg', lastModified: Date.now() })
  } catch {
    return file
  }
}
