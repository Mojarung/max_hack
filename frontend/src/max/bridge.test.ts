import { afterEach, describe, expect, it, vi } from 'vitest'
import { getInitData, getStartParam, haptic, isInMax, openLink, type MaxWebApp } from './bridge'
import { deepLinkToPath } from './deeplink'

function setWebApp(app: MaxWebApp | undefined): void {
  window.WebApp = app
}

afterEach(() => {
  setWebApp(undefined)
  window.history.replaceState(null, '', '/')
  vi.restoreAllMocks()
})

describe('isInMax', () => {
  it('returns false when WebApp is missing', () => {
    setWebApp(undefined)
    expect(isInMax()).toBe(false)
    expect(getInitData()).toBe('')
  })

  it('treats WebApp with empty initData as mock mode (plain browser)', () => {
    setWebApp({ initData: '', platform: 'web' })
    expect(isInMax()).toBe(false)
  })

  it('treats whitespace-only initData as mock mode', () => {
    setWebApp({ initData: '   ' })
    expect(isInMax()).toBe(false)
  })

  it('detects MAX when initData is present', () => {
    setWebApp({ initData: 'query_id=1&hash=abc', platform: 'android' })
    expect(isInMax()).toBe(true)
    expect(getInitData()).toBe('query_id=1&hash=abc')
  })
})

describe('getStartParam', () => {
  it('reads start_param from initDataUnsafe inside MAX', () => {
    setWebApp({ initData: 'x=1', initDataUnsafe: { start_param: 'issue_5' } })
    expect(getStartParam()).toBe('issue_5')
  })

  it('reads ?startapp= from the URL in mock mode', () => {
    window.history.replaceState(null, '', '/?startapp=event_3')
    expect(getStartParam()).toBe('event_3')
  })

  it('returns null when nothing is passed', () => {
    expect(getStartParam()).toBeNull()
  })
})

describe('guards', () => {
  it('does not call haptics on desktop', () => {
    const impactOccurred = vi.fn()
    setWebApp({
      initData: 'x=1',
      platform: 'desktop',
      HapticFeedback: { impactOccurred, notificationOccurred: vi.fn() },
    })
    haptic.impact('light')
    expect(impactOccurred).not.toHaveBeenCalled()
  })

  it('calls haptics on a phone inside MAX', () => {
    const impactOccurred = vi.fn()
    setWebApp({
      initData: 'x=1',
      platform: 'ios',
      HapticFeedback: { impactOccurred, notificationOccurred: vi.fn() },
    })
    haptic.impact('heavy')
    expect(impactOccurred).toHaveBeenCalledWith('heavy')
  })

  it('opens links via MAX when available and falls back to window.open', () => {
    const maxOpen = vi.fn()
    setWebApp({ initData: 'x=1', openLink: maxOpen })
    openLink('https://yandex.ru/maps')
    expect(maxOpen).toHaveBeenCalledWith('https://yandex.ru/maps')

    setWebApp(undefined)
    const winOpen = vi.spyOn(window, 'open').mockReturnValue(null)
    openLink('https://osm.org')
    expect(winOpen).toHaveBeenCalledWith('https://osm.org', '_blank', 'noopener,noreferrer')
  })
})

describe('deepLinkToPath', () => {
  it.each([
    ['issue_5', '/issues/5'],
    ['event_3', '/events/3'],
    ['listing_2', '/market/2'],
    ['alert', '/more/safety'],
    ['ISSUE_12', '/issues/12'],
    ['announcements', '/announcements'],
    ['documents', '/more/documents'],
    ['house_setup', '/more/house/edit'],
    ['new_issue', '/issues/new'],
  ])('maps %s to %s', (param, path) => {
    expect(deepLinkToPath(param)).toBe(path)
  })

  it('rejects unknown or malformed params', () => {
    expect(deepLinkToPath('issue_')).toBeNull()
    expect(deepLinkToPath('javascript:alert(1)')).toBeNull()
    expect(deepLinkToPath(null)).toBeNull()
  })
})
