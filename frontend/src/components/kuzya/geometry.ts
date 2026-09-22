/**
 * Геометрия маскота «Домовой Кузя» в чиби-пропорциях: огромная кремовая копна из толстых
 * прядей пряжи, смуглое лицо с веснушками, большие зелёные глаза, тёмный носик, красное
 * платье в горошек с пуговицей и серые валенки. Настроение меняет лицо и позу рук.
 *
 * Части собираются в SVG-разметку строками, поэтому один и тот же код используют
 * компонент KuzyaMascot и scripts/gen-kuzya-svg.ts (логотип и аватар бота).
 * Файл без зависимостей. Разметка статична и не содержит пользовательских данных.
 */

export type KuzyaMood = 'happy' | 'ok' | 'worried' | 'sad' | 'alarm' | 'proud'

export const COLORS = {
  hair: '#EFE4C8',
  hairShade: '#D2C199',
  hairLight: '#FBF6E9',
  skin: '#E9BF94',
  skinShade: '#CFA078',
  shirt: '#E0362E',
  shirtDark: '#B3221C',
  boot: '#A9A49F',
  bootDark: '#8A857F',
  button: '#EBD7AE',
  buttonDark: '#C6AA72',
  nose: '#4A2F22',
  ink: '#2B1A12',
  mouth: '#6E2418',
  tongue: '#E8706A',
  eyeGreen: '#3FA34D',
  eyeDark: '#1F6B2C',
  cheek: '#E98A7A',
  tear: '#7EC8F2',
} as const

export interface KuzyaIds {
  dots: string
  felt: string
  skin: string
  glow: string
}

type EyeState = 'open' | 'closed' | 'wink'
type MouthKind = 'smile' | 'laugh' | 'o' | 'frown' | 'grimace'
type Pose = 'down' | 'up' | 'cheeks' | 'clasped' | 'crossed' | 'thumb'

export interface Face {
  eyes: [EyeState, EyeState]
  browLeft: string
  browRight: string
  mouth: MouthKind
  pupilDx: number
  pupilDy: number
  tears: boolean
  pose: Pose
}

export const FACES: Record<KuzyaMood, Face> = {
  ok: {
    eyes: ['open', 'open'],
    browLeft: 'M75 81 Q84 77 93 80',
    browRight: 'M107 80 Q116 77 125 81',
    mouth: 'smile',
    pupilDx: 0,
    pupilDy: 0,
    tears: false,
    pose: 'down',
  },
  happy: {
    eyes: ['closed', 'closed'],
    browLeft: 'M75 79 Q84 74 93 78',
    browRight: 'M107 78 Q116 74 125 79',
    mouth: 'laugh',
    pupilDx: 0,
    pupilDy: 0,
    tears: false,
    pose: 'up',
  },
  proud: {
    eyes: ['open', 'wink'],
    browLeft: 'M75 80 Q84 76 93 79',
    browRight: 'M107 83 Q116 80 125 84',
    mouth: 'smile',
    pupilDx: 1.5,
    pupilDy: 0,
    tears: false,
    pose: 'thumb',
  },
  worried: {
    eyes: ['open', 'open'],
    browLeft: 'M75 76 Q84 70 93 75',
    browRight: 'M107 75 Q116 70 125 76',
    mouth: 'o',
    pupilDx: 0,
    pupilDy: -1,
    tears: false,
    pose: 'cheeks',
  },
  sad: {
    eyes: ['open', 'open'],
    browLeft: 'M75 84 Q84 81 93 76',
    browRight: 'M107 76 Q116 81 125 84',
    mouth: 'frown',
    pupilDx: 0,
    pupilDy: 2.5,
    tears: true,
    pose: 'clasped',
  },
  alarm: {
    eyes: ['open', 'open'],
    browLeft: 'M75 75 Q84 78 93 85',
    browRight: 'M107 85 Q116 78 125 75',
    mouth: 'grimace',
    pupilDx: 0,
    pupilDy: 0,
    tears: false,
    pose: 'crossed',
  },
}

