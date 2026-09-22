/**
 * Геометрия маскота «Домовой Кузя»: лохматая соломенная шевелюра, большие зелёные глаза,
 * красная рубаха в горошек с крупной пуговицей, валенки и зелёный сундучок.
 * Части собираются в SVG-разметку строками, поэтому один и тот же код используют
 * компонент KuzyaMascot и scripts/gen-kuzya-svg.ts (логотип и аватар бота).
 * Файл без зависимостей. Разметка статична и не содержит пользовательских данных.
 */

export type KuzyaMood = 'happy' | 'ok' | 'worried' | 'sad' | 'alarm'

export interface KuzyaPalette {
  skin: string
  skinShade: string
  shirt: string
  shirtDark: string
  hair: string
  hairShade: string
  hairLight: string
  cheek: string
}

export const PALETTES: Record<KuzyaMood, KuzyaPalette> = {
  happy: {
    skin: '#FFF6EE',
    skinShade: '#EFD9C7',
    shirt: '#D8322B',
    shirtDark: '#A91F1A',
    hair: '#D9C499',
    hairShade: '#B09669',
    hairLight: '#EEDFBC',
    cheek: '#F29C95',
  },
  ok: {
    skin: '#FDF4EC',
    skinShade: '#ECD6C4',
    shirt: '#CF3530',
    shirtDark: '#A2221D',
    hair: '#D6C299',
    hairShade: '#AD956A',
    hairLight: '#EBDDBB',
    cheek: '#EFA39C',
  },
  worried: {
    skin: '#FBF2EA',
    skinShade: '#E9D4C3',
    shirt: '#C9403A',
    shirtDark: '#9E2A25',
    hair: '#D3C19C',
    hairShade: '#AA946D',
    hairLight: '#E8DBBD',
    cheek: '#E9ABA3',
  },
  sad: {
    skin: '#F5EEE8',
    skinShade: '#DDD0C5',
    shirt: '#AE4C47',
    shirtDark: '#833430',
    hair: '#CBBEA3',
    hairShade: '#A39479',
    hairLight: '#E0D7C4',
    cheek: '#DDB2AB',
  },
  alarm: {
    skin: '#FFF4EB',
    skinShade: '#F1D7C3',
    shirt: '#E02A22',
    shirtDark: '#AE1B15',
    hair: '#DDC698',
    hairShade: '#B49867',
    hairLight: '#F0E0BA',
    cheek: '#F58F86',
  },
}

export const INK = '#2B1A12'
const EYE_GREEN = '#3D9A4C'
const EYE_DARK = '#1E5E2B'
const GOLD = '#D8A93B'
const GOLD_DARK = '#A9812A'

export interface Face {
  browLeft: string
  browRight: string
  mouth: string
  mouthFilled: boolean
  tooth: boolean
  pupilDx: number
  pupilDy: number
}

export const FACES: Record<KuzyaMood, Face> = {
  happy: {
    browLeft: 'M78 84 Q86 79 94 83',
    browRight: 'M106 83 Q114 79 122 84',
    mouth: 'M89 113 Q100 126 111 113 Q100 117 89 113 Z',
    mouthFilled: true,
    tooth: true,
    pupilDx: 0,
    pupilDy: 0,
  },
  ok: {
    browLeft: 'M78 84 Q86 82 94 83',
    browRight: 'M106 83 Q114 82 122 84',
    mouth: 'M92 116 Q100 121 108 116',
    mouthFilled: false,
    tooth: false,
    pupilDx: 0,
    pupilDy: 1,
  },
  worried: {
    browLeft: 'M78 85 Q86 84 94 79',
    browRight: 'M106 79 Q114 84 122 85',
    mouth: 'M90 118 Q95 114 100 118 Q105 122 110 118',
    mouthFilled: false,
    tooth: false,
    pupilDx: -1.5,
    pupilDy: 0,
  },
  sad: {
    browLeft: 'M78 86 Q86 85 94 79',
    browRight: 'M106 79 Q114 85 122 86',
    mouth: 'M91 121 Q100 112 109 121',
    mouthFilled: false,
    tooth: false,
    pupilDx: 0,
    pupilDy: 3,
  },
  alarm: {
    browLeft: 'M78 79 Q86 81 94 85',
    browRight: 'M106 85 Q114 81 122 79',
    mouth: 'M95 117 Q95 110 100 110 Q105 110 105 117 Q105 124 100 124 Q95 124 95 117 Z',
    mouthFilled: true,
    tooth: false,
    pupilDx: 0,
    pupilDy: -1,
  },
}

export interface KuzyaIds {
  dots: string
  knit: string
  skin: string
  glow: string
}

const r1 = (n: number): number => Math.round(n * 10) / 10

