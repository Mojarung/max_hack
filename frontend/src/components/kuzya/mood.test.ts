import { describe, expect, it } from 'vitest'
import { tapPose, type KuzyaMood } from './mood'
import { POSES } from './sprites'
import { spriteUrl } from './spriteUrl'

describe('tapPose', () => {
  it('cheers up a calm Kuzya with the arms-up pose', () => {
    expect(tapPose('ok')).toBe('happy')
    expect(tapPose('worried')).toBe('happy')
    expect(tapPose('proud')).toBe('happy')
  })

  it('answers an already happy Kuzya with a wink', () => {
    expect(tapPose('happy')).toBe('proud')
  })

  it('keeps Kuzya serious while an issue is overdue or an alert is on', () => {
    expect(tapPose('sad')).toBeNull()
    expect(tapPose('alarm')).toBeNull()
  })
})

describe('sprites', () => {
  const moods = Object.keys(POSES) as KuzyaMood[]

  it('has body and head layers for every mood', () => {
    expect(moods).toHaveLength(6)
    for (const mood of moods) {
      expect(spriteUrl(mood, 'body')).toBeTruthy()
      expect(spriteUrl(mood, 'head')).toBeTruthy()
    }
  })

  it('ships eyelids only for poses that blink', () => {
    for (const mood of moods) {
      expect(Boolean(spriteUrl(mood, 'lids'))).toBe(POSES[mood].blink)
    }
  })
})
