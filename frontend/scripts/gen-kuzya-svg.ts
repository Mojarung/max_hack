/**
 * Генерирует статичные public/kuzya.svg (логотип, favicon) и public/kuzya-avatar.svg
 * (аватар бота 512x512) из той же геометрии, что и компонент KuzyaMascot.
 * Запуск: node scripts/gen-kuzya-svg.ts
 */
import { writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BODY_PATH, FACES, INK, PALETTES, ROOF } from '../src/components/kuzya/geometry.ts'

const p = PALETTES.happy
const f = FACES.happy

const figure = `
  <ellipse cx="100" cy="206" rx="54" ry="8" fill="#000" opacity="0.12"/>
  <g fill="#CFC8C1">
    <circle cx="135" cy="22" r="6" opacity="0.8"/>
    <circle cx="142" cy="9" r="8" opacity="0.55"/>
  </g>
  <ellipse cx="80" cy="192" rx="16" ry="9" fill="${p.furDark}"/>
  <ellipse cx="120" cy="192" rx="16" ry="9" fill="${p.furDark}"/>
  <path d="M31 160 Q39 150 47 160" fill="none" stroke="#6D4C41" stroke-width="3"/>
  <circle cx="39" cy="178" r="20" fill="url(#kzGlow)" opacity="0.5"/>
  <rect x="28" y="162" width="22" height="28" rx="6" fill="#6D4C41"/>
  <rect x="31.5" y="166" width="15" height="19" rx="4" fill="#FFC94D"/>
  <rect x="30" y="188" width="18" height="5" rx="2.5" fill="#5D4037"/>
  <path d="${BODY_PATH}" fill="url(#kzBody)"/>
  <ellipse cx="100" cy="156" rx="34" ry="28" fill="${p.belly}"/>
  <ellipse cx="47" cy="150" rx="11" ry="16" transform="rotate(32 47 150)" fill="${p.fur}"/>
  <ellipse cx="152" cy="146" rx="11" ry="16" transform="rotate(-28 152 146)" fill="${p.fur}"/>
  <ellipse cx="68" cy="140" rx="9" ry="6" fill="${p.cheek}" opacity="0.55"/>
  <ellipse cx="132" cy="140" rx="9" ry="6" fill="${p.cheek}" opacity="0.55"/>
  <ellipse cx="80" cy="123" rx="14" ry="16" fill="#fff"/>
  <ellipse cx="120" cy="123" rx="14" ry="16" fill="#fff"/>
  <circle cx="82" cy="126" r="8.5" fill="${INK}"/>
  <circle cx="122" cy="126" r="8.5" fill="${INK}"/>
  <circle cx="85" cy="122" r="3.2" fill="#fff"/>
  <circle cx="125" cy="122" r="3.2" fill="#fff"/>
  <g fill="none" stroke="${INK}" stroke-width="4" stroke-linecap="round">
    <path d="${f.browLeft}"/>
    <path d="${f.browRight}"/>
  </g>
  <path d="${f.mouth}" fill="#6B2B1C" stroke="${INK}" stroke-width="3.5" stroke-linejoin="round"/>
  <rect x="124" y="40" width="13" height="28" rx="2" fill="${ROOF.dark}"/>
  <rect x="121" y="36" width="19" height="7" rx="2.5" fill="${ROOF.dark}"/>
  <path d="M42 88 L100 36 L158 88 Z" fill="${ROOF.main}" stroke="${ROOF.main}" stroke-width="10" stroke-linejoin="round"/>
  <path d="M44 90 L100 40 L156 90" fill="none" stroke="${ROOF.dark}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
  <circle cx="100" cy="66" r="10" fill="${ROOF.window}" stroke="${ROOF.dark}" stroke-width="3"/>
  <path d="M100 57 V75 M91 66 H109" stroke="${ROOF.dark}" stroke-width="2.5"/>`

const defs = `
  <defs>
    <radialGradient id="kzBody" cx="38%" cy="32%" r="75%">
      <stop offset="0%" stop-color="${p.furLight}"/>
      <stop offset="70%" stop-color="${p.fur}"/>
      <stop offset="100%" stop-color="${p.furDark}"/>
    </radialGradient>
    <radialGradient id="kzGlow">
      <stop offset="0%" stop-color="#FFC94D" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#FFC94D" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="kzBg" cx="50%" cy="40%" r="70%">
      <stop offset="0%" stop-color="#FFF4E3"/>
      <stop offset="100%" stop-color="#FFD9A8"/>
    </radialGradient>
  </defs>`

const logo = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 220" width="200" height="220">
<title>Домовой Кузя</title>${defs}
<g>${figure}
</g>
</svg>
`

const avatar = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
<title>Домовой Кузя</title>${defs}
<circle cx="256" cy="256" r="256" fill="url(#kzBg)"/>
<g transform="translate(61 34) scale(1.95)">${figure}
</g>
</svg>
`

const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public')
writeFileSync(resolve(publicDir, 'kuzya.svg'), logo)
writeFileSync(resolve(publicDir, 'kuzya-avatar.svg'), avatar)
console.warn('kuzya.svg и kuzya-avatar.svg обновлены')
