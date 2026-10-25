import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  backButton,
  copyText,
  getInitData,
  getPlatform,
  getStartParam,
  haptic,
  isInMax,
  openLink,
  openMaxLink,
  ready,
  setClosingConfirmation,
  shareContent,
  type MaxWebApp,
} from './bridge'
import { deepLinkToPath, issueDeepLink } from './deeplink'

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

describe('мост MAX: что ещё умеет обёртка', () => {
  it('сообщает MAX о готовности только внутри MAX', () => {
    const appReady = vi.fn()
    setWebApp({ initData: '', ready: appReady })
    ready()
    expect(appReady).not.toHaveBeenCalled()
    setWebApp({ initData: 'x=1', ready: appReady })
    ready()
    expect(appReady).toHaveBeenCalledTimes(1)
  })

  it('платформа по умолчанию - веб', () => {
    expect(getPlatform()).toBe('web')
    setWebApp({ initData: 'x=1', platform: 'android' })
    expect(getPlatform()).toBe('android')
  })

  it('читает ?start_param= из адреса и пустой start_param внутри MAX', () => {
    window.history.replaceState(null, '', '/?start_param=listing_2')
    expect(getStartParam()).toBe('listing_2')
    setWebApp({ initData: 'x=1', initDataUnsafe: {} })
    expect(getStartParam()).toBeNull()
  })

  it('вибрирует уведомлением и выбором на телефоне', () => {
    const notificationOccurred = vi.fn()
    const selectionChanged = vi.fn()
    setWebApp({
      initData: 'x=1',
      platform: 'android',
      HapticFeedback: { impactOccurred: vi.fn(), notificationOccurred, selectionChanged },
    })
    haptic.notify('success')
    haptic.selection()
    haptic.impact()
    expect(notificationOccurred).toHaveBeenCalledWith('success')
    expect(selectionChanged).toHaveBeenCalled()
  })

  it('в браузере вибро не вызывается вовсе', () => {
    const notificationOccurred = vi.fn()
    setWebApp({ initData: '', HapticFeedback: { impactOccurred: vi.fn(), notificationOccurred } })
    haptic.notify('error')
    haptic.selection()
    expect(notificationOccurred).not.toHaveBeenCalled()
  })

  it('сбой моста не роняет приложение, а пишет предупреждение', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    setWebApp({
      initData: 'x=1',
      platform: 'ios',
      HapticFeedback: {
        impactOccurred: () => {
          throw new Error('bridge is gone')
        },
        notificationOccurred: vi.fn(),
      },
    })
    expect(() => haptic.impact('rigid')).not.toThrow()
    expect(warn).toHaveBeenCalledWith('[max-bridge]', expect.any(Error))
  })
})