const PART_X = 100
const PART_Y = 31

/** Неровный край из кончиков прядей: точки от x0 к x1 с чередованием длины. */
function tips(x0: number, x1: number, yLong: number, yShort: number, step: number): string {
  const dir = x1 > x0 ? 1 : -1
  const pts: string[] = []
  for (let x = x0, i = 0; dir > 0 ? x <= x1 : x >= x1; x += step * dir, i++) {
    // длина прядей гуляет, чтобы край не был «пилой»
    const y = i % 2 === 0 ? yLong + ((i * 7) % 5) : yShort + ((i * 3) % 4)
    pts.push(`L${r1(x)} ${r1(y)}`)
  }
  return pts.join(' ')
}

/**
 * Пушистый край из пучков пряжи: дуга эллипса, каждый сегмент выгнут наружу.
 * Углы в градусах, 0 справа, 90 вниз (как в SVG).
 */
function tuftArc(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  a0: number,
  a1: number,
  n: number,
): string {
  const pt = (deg: number, k = 1): [number, number] => {
    const a = (deg * Math.PI) / 180
    return [r1(cx + Math.cos(a) * rx * k), r1(cy + Math.sin(a) * ry * k)]
  }
  const step = (a1 - a0) / n
  let d = ''
  for (let i = 0; i < n; i++) {
    const [ex, ey] = pt(a0 + step * (i + 1))
    // пучки разной пышности, чтобы край не был ровной «ромашкой»
    const [qx, qy] = pt(a0 + step * (i + 0.5), 1.07 + 0.05 * ((i * 7) % 3))
    d += ` Q${qx} ${qy} ${ex} ${ey}`
  }
  return d
}

/** Нити пряжи: от линии пробора вверх-наружу, затем вниз с лёгкой волной. */
function yarnStrands(side: -1 | 1, count: number, p: KuzyaPalette): string {
  const paths: string[] = []
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1)
    const sx = r1(PART_X + side * (3 + t * 30))
    const sy = r1(PART_Y + t * t * 14)
    const ex = r1(PART_X + side * (22 + t * 50))
    const ey = r1(118 + t * 34 + ((i * 5) % 7))
    const c1x = r1(sx + side * (10 + t * 34))
    const c1y = r1(sy - 6 + t * 4)
    const c2x = r1(ex + side * (6 - ((i * 3) % 5)))
    const c2y = r1(ey - 48)
    const color = i % 3 === 0 ? p.hairLight : p.hairShade
    const width = i % 2 === 0 ? 2.2 : 1.5
    paths.push(
      `<path d="M${sx} ${sy} C${c1x} ${c1y} ${c2x} ${c2y} ${ex} ${ey}" stroke="${color}" stroke-width="${width}"/>`,
    )
  }
  return paths.join('')
}

export function defsMarkup(ids: KuzyaIds, p: KuzyaPalette, glowColor: string): string {
  return `
    <pattern id="${ids.dots}" width="13" height="13" patternUnits="userSpaceOnUse">
      <rect width="13" height="13" fill="${p.shirt}"/>
      <circle cx="3.5" cy="3.5" r="2.1" fill="#FFF6EE"/>
      <circle cx="10" cy="10" r="2.1" fill="#FFF6EE"/>
    </pattern>
    <pattern id="${ids.knit}" width="5" height="5" patternUnits="userSpaceOnUse">
      <rect width="5" height="5" fill="#A8A39C"/>
      <circle cx="2.5" cy="2.5" r="1.1" fill="#8F8A83"/>
    </pattern>
    <radialGradient id="${ids.skin}" cx="42%" cy="38%" r="70%">
      <stop offset="0%" stop-color="${p.skin}"/>
      <stop offset="100%" stop-color="${p.skinShade}"/>
    </radialGradient>
    <radialGradient id="${ids.glow}">
      <stop offset="0%" stop-color="${glowColor}" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="${glowColor}" stop-opacity="0"/>
    </radialGradient>`
}

/** Задняя часть копны: пышная, за головой, расширяется книзу до плеч. */
export function hairBackMarkup(p: KuzyaPalette): string {
  // пушистая дуга от левого бока через макушку к правому, затем бахрома кончиков внизу
  const mass =
    'M34 116' +
    tuftArc(100, 84, 72, 62, 150, 390, 16) +
    ' L174 152 ' +
    tips(174, 26, 158, 147, 6) +
    ' Z'
  return `
    <path d="${mass}" fill="${p.hairShade}"/>
    <path d="M40 112${tuftArc(100, 84, 66, 57, 152, 388, 14)} L166 146 ${tips(166, 34, 150, 141, 7)} Z" fill="${p.hair}"/>
    <g fill="none" stroke-linecap="round" opacity="0.85">
      ${yarnStrands(-1, 16, p)}${yarnStrands(1, 16, p)}
    </g>`
}