const r1 = (n: number): number => Math.round(n * 10) / 10
/** Детерминированный «шум» в [-1, 1]: пряди не выглядят циркулем, но рисунок стабилен. */
const noise = (k: number): number => Math.sin(k * 12.9898 + 4.1) * 0.9

const HAIR_CX = 100
const HAIR_CY = 82

export function defsMarkup(ids: KuzyaIds, glowColor: string): string {
  const c = COLORS
  return `
    <pattern id="${ids.dots}" width="12" height="12" patternUnits="userSpaceOnUse">
      <rect width="12" height="12" fill="${c.shirt}"/>
      <circle cx="3" cy="3" r="1.9" fill="#FFF3EC"/>
      <circle cx="9" cy="9" r="1.9" fill="#FFF3EC"/>
    </pattern>
    <pattern id="${ids.felt}" width="6" height="6" patternUnits="userSpaceOnUse">
      <rect width="6" height="6" fill="${c.boot}"/>
      <circle cx="1.5" cy="1.5" r="1" fill="${c.bootDark}" opacity="0.7"/>
      <circle cx="4.5" cy="4.5" r="0.8" fill="#C4BFB9" opacity="0.8"/>
    </pattern>
    <radialGradient id="${ids.skin}" cx="45%" cy="38%" r="68%">
      <stop offset="0%" stop-color="${c.skin}"/>
      <stop offset="100%" stop-color="${c.skinShade}"/>
    </radialGradient>
    <radialGradient id="${ids.glow}">
      <stop offset="0%" stop-color="${glowColor}" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="${glowColor}" stop-opacity="0"/>
    </radialGradient>`
}

/** Одна прядь пряжи: от макушки наружу с выпуклостью, боковые ещё и свисают вниз. */
function strand(i: number, n: number, radiusK: number, color: string, width: number): string {
  const t = i / (n - 1)
  const a = ((128 + t * 284) * Math.PI) / 180
  const cos = Math.cos(a)
  const sin = Math.sin(a)
  const hang = Math.max(0, sin)
  const rx = (74 + 6 * noise(i)) * radiusK
  const ry = (66 + 5 * noise(i + 3)) * radiusK
  const sx = HAIR_CX + cos * 9 + 3 * noise(i + 7)
  const sy = 60 + sin * 6
  const ex = HAIR_CX + cos * rx
  const ey = HAIR_CY + sin * ry + hang * 24 * radiusK
  const bulge = 11 * noise(i + 11)
  const px = -sin
  const py = cos
  const c1x = sx + (ex - sx) * 0.4 + px * bulge
  const c1y = sy + (ey - sy) * 0.3 + py * bulge
  const c2x = sx + (ex - sx) * 0.85 - px * bulge * 0.5
  const c2y = sy + (ey - sy) * 0.85 + 7
  return `<path d="M${r1(sx)} ${r1(sy)} C${r1(c1x)} ${r1(c1y)} ${r1(c2x)} ${r1(c2y)} ${r1(ex)} ${r1(ey)}" stroke="${color}" stroke-width="${width}"/>`
}

/** Копна за головой: подложка, слой коротких прядей и слой длинных. */
export function hairBackMarkup(): string {
  const c = COLORS
  const shades = [c.hairShade, c.hair, c.hairLight]
  const short: string[] = []
  const long: string[] = []
  for (let i = 0; i < 34; i++) short.push(strand(i, 34, 0.68, i % 2 ? c.hairShade : c.hair, 5.5))
  for (let i = 0; i < 46; i++) long.push(strand(i, 46, 1, shades[i % 3] ?? c.hair, 4 + (i % 3)))
  return `
    <ellipse cx="${HAIR_CX}" cy="${HAIR_CY}" rx="58" ry="54" fill="${c.hair}"/>
    <ellipse cx="54" cy="118" rx="22" ry="30" fill="${c.hair}"/>
    <ellipse cx="146" cy="118" rx="22" ry="30" fill="${c.hair}"/>
    <g fill="none" stroke-linecap="round">${short.join('')}${long.join('')}</g>`
}

