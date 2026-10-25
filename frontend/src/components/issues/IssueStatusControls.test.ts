import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import type { IssueDetail } from '@/api/types'
import { Toaster } from '@/components/ui/sonner'
import { buildIssues, buildUsers } from '@/mock/fixtures'
import type { MockScenario } from '@/mock/scenario'
import { useIssuesStore } from '@/stores/issues'
import { click, getButton, getByText, getField, queryButton, type, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import IssueStatusControls from './IssueStatusControls.vue'

/** Кнопки статуса и тосты рядом: так житель видит ответ после «Сохранить». */
const WithToaster = defineComponent({
  inheritAttrs: false,
  setup:
    (_, { attrs }) =>
    () => [h(IssueStatusControls, attrs as { issue: IssueDetail }), h(Toaster)],
})

/** Заявка из фикстур мок-бэкенда (в сценарии error сервер её не отдаст). */
function issueFromFixtures(id: number): IssueDetail {
  const s = { name: 'default' } as MockScenario
  return buildIssues(s, buildUsers(s), 6).find((i) => i.id === id)!
}

async function renderFor(id: number, scenario?: Partial<MockScenario>) {
  await renderComponent(WithToaster, { props: { issue: issueFromFixtures(id) }, scenario })
  await waitFor(() => getByText('Что с заявкой сейчас?'))
}

describe('Управление статусом заявки', () => {
  it('для отправленной заявки предлагает начать, закрыть или отклонить', async () => {
    await renderFor(103)
    expect(getButton('Начали чинить')).toBeTruthy()
    expect(getButton('Всё исправили')).toBeTruthy()
    expect(getButton('Отклонить')).toBeTruthy()
  })

  it('когда уже чинят, кнопки «Начали чинить» нет', async () => {
    await renderFor(104)
    expect(queryButton('Начали чинить')).toBeNull()
    expect(getButton('Всё исправили')).toBeTruthy()
    expect(getButton('Отклонить')).toBeTruthy()
  })

  it('сохраняет новый статус с комментарием и сообщает об этом', async () => {
    await renderFor(103)
    await click('Всё исправили')
    const note = await waitFor(() => getField('Комментарий'))
    expect(note.getAttribute('placeholder')).toContain('Кровлю залатали')
    expect(getByText('Комментарий увидят все жители')).toBeTruthy()

    await type(note, '  Лифт починили  ')
    await click('Сохранить')

    await waitFor(() => getByText('Статус обновлён'))
    expect(getByText('Жители увидят изменения сразу')).toBeTruthy()
    const saved = useIssuesStore().details[103]!
    expect(saved.status).toBe('resolved')
    expect(saved.timeline.at(-1)?.note).toBe('Лифт починили')
    // шторка закрылась
    await waitFor(() => !document.querySelector('[data-vaul-drawer][data-state="open"]'))
  })

  it('у каждого действия своя подсказка в шторке', async () => {
    await renderFor(103)
    await click('Отклонить')
    const note = await waitFor(() => getField('Комментарий'))
    expect(note.getAttribute('placeholder')).toBe('Коротко объясните причину')
  })

  it('при ошибке сервера статус не меняется и житель видит причину', async () => {
    await renderFor(103, { name: 'error' })
    await click('Начали чинить')
    await waitFor(() => getField('Комментарий'))
    await click('Сохранить')
    await waitFor(() => getByText('Статус не изменился'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    expect(useIssuesStore().details[103]).toBeUndefined()
    // шторка остаётся открытой: можно попробовать ещё раз
    expect(getButton('Сохранить')).toBeTruthy()
  })
})
