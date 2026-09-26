import type { KuzyaMood } from './mood'

export type SpriteLayer = 'body' | 'head' | 'lids'

// Только URL: сами картинки грузятся, когда поза впервые появляется на экране.
const files = import.meta.glob<string>('./sprites/*.webp', {
  eager: true,
  query: '?url',
  import: 'default',
})

export function spriteUrl(mood: KuzyaMood, layer: SpriteLayer): string | undefined {
  return files[`./sprites/${mood}-${layer}.webp`]
}

/** Догружает и декодирует слои позы, чтобы смена позы не мигала пустым кадром. */
export async function preloadPose(mood: KuzyaMood): Promise<void> {
  const urls = (['body', 'head', 'lids'] as const)
    .map((layer) => spriteUrl(mood, layer))
    .filter((url): url is string => Boolean(url))
  await Promise.all(
    urls.map((url) => {
      const img = new Image()
      img.src = url
      // decode есть во всех браузерах, но не в jsdom
      return typeof img.decode === 'function' ? img.decode().catch(() => undefined) : undefined
    }),
  )
}