/** Чёлка и боковые пряди поверх лица. */
export function fringeMarkup(): string {
  const c = COLORS
  const parts: string[] = []
  for (let i = 0; i < 13; i++) {
    const ex = 68 + i * 5.3
    const off = ex - HAIR_CX
    const ey = 66 + (i % 3) * 3 + 2 * noise(i)
    const sx = HAIR_CX + off * 0.2
    const color = i % 3 === 1 ? c.hairLight : i % 3 === 2 ? c.hairShade : c.hair
    parts.push(
      `<path d="M${r1(sx)} 46 C${r1(sx + off * 0.6)} 48 ${r1(ex - off * 0.1)} ${r1(ey - 12)} ${r1(ex)} ${r1(ey)}" stroke="${color}" stroke-width="${4.5 + (i % 2)}"/>`,
    )
  }
  const sides: Array<[number, number, number, number]> = [
    [64, 70, 56, 132],
    [70, 66, 62, 142],
    [136, 70, 144, 132],
    [130, 66, 138, 142],
  ]
  for (const [sx, sy, ex, ey] of sides) {
    parts.push(
      `<path d="M${sx} ${sy} C${sx - 6} ${sy + 24} ${ex} ${ey - 26} ${ex} ${ey}" stroke="${c.hair}" stroke-width="5"/>`,
    )
  }
  return `<g fill="none" stroke-linecap="round">${parts.join('')}</g>`
}

export function bootsMarkup(ids: KuzyaIds): string {
  const boot = (x: number): string =>
    `<path d="M${x} 176 h30 v22 q0 10 -10 10 h-13 q-10 0 -10 -10 z" fill="url(#${ids.felt})"/>
     <path d="M${x} 176 h30 v6 h-30 z" fill="${COLORS.bootDark}" opacity="0.35"/>`
  return boot(69) + boot(101)
}

export function dressMarkup(ids: KuzyaIds): string {
  const c = COLORS
  return `
    <path d="M74 124 Q100 118 126 124 L140 178 Q100 187 60 178 Z" fill="url(#${ids.dots})"/>
    <path d="M60 178 Q100 187 140 178" fill="none" stroke="${c.shirtDark}" stroke-width="3" stroke-linecap="round"/>
    <path d="M84 124 Q100 131 116 124" fill="none" stroke="${c.shirtDark}" stroke-width="3" stroke-linecap="round"/>
    <circle cx="100" cy="146" r="8.5" fill="${c.button}" stroke="${c.buttonDark}" stroke-width="1.6"/>
    <circle cx="97" cy="146" r="1.4" fill="${c.buttonDark}"/>
    <circle cx="103" cy="146" r="1.4" fill="${c.buttonDark}"/>`
}

export interface Arms {
  left: string
  right: string
  /** Руки перед лицом или на груди: рисуются после головы. */
  front: boolean
}

function sleeve(ids: KuzyaIds, d: string, hx: number, hy: number, extra = ''): string {
  // тёмный контур отделяет рукав от платья с тем же горошком
  return `
    <path d="${d}" fill="none" stroke="${COLORS.shirtDark}" stroke-width="18" stroke-linecap="round"/>
    <path d="${d}" fill="none" stroke="url(#${ids.dots})" stroke-width="15" stroke-linecap="round"/>
    <circle cx="${hx}" cy="${hy}" r="7" fill="${COLORS.skin}"/>${extra}`
}

