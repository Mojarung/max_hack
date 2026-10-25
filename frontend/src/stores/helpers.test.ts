import { describe, expect, it, vi } from 'vitest'
import { registerReset, removeById, resetAllStores, upsertById } from './helpers'

type Row = { id: number; title: string; mine?: boolean }

const list: readonly Row[] = [
  { id: 1, title: 'Крыша', mine: true },
  { id: 2, title: 'Лифт', mine: false },
]

describe('upsertById', () => {
  it('заменяет элемент на месте и не мутирует исходный список', () => {
    const next = upsertById(list, { id: 2, title: 'Лифт починили' })
    expect(next.map((r) => r.title)).toEqual(['Крыша', 'Лифт починили'])
    expect(list[1]?.title).toBe('Лифт')
    expect(next).not.toBe(list)
  })

  it('сохраняет личные поля из локальной версии', () => {
    const next = upsertById(list, { id: 1, title: 'Крыша', mine: false }, { keep: ['mine'] })
    expect(next[0]?.mine).toBe(true)
  })

  it('новый элемент добавляет в конец или в начало', () => {
    expect(upsertById(list, { id: 3, title: 'Свет' }).at(-1)?.id).toBe(3)
    expect(upsertById(list, { id: 3, title: 'Свет' }, { prepend: true })[0]?.id).toBe(3)
  })

  it('с onlyExisting новый элемент не добавляет', () => {
    const next = upsertById(list, { id: 3, title: 'Свет' }, { onlyExisting: true })
    expect(next.map((r) => r.id)).toEqual([1, 2])
    expect(next).not.toBe(list)
  })
})

describe('removeById', () => {
  it('убирает элемент по id', () => {
    expect(removeById(list, 1).map((r) => r.id)).toEqual([2])
    expect(list).toHaveLength(2)
  })
})

describe('resetAllStores', () => {
  it('вызывает все зарегистрированные сбросчики', () => {
    const first = vi.fn()
    const second = vi.fn()
    registerReset(first)
    registerReset(second)
    resetAllStores()
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)
  })
})