describe('системная кнопка «Назад»', () => {
  function withBackButton() {
    const handlers = new Set<() => void>()
    const button = {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn((cb: () => void) => handlers.add(cb)),
      offClick: vi.fn((cb: () => void) => handlers.delete(cb)),
    }
    setWebApp({ initData: 'x=1', BackButton: button })
    return { button, press: () => handlers.forEach((cb) => cb()) }
  }

  it('показывает кнопку и заменяет старый обработчик новым', () => {
    const { button, press } = withBackButton()
    const first = vi.fn()
    const second = vi.fn()
    backButton.show(first)
    backButton.show(second)
    expect(button.show).toHaveBeenCalledTimes(2)
    expect(button.offClick).toHaveBeenCalledWith(first)
    press()
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('прячет кнопку и снимает обработчик', () => {
    const { button, press } = withBackButton()
    const onBack = vi.fn()
    backButton.show(onBack)
    backButton.hide()
    backButton.hide()
    expect(button.hide).toHaveBeenCalledTimes(2)
    press()
    expect(onBack).not.toHaveBeenCalled()
  })

  it('вне MAX кнопки нет', () => {
    setWebApp({ initData: '' })
    expect(() => {
      backButton.show(vi.fn())
      backButton.hide()
    }).not.toThrow()
  })
})

describe('ссылки, «поделиться» и копирование', () => {
  it('ссылки на MAX открывает внутри MAX, иначе в новой вкладке', () => {
    const maxOpen = vi.fn()
    setWebApp({ initData: 'x=1', openMaxLink: maxOpen })
    openMaxLink('https://max.ru/domovoy_kuzya_bot')
    expect(maxOpen).toHaveBeenCalledWith('https://max.ru/domovoy_kuzya_bot')

    const winOpen = vi.spyOn(window, 'open').mockReturnValue(null)
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    setWebApp({
      initData: 'x=1',
      openMaxLink: () => {
        throw new Error('старый клиент')
      },
    })
    openMaxLink('https://max.ru/x')
    expect(winOpen).toHaveBeenCalledWith('https://max.ru/x', '_blank', 'noopener,noreferrer')
  })

  it('внутри MAX делится через MAX', async () => {
    const shareMaxContent = vi.fn()
    setWebApp({ initData: 'x=1', shareMaxContent })
    await expect(shareContent('Жалоба', 'https://max.ru/x')).resolves.toBe('shared')
    expect(shareMaxContent).toHaveBeenCalledWith('Жалоба', 'https://max.ru/x')

    const share = vi.fn()
    setWebApp({ initData: 'x=1', shareContent: share })
    await expect(shareContent('Жалоба')).resolves.toBe('shared')
    expect(share).toHaveBeenCalledWith('Жалоба', undefined)
  })

  it('в браузере делится через системное меню телефона', async () => {
    const share = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', { share })
    await expect(shareContent('Жалоба', 'https://x.ru')).resolves.toBe('shared')
    expect(share).toHaveBeenCalledWith({ text: 'Жалоба', url: 'https://x.ru' })
  })

  it('житель закрыл меню «поделиться» - ничего не копируем', async () => {
    const share = vi.fn(async () => {
      throw new DOMException('cancel', 'AbortError')
    })
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', { share, clipboard: { writeText } })
    await expect(shareContent('Жалоба')).resolves.toBe('failed')
    expect(writeText).not.toHaveBeenCalled()
  })

  it('без «поделиться» копирует текст со ссылкой в буфер', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', {
      share: vi.fn(async () => {
        throw new Error('не разрешено')
      }),
      clipboard: { writeText },
    })
    await expect(shareContent('Жалоба', 'https://x.ru')).resolves.toBe('copied')
    expect(writeText).toHaveBeenCalledWith('Жалоба\nhttps://x.ru')
  })

  it('без буфера обмена копирует старым способом, а если и он не смог - сообщает', async () => {
    vi.stubGlobal('navigator', {})
    const execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand })
    await expect(copyText('Текст обращения')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()

    execCommand.mockImplementation(() => {
      throw new Error('запрещено')
    })
    await expect(shareContent('Жалоба')).resolves.toBe('failed')
    Reflect.deleteProperty(document, 'execCommand')
  })
})

describe('подтверждение закрытия', () => {
  it('включает и выключает вопрос перед закрытием внутри MAX', () => {
    const enable = vi.fn()
    const disable = vi.fn()
    setWebApp({
      initData: 'x=1',
      enableClosingConfirmation: enable,
      disableClosingConfirmation: disable,
    })
    setClosingConfirmation(true)
    setClosingConfirmation(false)
    expect(enable).toHaveBeenCalledTimes(1)
    expect(disable).toHaveBeenCalledTimes(1)
  })

  it('вне MAX ничего не делает', () => {
    const enable = vi.fn()
    setWebApp({ initData: '', enableClosingConfirmation: enable })
    setClosingConfirmation(true)
    expect(enable).not.toHaveBeenCalled()
  })
})

describe('диплинки', () => {
  it('ссылка на заявку в MAX, если известен ник бота', () => {
    expect(issueDeepLink(5, 'domovoy_kuzya_bot')).toBe(
      'https://max.ru/domovoy_kuzya_bot?startapp=issue_5',
    )
    expect(issueDeepLink(5, null)).toBeNull()
  })

  it.each([
    ['safety', '/more/safety'],
    ['shelters', '/more/safety'],
    ['issues', '/issues'],
    ['events', '/events'],
    ['market', '/market'],
    ['listings', '/market'],
    ['achievements', '/more/achievements'],
    ['house', '/more/house'],
    ['people', '/people'],
    ['  home ', '/'],
  ])('раздел %s открывает %s', (param, path) => {
    expect(deepLinkToPath(param)).toBe(path)
  })

  it('слишком длинный номер и пустая строка не принимаются', () => {
    expect(deepLinkToPath('issue_1234567890')).toBeNull()
    expect(deepLinkToPath('')).toBeNull()
  })
})
