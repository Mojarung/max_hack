import { config } from '@vue/test-utils'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, reactive } from 'vue'
import { getByText, queryByText, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import AnimatedList from './AnimatedList.vue'

/** Список карточек, который меняется при смене фильтра. */
function listOf(items: string[]) {
  const state = reactive({ items })
  const component = defineComponent({
    setup: () => () =>
      h(AnimatedList, { tag: 'ul' }, () => state.items.map((t) => h('li', { key: t }, t))),
  })
  return { state, component }
}

// test-utils по умолчанию подменяет TransitionGroup заглушкой, а здесь проверяем именно её
const defaultStubs = config.global.stubs
beforeAll(() => {
  config.global.stubs = { ...defaultStubs, 'transition-group': false }
})
afterAll(() => {
  config.global.stubs = defaultStubs
})

afterEach(() => {
  document.documentElement.dataset.motion = 'off'
})

describe('Список с плавной перестройкой', () => {
  it('рисует карточки внутри нужного тега', async () => {
    const { component } = listOf(['Мебель', 'Детское'])
    await renderComponent(component)
    const list = document.querySelector('ul.alist')!
    expect(list.children).toHaveLength(2)
    expect(getByText('Детское').tagName).toBe('LI')
  })

  it('без анимаций убранная карточка исчезает сразу', async () => {
    const { state, component } = listOf(['Мебель', 'Детское', 'Техника'])
    await renderComponent(component)
    state.items = ['Мебель', 'Техника']
    await nextTick()
    expect(queryByText('Детское')).toBeNull()
  })

  it('с анимацией уходящая карточка остаётся на своём месте, пока растворяется', async () => {
    delete document.documentElement.dataset.motion
    const { state, component } = listOf(['Мебель', 'Детское', 'Техника'])
    await renderComponent(component)
    const leaving = getByText('Детское')
    state.items = ['Мебель', 'Техника']
    await nextTick()
    expect(leaving.style.position).toBe('absolute')
    expect(leaving.style.top).toBe('0px')
    expect(leaving.className).toContain('alist-leave-active')
    await waitFor(() => queryByText('Детское') === null)
  })
})