/** Позы рук. Правая рука всегда в своей группе: её анимирует взмах по нажатию. */
export function armsMarkup(ids: KuzyaIds, pose: Pose): Arms {
  const s = (d: string, hx: number, hy: number, extra?: string) => sleeve(ids, d, hx, hy, extra)
  switch (pose) {
    case 'up':
      return {
        left: s('M76 128 Q60 118 46 100', 43, 95),
        right: s('M124 128 Q140 118 154 100', 157, 95),
        front: false,
      }
    case 'cheeks':
      return {
        left: s('M76 131 Q64 130 73 113', 76, 108),
        right: s('M124 131 Q136 130 127 113', 124, 108),
        front: true,
      }
    case 'clasped':
      return {
        left: s('M76 131 Q80 158 94 166', 96, 168),
        right: s('M124 131 Q120 158 106 166', 104, 168),
        front: true,
      }
    case 'crossed':
      return {
        left: s('M76 132 Q86 150 128 152', 130, 150),
        right: s('M124 132 Q114 152 72 154', 70, 152),
        front: true,
      }
    case 'thumb':
      return {
        left: s('M76 128 Q60 148 56 168', 55, 174),
        right: s(
          'M124 128 Q142 128 150 112',
          152,
          107,
          `<rect x="149" y="91" width="6.5" height="15" rx="3.2" fill="${COLORS.skin}"/>
           <g stroke="#F2B233" stroke-width="2.5" stroke-linecap="round">
             <path d="M162 96 L168 90"/><path d="M164 104 L172 104"/><path d="M160 88 L163 80"/>
           </g>`,
        ),
        front: false,
      }
    default:
      return {
        left: s('M76 128 Q60 148 56 168', 55, 174),
        right: s('M124 128 Q140 148 144 168', 145, 174),
        front: false,
      }
  }
}

export function headMarkup(ids: KuzyaIds): string {
  const c = COLORS
  return `
    <ellipse cx="100" cy="93" rx="35" ry="33" fill="url(#${ids.skin})"/>
    <ellipse cx="74" cy="110" rx="7.5" ry="4.5" fill="${c.cheek}" opacity="0.45"/>
    <ellipse cx="126" cy="110" rx="7.5" ry="4.5" fill="${c.cheek}" opacity="0.45"/>
    <g fill="${c.skinShade}">
      <circle cx="71" cy="106" r="1"/><circle cx="76" cy="104" r="1"/><circle cx="74" cy="109" r="0.9"/>
      <circle cx="129" cy="106" r="1"/><circle cx="124" cy="104" r="1"/><circle cx="126" cy="109" r="0.9"/>
    </g>
    <ellipse cx="100" cy="108" rx="4.6" ry="3.6" fill="${c.nose}"/>
    <circle cx="98.6" cy="107" r="1" fill="#fff" opacity="0.5"/>`
}

function eye(cx: number, state: EyeState, face: Face, outer: -1 | 1): string {
  const c = COLORS
  const cy = 97
  const lashes = `<g stroke="${c.ink}" stroke-width="1.5" stroke-linecap="round">
      <path d="M${cx + outer * 11} ${cy - 5} L${cx + outer * 14.5} ${cy - 9}"/>
      <path d="M${cx + outer * 8} ${cy - 9} L${cx + outer * 10} ${cy - 13.5}"/>
      <path d="M${cx + outer * 4} ${cy - 11.5} L${cx + outer * 4.5} ${cy - 16}"/>
    </g>`
  if (state !== 'open') {
    // закрытый глаз: дуга вверх (улыбка глазами), у подмигивания чуть ниже
    const lift = state === 'wink' ? 8 : 11
    return `<path d="M${cx - 11} ${cy + 3} Q${cx} ${cy - lift} ${cx + 11} ${cy + 3}" fill="none" stroke="${c.ink}" stroke-width="3.2" stroke-linecap="round"/>${lashes}`
  }
  const dx = face.pupilDx
  const dy = face.pupilDy
  return `
    <ellipse cx="${cx}" cy="${cy}" rx="12.5" ry="13.5" fill="#FFFDF8" stroke="${c.ink}" stroke-width="1.6"/>
    <g transform="translate(${dx} ${dy})">
      <circle cx="${cx}" cy="${cy + 0.5}" r="9" fill="${c.eyeGreen}"/>
      <circle cx="${cx}" cy="${cy + 0.5}" r="9" fill="none" stroke="${c.eyeDark}" stroke-width="2"/>
      <circle cx="${cx}" cy="${cy + 1}" r="4.4" fill="${c.ink}"/>
      <circle cx="${cx + 3.2}" cy="${cy - 3.2}" r="3" fill="#fff"/>
      <circle cx="${cx - 3}" cy="${cy + 4.5}" r="1.2" fill="#fff" opacity="0.85"/>
    </g>
    <path d="M${cx - 12} ${cy - 3} Q${cx} ${cy - 16} ${cx + 12} ${cy - 3}" fill="none" stroke="${c.ink}" stroke-width="2.4" stroke-linecap="round"/>
    ${lashes}`
}