export function chestMarkup(): string {
  return `
    <rect x="4" y="182" width="56" height="25" rx="3" fill="#2E7D4F"/>
    <path d="M4 185 Q4 169 32 169 Q60 169 60 185 Z" fill="#3A9B63"/>
    <path d="M4 185 H60" stroke="${GOLD_DARK}" stroke-width="2.5"/>
    <rect x="11" y="171" width="5" height="36" rx="1.5" fill="${GOLD}"/>
    <rect x="48" y="171" width="5" height="36" rx="1.5" fill="${GOLD}"/>
    <rect x="27" y="180" width="10" height="11" rx="2.5" fill="${GOLD}" stroke="${GOLD_DARK}" stroke-width="1.2"/>
    <circle cx="32" cy="184.5" r="1.6" fill="#4A3410"/>
    <path d="M32 185 V188" stroke="#4A3410" stroke-width="1.4"/>`
}

export function bootsMarkup(ids: KuzyaIds): string {
  return `
    <path d="M80 178 H98 V200 Q98 207 90 207 H76 Q70 207 70 202 Q70 197 78 196 Z" fill="url(#${ids.knit})"/>
    <path d="M102 178 H120 V196 Q128 197 128 202 Q128 207 122 207 H108 Q102 207 102 200 Z" fill="url(#${ids.knit})"/>`
}

export function shirtMarkup(ids: KuzyaIds, p: KuzyaPalette): string {
  return `
    <path d="M70 122 Q100 114 130 122 L142 182 Q100 191 58 182 Z" fill="url(#${ids.dots})"/>
    <path d="M58 182 Q100 191 142 182" fill="none" stroke="${p.shirtDark}" stroke-width="3" stroke-linecap="round"/>
    <path d="M86 121 Q100 130 114 121" fill="none" stroke="${p.shirtDark}" stroke-width="3" stroke-linecap="round"/>
    <circle cx="108" cy="142" r="7.5" fill="#EBD5A7" stroke="#C4A265" stroke-width="1.5"/>
    <circle cx="105.6" cy="142" r="1.3" fill="#9C7A3E"/>
    <circle cx="110.4" cy="142" r="1.3" fill="#9C7A3E"/>`
}

/** Левая рука лежит на сундучке. */
export function armLeftMarkup(ids: KuzyaIds, p: KuzyaPalette): string {
  return `
    <path d="M73 130 Q57 146 49 165" fill="none" stroke="url(#${ids.dots})" stroke-width="16" stroke-linecap="round"/>
    <circle cx="47" cy="170" r="7" fill="${p.skin}"/>`
}

/** Правая рука: этой машет. Плечо в левом верхнем углу группы. */
export function armRightMarkup(ids: KuzyaIds, p: KuzyaPalette): string {
  return `
    <path d="M127 130 Q143 146 150 162" fill="none" stroke="url(#${ids.dots})" stroke-width="16" stroke-linecap="round"/>
    <circle cx="152" cy="167" r="7" fill="${p.skin}"/>`
}

export function headMarkup(ids: KuzyaIds, p: KuzyaPalette): string {
  return `
    <ellipse cx="66" cy="98" rx="6" ry="8" fill="${p.skinShade}"/>
    <ellipse cx="134" cy="98" rx="6" ry="8" fill="${p.skinShade}"/>
    <ellipse cx="100" cy="96" rx="34" ry="31" fill="url(#${ids.skin})"/>`
}

/** Пряди поверх лица: боковые локоны закрывают уши, чёлка из прядей падает до бровей. */
export function fringeMarkup(p: KuzyaPalette): string {
  const lock =
    'M76 50 C64 56 58 70 58 88 C58 104 60 120 61 134 ' +
    'L64 126 L66 138 L69 125 L71 131 C71 112 70 96 71 82 C72 68 76 58 80 54 Z'
  const lockStrands = [0, 1, 2]
    .map(
      (i) =>
        `<path d="M${74 - i * 4} ${54 + i * 3} C${63 - i} 66 ${63 + i} 104 ${63 + i * 3} ${130 + (i % 2) * 4}" stroke="${i === 1 ? p.hairLight : p.hairShade}" stroke-width="1.7"/>`,
    )
    .join('')
  const side = `<path d="${lock}" fill="${p.hair}"/><g fill="none" stroke-linecap="round">${lockStrands}</g>`
  const fringe =
    `M68 76 C66 50 82 34 ${PART_X} 33 C118 34 134 50 132 76 ` + tips(132, 68, 81, 70, 4.5) + ' Z'
  const fringeStrands: string[] = []
  for (let x = 71, i = 0; x <= 129; x += 4.5, i++) {
    const off = x - PART_X
    const endY = i % 2 === 0 ? 79 : 72
    fringeStrands.push(
      `<path d="M${r1(PART_X + off * 0.15)} 35 C${r1(PART_X + off * 0.9)} 36 ${r1(x + off * 0.1)} 55 ${r1(x)} ${endY}" stroke="${i % 3 === 0 ? p.hairLight : p.hairShade}" stroke-width="${i % 2 === 0 ? 1.8 : 1.3}"/>`,
    )
  }
  return `
    ${side}
    <g transform="translate(200 0) scale(-1 1)">${side}</g>
    <path d="${fringe}" fill="${p.hair}"/>
    <g fill="none" stroke-linecap="round">${fringeStrands.join('')}</g>
    <path d="M${PART_X} 31 Q${PART_X - 1} 36 ${PART_X} 41" stroke="${p.hairShade}" stroke-width="2" fill="none" stroke-linecap="round"/>`
}

