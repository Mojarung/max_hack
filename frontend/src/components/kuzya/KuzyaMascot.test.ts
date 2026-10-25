import { afterEach, describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import { click, settle, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import KuzyaMascot from './KuzyaMascot.vue'
import { preloadPose, spriteUrl } from './spriteUrl'

function kuzya(): HTMLElement {
  const el = document.querySelector<HTMLElement>('.kuzya')
  if (!el) throw new Error('Кузя не нарисован')
  return el
}

/** Включает анимации, как у жителя без настройки «уменьшить движение». */
function enableMotion(): void {
  delete document.documentElement.dataset.motion
}

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
})

describe('Картинки поз Кузи', () => {
  it('у каждой позы есть тело и голова, веки только у моргающих', () => {
    expect(spriteUrl('ok', 'body')).toMatch(/ok-body\.webp/)
    expect(spriteUrl('ok', 'head')).toMatch(/ok-head\.webp/)
    expect(spriteUrl('ok', 'lids')).toMatch(/ok-lids\.webp/)
    expect(spriteUrl('happy', 'lids')).toBeUndefined()
  })

  it('догрузка позы не падает там, где картинки не декодируются', async () => {
    await expect(preloadPose('sad')).resolves.toBeUndefined()
  })
})

describe('Кузя на экране', () => {
  it('рисует позу настроения и подписан для диктора', async () => {
    await renderComponent(KuzyaMascot, { props: { mood: 'ok', size: 120 } })
    const el = kuzya()
    expect(el.tagName).toBe('BUTTON')
    expect(el.getAttribute('aria-label')).toBe('Домовой Кузя спокоен. Нажмите, чтобы поздороваться')
    expect(el.classList.contains('kuzya--ok')).toBe(true)
    expect(el.style.width).toBe('120px')
    const images = Array.from(el.querySelectorAll('img')).map((img) => img.getAttribute('src'))
    expect(images).toEqual([
      spriteUrl('ok', 'body'),
      spriteUrl('ok', 'head'),
      spriteUrl('ok', 'lids'),
    ])
  })

  it('без нажатия это просто картинка с подписью', async () => {
    await renderComponent(KuzyaMascot, { props: { mood: 'sad', interactive: false } })
    const el = kuzya()
    expect(el.tagName).toBe('SPAN')
    expect(el.getAttribute('role')).toBe('img')
    expect(el.getAttribute('aria-label')).toBe('Домовой Кузя грустит')
  })

  it('на нажатие отвечает вибро, сообщает о нажатии и на миг радуется', async () => {
    const { max, wrapper } = await renderComponent(KuzyaMascot, { props: { mood: 'ok' } })
    await click(kuzya())
    expect(max.impact).toHaveBeenCalledWith('light')
    expect(wrapper.findComponent(KuzyaMascot).emitted('tap')).toHaveLength(1)
    await waitFor(() => kuzya().classList.contains('kuzya--happy'))
  })

  it('радостный Кузя на нажатие гордится', async () => {
    await renderComponent(KuzyaMascot, { props: { mood: 'happy' } })
    await click(kuzya())
    await waitFor(() => kuzya().classList.contains('kuzya--proud'))
  })

  it('во время тревоги на нажатие не радуется, а только подпрыгивает', async () => {
    const { max } = await renderComponent(KuzyaMascot, { props: { mood: 'alarm' } })
    await click(kuzya())
    await settle()
    expect(max.impact).toHaveBeenCalled()
    expect(kuzya().classList.contains('kuzya--alarm')).toBe(true)
    expect(kuzya().classList.contains('kuzya--happy')).toBe(false)
  })

  it('неинтерактивный Кузя нажатия не замечает', async () => {
    const { max, wrapper } = await renderComponent(KuzyaMascot, {
      props: { mood: 'ok', interactive: false },
    })
    await click(kuzya())
    expect(max.impact).not.toHaveBeenCalled()
    expect(wrapper.findComponent(KuzyaMascot).emitted('tap')).toBeUndefined()
    expect(kuzya().classList.contains('kuzya--ok')).toBe(true)
  })

  it('меняет позу и подпись вслед за настроением дома', async () => {
    const props = reactive({ mood: 'ok' as 'ok' | 'sad' })
    await renderComponent(KuzyaMascot, { props })
    props.mood = 'sad'
    await waitFor(() => kuzya().classList.contains('kuzya--sad'))
    expect(kuzya().getAttribute('aria-label')).toContain('Домовой Кузя грустит')
  })

  it('без настройки «уменьшить движение» дышит и моргает, а в списках стоит смирно', async () => {
    enableMotion()
    await renderComponent(KuzyaMascot, { props: { mood: 'worried' } })
    expect(kuzya().classList.contains('kuzya--calm')).toBe(false)
    document.body.innerHTML = ''
    await renderComponent(KuzyaMascot, { props: { mood: 'worried', still: true } })
    expect(document.querySelector('.kuzya')!.classList.contains('kuzya--calm')).toBe(true)
  })

  it('с анимациями нажатие тоже меняет позу, а смена настроения проходит без ошибок', async () => {
    enableMotion()
    const props = reactive({ mood: 'ok' as 'ok' | 'proud' })
    await renderComponent(KuzyaMascot, { props })
    await click(kuzya())
    await waitFor(() => kuzya().classList.contains('kuzya--happy'))
    props.mood = 'proud'
    await waitFor(() => kuzya().classList.contains('kuzya--proud'))
  })

  it('в спокойном режиме анимации выключены', async () => {
    await renderComponent(KuzyaMascot, { props: { mood: 'ok' } })
    expect(kuzya().classList.contains('kuzya--calm')).toBe(true)
  })
})