/** Глаза: белки, зелёные радужки, ресницы. Зрачки сдвигаются по настроению. */
export function eyesMarkup(face: Face): string {
  return eye(84, face.eyes[0], face, -1) + eye(116, face.eyes[1], face, 1)
}

function mouthMarkup(kind: MouthKind): string {
  const c = COLORS
  const line = (d: string) =>
    `<path d="${d}" fill="none" stroke="${c.ink}" stroke-width="2.6" stroke-linecap="round"/>`
  const tooth = `<rect x="97.4" y="118" width="5.2" height="4.6" rx="1.1" fill="#FFF8EC" stroke="${c.ink}" stroke-width="0.8"/>`
  switch (kind) {
    case 'laugh':
      return `<path d="M89 114 Q100 131 111 114 Z" fill="${c.mouth}" stroke="${c.ink}" stroke-width="2.4" stroke-linejoin="round"/>
        <ellipse cx="100" cy="123" rx="5" ry="3" fill="${c.tongue}"/>`
    case 'o':
      return `<ellipse cx="100" cy="120" rx="4.6" ry="6.2" fill="${c.mouth}" stroke="${c.ink}" stroke-width="2.2"/>`
    case 'frown':
      return line('M92 123 Q100 115 108 123')
    case 'grimace':
      return line('M91 118 Q100 116 109 118') + tooth
    default:
      return line('M91 117 Q100 125 109 117') + tooth
  }
}

export function faceMarkup(face: Face): string {
  const c = COLORS
  const tears = face.tears
    ? `<path d="M76 110 Q72 118 76 122 Q80 118 76 110 Z" fill="${c.tear}" opacity="0.9"/>
       <path d="M124 110 Q120 118 124 122 Q128 118 124 110 Z" fill="${c.tear}" opacity="0.9"/>`
    : ''
  return `
    <g fill="none" stroke="${c.ink}" stroke-width="2.8" stroke-linecap="round">
      <path d="${face.browLeft}"/><path d="${face.browRight}"/>
    </g>
    ${mouthMarkup(face.mouth)}${tears}`
}

/** Полная фигура одной строкой, для статичных SVG. */
export function staticFigure(ids: KuzyaIds, mood: KuzyaMood = 'ok'): string {
  const face = FACES[mood]
  const arms = armsMarkup(ids, face.pose)
  const armsBlock = `${arms.left}${arms.right}`
  return `
    <ellipse cx="100" cy="210" rx="52" ry="6" fill="#000" opacity="0.12"/>
    ${hairBackMarkup()}
    ${bootsMarkup(ids)}
    ${dressMarkup(ids)}
    ${arms.front ? '' : armsBlock}
    ${headMarkup(ids)}
    ${eyesMarkup(face)}
    ${faceMarkup(face)}
    ${fringeMarkup()}
    ${arms.front ? armsBlock : ''}`
}