/** Глаза: белки и зелёные радужки. Зрачки двигаются по настроению. */
export function eyesMarkup(face: Face): string {
  const dx = face.pupilDx
  const dy = face.pupilDy
  const eye = (cx: number): string => `
    <ellipse cx="${cx}" cy="97" rx="11" ry="12.5" fill="#FFFDF8"/>
    <g transform="translate(${dx} ${dy})">
      <circle cx="${cx}" cy="98" r="8" fill="${EYE_GREEN}"/>
      <circle cx="${cx}" cy="98" r="8" fill="none" stroke="${EYE_DARK}" stroke-width="1.8"/>
      <circle cx="${cx}" cy="98.5" r="3.8" fill="${INK}"/>
      <circle cx="${cx + 2.6}" cy="94.6" r="2.4" fill="#fff"/>
      <circle cx="${cx - 2.4}" cy="101.5" r="1" fill="#fff" opacity="0.8"/>
    </g>
    <path d="M${cx - 11} 95 Q${cx} 83 ${cx + 11} 95" fill="none" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"/>
    <g stroke="${INK}" stroke-width="1.4" stroke-linecap="round">
      <path d="M${cx - 8} 90.5 L${cx - 11} 86.5"/><path d="M${cx - 3} 88.7 L${cx - 4} 84.2"/>
      <path d="M${cx + 3} 88.7 L${cx + 4} 84.2"/><path d="M${cx + 8} 90.5 L${cx + 11} 86.5"/>
    </g>`
  return eye(86) + eye(114)
}

export function faceMarkup(face: Face, p: KuzyaPalette, mood: KuzyaMood): string {
  const mouthFill = face.mouthFilled ? '#6E2418' : 'none'
  const tooth = face.tooth
    ? '<rect x="97.4" y="114" width="5.2" height="4.6" rx="1" fill="#FFF8EC"/>'
    : ''
  const tear =
    mood === 'sad'
      ? '<path d="M78 108 Q74 116 78 120 Q82 116 78 108 Z" fill="#7EC8F2" opacity="0.9"/>'
      : ''
  const sweat =
    mood === 'alarm' || mood === 'worried'
      ? '<path d="M131 80 Q126 89 131 93 Q136 89 131 80 Z" fill="#7EC8F2" opacity="0.85"/>'
      : ''
  return `
    <ellipse cx="76" cy="110" rx="7" ry="4.5" fill="${p.cheek}" opacity="0.5"/>
    <ellipse cx="124" cy="110" rx="7" ry="4.5" fill="${p.cheek}" opacity="0.5"/>
    <g fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round">
      <path d="${face.browLeft}"/><path d="${face.browRight}"/>
    </g>
    <ellipse cx="100" cy="107" rx="4.6" ry="3.6" fill="#3E2A20"/>
    <path d="${face.mouth}" fill="${mouthFill}" stroke="${INK}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    ${tooth}${tear}${sweat}`
}

/** Полная фигура одной строкой, для статичных SVG. */
export function staticFigure(ids: KuzyaIds, mood: KuzyaMood = 'happy'): string {
  const p = PALETTES[mood]
  const face = FACES[mood]
  return `
    <ellipse cx="100" cy="209" rx="62" ry="7" fill="#000" opacity="0.12"/>
    ${hairBackMarkup(p)}
    ${chestMarkup()}
    ${bootsMarkup(ids)}
    ${shirtMarkup(ids, p)}
    ${armLeftMarkup(ids, p)}
    ${armRightMarkup(ids, p)}
    ${headMarkup(ids, p)}
    ${fringeMarkup(p)}
    ${eyesMarkup(face)}
    ${faceMarkup(face, p, mood)}`
}
