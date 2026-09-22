/**
 * Геометрия и палитры маскота «Домовой Кузя».
 * Файл без зависимостей: его же использует scripts/gen-kuzya-svg.ts для статичных SVG.
 */

export type KuzyaMood = 'happy' | 'ok' | 'worried' | 'sad' | 'alarm'

/** Пушистый контур: эллипс с «кочками» шерсти по краю. */
export function fluffyPath(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  bumps: number,
  depth: number,
): string {
  const round = (n: number) => Math.round(n * 10) / 10
  const point = (angle: number, grow: number) => [
    round(cx + Math.cos(angle) * (rx + grow)),
    round(cy + Math.sin(angle) * (ry + grow)),
  ]
  const step = (Math.PI * 2) / bumps
  const start = -Math.PI / 2
  const [sx, sy] = point(start, 0)
  let d = `M${sx} ${sy}`
  for (let i = 0; i < bumps; i++) {
    const a0 = start + i * step
    const a1 = a0 + step
    const [qx, qy] = point(a0 + step / 2, depth)
    const [ex, ey] = point(a1, 0)
    d += ` Q${qx} ${qy} ${ex} ${ey}`
  }
  return `${d} Z`
}

export const BODY_PATH = fluffyPath(100, 136, 60, 56, 18, 8)

export interface KuzyaPalette {
  fur: string
  furLight: string
  furDark: string
  belly: string
  cheek: string
}

export const PALETTES: Record<KuzyaMood, KuzyaPalette> = {
  happy: {
    fur: '#F2A65A',
    furLight: '#FFC98A',
    furDark: '#D9803F',
    belly: '#FFE3BF',
    cheek: '#FF8A80',
  },
  ok: {
    fur: '#E8A866',
    furLight: '#F9C993',
    furDark: '#C98646',
    belly: '#FBE5C8',
    cheek: '#F9A09A',
  },
  worried: {
    fur: '#E2B274',
    furLight: '#F3D1A0',
    furDark: '#C29252',
    belly: '#F7E8CF',
    cheek: '#F3B0A0',
  },
  sad: {
    fur: '#B8A290',
    furLight: '#D3C2B2',
    furDark: '#957F6C',
    belly: '#E9DED2',
    cheek: '#D8A8A0',
  },
  alarm: {
    fur: '#EF8B64',
    furLight: '#FFB08F',
    furDark: '#C95A3D',
    belly: '#FFDCCB',
    cheek: '#FF6F61',
  },
}

export const ROOF = { main: '#C8553D', dark: '#96392A', window: '#FFE08A' }
export const INK = '#3B2418'

export interface Face {
  browLeft: string
  browRight: string
  mouth: string
  mouthFilled: boolean
  pupilDy: number
  pupilDx: number
}

export const FACES: Record<KuzyaMood, Face> = {
  happy: {
    browLeft: 'M69 101 Q79 93 89 100',
    browRight: 'M111 100 Q121 93 131 101',
    mouth: 'M86 143 Q100 164 114 143 Q100 149 86 143 Z',
    mouthFilled: true,
    pupilDx: 0,
    pupilDy: 0,
  },
  ok: {
    browLeft: 'M70 101 Q79 97 88 100',
    browRight: 'M112 100 Q121 97 130 101',
    mouth: 'M89 146 Q100 154 111 146',
    mouthFilled: false,
    pupilDx: 0,
    pupilDy: 1,
  },
  worried: {
    browLeft: 'M69 103 Q80 101 89 95',
    browRight: 'M111 95 Q120 101 131 103',
    mouth: 'M88 150 Q94 145 100 150 Q106 155 112 150',
    mouthFilled: false,
    pupilDx: -2,
    pupilDy: 0,
  },
  sad: {
    browLeft: 'M69 105 Q80 102 89 95',
    browRight: 'M111 95 Q120 102 131 105',
    mouth: 'M89 154 Q100 143 111 154',
    mouthFilled: false,
    pupilDx: 0,
    pupilDy: 4,
  },
  alarm: {
    browLeft: 'M69 95 Q80 97 90 103',
    browRight: 'M110 103 Q120 97 131 95',
    mouth: 'M93 151 Q93 141 100 141 Q107 141 107 151 Q107 160 100 160 Q93 160 93 151 Z',
    mouthFilled: true,
    pupilDx: 0,
    pupilDy: -1,
  },
}
