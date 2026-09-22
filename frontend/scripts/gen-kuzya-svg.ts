/**
 * Генерирует статичные public/kuzya.svg (логотип, favicon) и public/kuzya-avatar.svg
 * (аватар бота 512x512) из той же геометрии, что и компонент KuzyaMascot.
 * Запуск: node scripts/gen-kuzya-svg.ts
 */
import { writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  PALETTES,
  defsMarkup,
  staticFigure,
  type KuzyaIds,
} from '../src/components/kuzya/geometry.ts'

const ids: KuzyaIds = { dots: 'kzDots', knit: 'kzKnit', skin: 'kzSkin', glow: 'kzGlow' }
const defs = `<defs>${defsMarkup(ids, PALETTES.happy, '#FFC94D')}
    <radialGradient id="kzBg" cx="50%" cy="40%" r="70%">
      <stop offset="0%" stop-color="#FFF4E3"/>
      <stop offset="100%" stop-color="#FFD9A8"/>
    </radialGradient>
  </defs>`
const figure = staticFigure(ids, 'happy')

const logo = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 220" width="200" height="220">
<title>Домовой Кузя</title>${defs}
<g>${figure}
</g>
</svg>
`

const avatar = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
<title>Домовой Кузя</title>${defs}
<circle cx="256" cy="256" r="256" fill="url(#kzBg)"/>
<g transform="translate(61 30) scale(1.95)">${figure}
</g>
</svg>
`

const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public')
writeFileSync(resolve(publicDir, 'kuzya.svg'), logo)
writeFileSync(resolve(publicDir, 'kuzya-avatar.svg'), avatar)
console.warn('kuzya.svg и kuzya-avatar.svg обновлены')
