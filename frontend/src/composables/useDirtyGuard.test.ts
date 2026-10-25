import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref, type Ref } from 'vue'
import { useDirtyGuard } from './useDirtyGuard'

afterEach(() => {
  delete window.WebApp
})

function installMax() {
  const closing = vi.fn()
  window.WebApp = {
    initData: 'signed',
    enableClosingConfirmation: () => closing(true),
    disableClosingConfirmation: () => closing(false),
  }
  return closing
}

/** Форма, которая следит за своей заполненностью. */
function mountForm(dirty: Ref<boolean>) {
  return mount(
    defineComponent({
      setup() {
        useDirtyGuard(dirty)
        return () => h('form')
      },
    }),
  )
}

describe('защита заполненной формы', () => {
  it('пока форма заполнена, MAX спросит перед закрытием', async () => {
    const closing = installMax()
    const dirty = ref(false)
    const wrapper = mountForm(dirty)
    expect(closing).toHaveBeenLastCalledWith(false)
    dirty.value = true
    await nextTick()
    expect(closing).toHaveBeenLastCalledWith(true)

    wrapper.unmount()
    expect(closing).toHaveBeenLastCalledWith(false)
  })

  it('вне MAX ничего не вызывает', () => {
    window.WebApp = { initData: '' }
    expect(() => mountForm(ref(true)).unmount()).not.toThrow()
  })
})
