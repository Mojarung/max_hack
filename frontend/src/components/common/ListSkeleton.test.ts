import { describe, expect, it } from 'vitest'
import { renderComponent } from '@/test/harness'
import ListSkeleton from './ListSkeleton.vue'

function root(): HTMLElement {
  return document.querySelector('[aria-busy="true"]') as HTMLElement
}

describe('Заглушка списка при загрузке', () => {
  it('по умолчанию рисует четыре строки и говорит диктору «Загрузка»', async () => {
    await renderComponent(ListSkeleton)
    expect(root().getAttribute('aria-label')).toBe('Загрузка')
    expect(root().className).toContain('flex-col')
    expect(root().children).toHaveLength(4)
  })

  it('сеткой рисует нужное число плиток', async () => {
    await renderComponent(ListSkeleton, { props: { count: 6, variant: 'grid' } })
    expect(root().className).toContain('grid-cols-2')
    expect(root().children).toHaveLength(6)
  })
})
