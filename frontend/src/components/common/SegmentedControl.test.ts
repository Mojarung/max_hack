import { DOMWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'
import { click, getByText, settle, swipe } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import SegmentedControl from './SegmentedControl.vue'

type Tab = 'upcoming' | 'past' | 'mine'

const OPTIONS: { value: Tab; label: string; icon?: string }[] = [
  { value: 'upcoming', label: 'Скоро', icon: 'mdi-calendar' },
  { value: 'past', label: 'Прошли' },
  { value: 'mine', label: 'Мои' },
]

/** Переключатель над списком, как на экране событий: под ним область .list-area. */
async function renderTabs(start: Tab = 'upcoming') {
  const state = reactive({ value: start })
  const rendered = await renderComponent(
    defineComponent({
      setup: () => () =>
        h('div', { class: 'screen' }, [
          h(SegmentedControl<Tab>, {
            options: OPTIONS,
            label: 'Какие события',
            modelValue: state.value,
            'onUpdate:modelValue': (v: Tab) => (state.value = v),
          }),
          h('div', { class: 'list-area' }, 'Список'),
        ]),
    }),
  )
  const scrollBy = vi.fn()
  vi.stubGlobal('scrollBy', scrollBy)
  return { ...rendered, state, scrollBy }
}

function radio(label: string): HTMLElement {
  return getByText(label).closest('[role="radio"]') as HTMLElement
}

function area(): HTMLElement {
  return document.querySelector('.list-area') as HTMLElement
}

async function key(name: string): Promise<KeyboardEvent> {
  const event = new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true })
  document.querySelector('[role="radiogroup"]')!.dispatchEvent(event)
  await settle()
  return event
}

describe('Сегментированный переключатель', () => {
  it('показывает пункты как радиокнопки и отмечает выбранный', async () => {
    await renderTabs('past')
    const group = document.querySelector('[role="radiogroup"]') as HTMLElement
    expect(group.getAttribute('aria-label')).toBe('Какие события')
    expect(group.style.getPropertyValue('--count')).toBe('3')
    expect(group.style.getPropertyValue('--index')).toBe('1')
    expect(radio('Прошли').getAttribute('aria-checked')).toBe('true')
    expect(radio('Прошли').getAttribute('tabindex')).toBe('0')
    expect(radio('Скоро').getAttribute('aria-checked')).toBe('false')
    expect(radio('Скоро').getAttribute('tabindex')).toBe('-1')
    expect(radio('Скоро').querySelector('.mdi-calendar')).not.toBeNull()
  })

  it('нажатие выбирает пункт, отзывается вибро и задаёт направление списка', async () => {
    const { state, max } = await renderTabs()
    await click(radio('Мои'))
    expect(state.value).toBe('mine')
    expect(max.selection).toHaveBeenCalledTimes(1)
    expect(area().dataset.dir).toBe('next')

    await click(radio('Скоро'))
    expect(state.value).toBe('upcoming')
    expect(area().dataset.dir).toBe('prev')
  })

  it('повторное нажатие на выбранный пункт ничего не делает', async () => {
    const { state, max } = await renderTabs()
    await click(radio('Скоро'))
    expect(state.value).toBe('upcoming')
    expect(max.selection).not.toHaveBeenCalled()
  })

  it('если список пролистан и переключатель ушёл под шапку, возвращает к нему', async () => {
    const { scrollBy } = await renderTabs()
    const root = document.querySelector('[role="radiogroup"]') as HTMLElement
    vi.spyOn(root, 'getBoundingClientRect').mockReturnValue({ top: -200 } as DOMRect)
    Object.defineProperty(area(), 'offsetHeight', { configurable: true, value: 640 })
    await click(radio('Прошли'))
    expect(scrollBy).toHaveBeenCalledWith({ top: -280, behavior: 'auto' })
    // пока едем вверх, высота списка держится
    expect(area().style.minHeight).toBe('640px')
  })

  it('когда переключатель виден, страницу не двигает', async () => {
    const { scrollBy } = await renderTabs()
    const root = document.querySelector('[role="radiogroup"]') as HTMLElement
    vi.spyOn(root, 'getBoundingClientRect').mockReturnValue({ top: 150 } as DOMRect)
    await click(radio('Прошли'))
    expect(scrollBy).not.toHaveBeenCalled()
    expect(area().style.minHeight).toBe('')
  })

  it('стрелки переключают пункты по кругу, другие клавиши не трогает', async () => {
    const { state } = await renderTabs()
    await key('ArrowRight')
    expect(state.value).toBe('past')
    await key('ArrowLeft')
    await key('ArrowLeft')
    expect(state.value).toBe('mine')
    const other = await key('Enter')
    expect(other.defaultPrevented).toBe(false)
    expect(state.value).toBe('mine')
  })

  it('свайп по экрану под переключателем листает вкладки, на краях дальше не идёт', async () => {
    const { state } = await renderTabs()
    const screen = area()
    await swipe(screen, { x: 300, y: 200 }, { x: 150, y: 210 })
    expect(state.value).toBe('past')
    await swipe(screen, { x: 300, y: 200 }, { x: 150, y: 200 })
    expect(state.value).toBe('mine')
    await swipe(screen, { x: 300, y: 200 }, { x: 150, y: 200 })
    expect(state.value).toBe('mine')
    await swipe(screen, { x: 100, y: 200 }, { x: 260, y: 200 })
    expect(state.value).toBe('past')
  })

  it('короткое или вертикальное движение пальца не листает', async () => {
    const { state } = await renderTabs()
    await swipe(area(), { x: 300, y: 200 }, { x: 270, y: 200 })
    await swipe(area(), { x: 300, y: 100 }, { x: 220, y: 300 })
    expect(state.value).toBe('upcoming')
  })

  it('палец на самом переключателе не считается свайпом по экрану', async () => {
    const { state } = await renderTabs()
    const group = document.querySelector('[role="radiogroup"]') as HTMLElement
    await swipe(group, { x: 300, y: 20 }, { x: 100, y: 20 })
    expect(state.value).toBe('upcoming')
  })

  it('после ухода с экрана свайп больше не слушается', async () => {
    const { state, wrapper } = await renderTabs()
    const screen = area().parentElement!
    wrapper.unmount()
    await new DOMWrapper(screen).trigger('touchstart')
    expect(state.value).toBe('upcoming')
  })
})
