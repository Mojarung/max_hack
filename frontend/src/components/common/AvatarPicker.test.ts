import { describe, expect, it } from 'vitest'
import { defineComponent, h, reactive } from 'vue'
import type { MockScenario } from '@/mock/scenario'
import { Toaster } from '@/components/ui/sonner'
import { useSessionStore } from '@/stores/session'
import { click, getButton, getByText, queryButton, settle, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import AvatarPicker from './AvatarPicker.vue'

/** Шторка выбора аватарки с v-model:open, как в профиле, и тосты рядом. */
async function renderPicker(scenario?: Partial<MockScenario>) {
  const state = reactive({ open: true, changed: 0 })
  const rendered = await renderComponent(
    defineComponent({
      setup: () => () => [
        h(AvatarPicker, {
          open: state.open,
          'onUpdate:open': (v: boolean) => (state.open = v),
          onChanged: () => (state.changed += 1),
        }),
        h(Toaster),
      ],
    }),
    { session: true, scenario },
  )
  await waitFor(() => getByText('Аватарка'))
  return { ...rendered, state }
}

function preset(n: number): HTMLElement {
  return document.querySelector(`[aria-label="Картинка ${n}"]`) as HTMLElement
}

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement
}

describe('Выбор аватарки', () => {
  it('показывает девять готовых картинок и кнопку своего фото', async () => {
    await renderPicker()
    expect(getByText('Выберите картинку или поставьте своё фото')).toBeTruthy()
    const presets = document.querySelectorAll('[role="radiogroup"] [role="radio"]')
    expect(presets).toHaveLength(9)
    expect(preset(4).querySelector('img')!.getAttribute('src')).toBe('/avatars/4.webp')
    expect([...presets].every((p) => p.getAttribute('aria-checked') === 'false')).toBe(true)
    expect(getButton('Поставить своё фото')).toBeTruthy()
    expect(queryButton('Вернуть как было')).toBeNull()
  })

  it('выбранная картинка сразу становится аватаркой, шторка закрывается', async () => {
    const { state, max } = await renderPicker()
    await click(preset(3))
    await waitFor(() => getByText('Аватарка обновлена'))
    expect(useSessionStore().me!.user.avatar).toBe('preset:3')
    expect(useSessionStore().me!.user.photo_url).toBe('/avatars/3.webp')
    expect(max.notify).toHaveBeenCalledWith('success')
    expect(state.changed).toBe(1)
    expect(state.open).toBe(false)
  })

  it('отмечает текущую картинку, повторный выбор просто закрывает шторку', async () => {
    const { state } = await renderPicker()
    await click(preset(5))
    await waitFor(() => state.open === false)
    state.open = true
    await settle()
    await waitFor(() => preset(5).getAttribute('aria-checked') === 'true')
    expect(preset(5).querySelector('.mdi-check-circle')).not.toBeNull()

    await click(preset(5))
    expect(state.open).toBe(false)
    expect(state.changed).toBe(1)
  })

  it('«Вернуть как было» возвращает фото из MAX', async () => {
    const { state } = await renderPicker()
    await click(preset(2))
    await waitFor(() => state.open === false)
    state.open = true
    await waitFor(() => getButton('Вернуть как было'))
    await click('Вернуть как было')
    await waitFor(() => state.changed === 2)
    expect(useSessionStore().me!.user.avatar).toBeNull()
  })

  it('своё фото загружается и ставится вместо картинки', async () => {
    const { state } = await renderPicker()
    const input = fileInput()
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [new File(['фото'], 'me.jpg', { type: 'image/jpeg' })],
    })
    input.dispatchEvent(new Event('change'))
    await waitFor(() => getByText('Аватарка обновлена'))
    expect(useSessionStore().me!.user.avatar).toBe('upload')
    expect(state.open).toBe(false)

    state.open = true
    await waitFor(() => getButton('Поставить другое фото'))
  })

  it('пока фото загружается, показывает проценты и не даёт выбрать картинку', async () => {
    await renderPicker({ latency: 80 })
    const input = fileInput()
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [new File(['фото'], 'me.jpg', { type: 'image/jpeg' })],
    })
    input.dispatchEvent(new Event('change'))
    await waitFor(() => getByText(/Загружаем\.\.\. (30|70|100)%/))
    expect(preset(1).hasAttribute('disabled')).toBe(true)
    await waitFor(() => getByText('Аватарка обновлена'))
  })

  it('если фото не выбрали, ничего не отправляет', async () => {
    const { state } = await renderPicker()
    const input = fileInput()
    Object.defineProperty(input, 'files', { configurable: true, value: [] })
    input.dispatchEvent(new Event('change'))
    await settle()
    expect(state.changed).toBe(0)
    expect(state.open).toBe(true)
  })

  it('при ошибке сервера аватарка не меняется и житель видит причину', async () => {
    const { state, max } = await renderPicker({ name: 'error' })
    await click(preset(7))
    await waitFor(() => getByText('Не удалось сменить аватарку'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('error')
    expect(useSessionStore().me!.user.avatar ?? null).toBeNull()
    expect(state.open).toBe(true)
    // после ошибки картинки снова доступны
    expect(preset(7).hasAttribute('disabled')).toBe(false)
  })
})
