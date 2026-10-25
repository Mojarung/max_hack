import { describe, expect, it } from 'vitest'
import type { IssueStatus } from '@/api/types'
import { textOf } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import StatusChip from './StatusChip.vue'

async function chip(status: IssueStatus, overdue = false): Promise<HTMLElement> {
  const { wrapper } = await renderComponent(StatusChip, { props: { status, overdue } })
  return wrapper.find('.v-chip').element as HTMLElement
}

describe('Чип статуса заявки', () => {
  it.each([
    ['voting', 'Собираем голоса', 'mdi-account-multiple-plus'],
    ['sent', 'Отправлено', 'mdi-email-fast-outline'],
    ['in_progress', 'Чинят', 'mdi-hammer-wrench'],
    ['resolved', 'Решено', 'mdi-check-circle'],
    ['rejected', 'Отклонено', 'mdi-close-circle-outline'],
  ] as const)('статус %s подписан словами жителя: «%s»', async (status, title, icon) => {
    const el = await chip(status)
    expect(textOf(el)).toBe(title)
    expect(el.querySelector(`.${icon}`)).not.toBeNull()
    expect(el.className).toContain('v-chip--variant-tonal')
  })

  it('просрочку показывает заливкой тревожного цвета и часами', async () => {
    const el = await chip('sent', true)
    expect(textOf(el)).toBe('Просрочено')
    expect(el.querySelector('.mdi-clock-alert-outline')).not.toBeNull()
    expect(el.className).toContain('v-chip--variant-flat')
    expect(el.className).toContain('bg-deep')
  })

  it('незнакомый статус от сервера рисуется как сбор голосов, а не ломает экран', async () => {
    const el = await chip('archived' as IssueStatus)
    expect(el.querySelector('.mdi-account-multiple-plus')).not.toBeNull()
  })
})
