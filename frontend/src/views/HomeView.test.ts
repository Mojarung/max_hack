import { describe, expect, it, vi } from 'vitest'
import { meApi } from '@/api/endpoints'
import { scenario } from '@/mock/scenario'
import { click, getButton, getByText, queryByText, waitFor } from '@/test/dom'
import { renderRoute } from '@/test/harness'

describe('Главный экран', () => {
  it('показывает фразу Кузи, заявку без голосов и ближайшее событие', async () => {
    await renderRoute('/')
    await waitFor(() => getByText('Нужны голоса'))
    expect(
      getByText('Баки у первого подъезда так и не вывезли, срок вышел. Готовлю жалобу.'),
    ).toBeTruthy()
    // из двух заявок на голосовании «горячая» та, которой меньше всего не хватает
    expect(getByText('Течёт крыша над 9 этажом')).toBeTruthy()
    expect(queryByText('Не горит свет в подъезде 3')).toBeNull()
    expect(getByText('Ближайшее событие')).toBeTruthy()
    expect(getByText('Осенний субботник')).toBeTruthy()
    expect(getButton('Сообщить о проблеме')).toBeTruthy()
  })

  it('по кнопке «Сообщить о проблеме» открывает новую заявку', async () => {
    const { router } = await renderRoute('/')
    await click('Сообщить о проблеме')
    await waitFor(() => router.currentRoute.value.path === '/issues/new')
    expect(queryByText('Нужны голоса')).toBeNull()
  })

  it('пока Кузя не посмотрел на дом, говорит «сейчас посмотрю»', async () => {
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const original = meApi.pulse
    vi.spyOn(meApi, 'pulse').mockImplementation(async () => {
      await gate
      return original()
    })
    await renderRoute('/', { session: false })
    expect(getByText('Сейчас посмотрю, как дела у дома...')).toBeTruthy()
    expect(getByText('Считаем...')).toBeTruthy()
    release()
    await waitFor(() => getByText('Кузя волнуется'))
    expect(queryByText('Сейчас посмотрю, как дела у дома...')).toBeNull()
  })

  it('одна просроченная заявка видна отдельной строкой с выходом к жалобе', async () => {
    const { router } = await renderRoute('/')
    await waitFor(() => getByText('1 заявка просрочена'))
    expect(getByText('Откройте и перешлите готовую жалобу')).toBeTruthy()
    await click(getByText('1 заявка просрочена').closest('a')!)
    await waitFor(() => router.currentRoute.value.fullPath === '/issues?overdue=1')
  })

  it('при нескольких просрочках Кузя грустит и считает их', async () => {
    await renderRoute('/', { scenario: { name: 'overdue' } })
    await waitFor(() => getByText('4 заявки просрочены'))
    expect(
      getByText('Уже 4 заявки просрочены. Я подготовил жалобу в Госжилинспекцию.'),
    ).toBeTruthy()
    expect(getByText('Кузя грустит')).toBeTruthy()
  })

  it('во время тревоги главная кнопка ведёт в укрытие', async () => {
    const { router, max } = await renderRoute('/', { scenario: { name: 'alert' } })
    await waitFor(() => getButton('Идти в укрытие'))
    expect(queryByText('Сообщить о проблеме')).toBeNull()
    expect(getByText(/Тревога! Отойдите от окон/)).toBeTruthy()
    expect(getByText('Кузя бьёт тревогу')).toBeTruthy()
    expect(max.notify).toHaveBeenCalledWith('warning')

    await click(getButton('Где укрыться'))
    await waitFor(() => router.currentRoute.value.path === '/more/safety')
  })

  it('кнопка «Идти в укрытие» открывает экран безопасности', async () => {
    const { router } = await renderRoute('/', { scenario: { name: 'alert' } })
    await waitFor(() => getButton('Идти в укрытие'))
    await click('Идти в укрытие')
    await waitFor(() => router.currentRoute.value.path === '/more/safety')
  })

  it('если сервер не ответил, предлагает повторить и после повтора показывает дом', async () => {
    await renderRoute('/', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    expect(queryByText('Здоровье дома')).toBeNull()

    // сервер ожил
    scenario.name = 'default'
    await click('Попробовать ещё раз')
    await waitFor(() => getByText('Кузя волнуется'))
    expect(queryByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeNull()
  })

  it('администратор нового дома видит приглашение настроить дом', async () => {
    const { router } = await renderRoute('/', { scenario: { setup: true, role: 'admin' } })
    await waitFor(() => getByText('Настройте дом'))
    expect(getByText(/Укажите адрес и управляющую компанию/)).toBeTruthy()
    await click(getByText('Настройте дом').closest('a')!)
    await waitFor(() => router.currentRoute.value.path === '/more/house/edit')
  })

  it('житель не видит приглашение настроить дом', async () => {
    await renderRoute('/', { scenario: { setup: true } })
    await waitFor(() => getByText('Кузя волнуется'))
    expect(queryByText('Настройте дом')).toBeNull()
  })

  it('показывает закреплённое объявление и ведёт ко всем объявлениям', async () => {
    const { router } = await renderRoute('/')
    await waitFor(() => getByText('Отключение горячей воды 1-3 октября'))
    expect(queryByText('Покраска подъезда 2')).toBeNull()
    const all = getButton(/Все \(2\)/)
    await click(all)
    await waitFor(() => router.currentRoute.value.path === '/announcements')
  })

  it('показывает здоровье и уровень дома, а также уровень жителя', async () => {
    const { router } = await renderRoute('/')
    await waitFor(() => getByText('Уровень дома: 3'))
    expect(getByText('340 из 500 очков')).toBeTruthy()
    expect(getByText('Анна, вы «Добрый сосед»')).toBeTruthy()
    expect(getByText(/ещё 105 до уровня 4/)).toBeTruthy()
    await click(getButton('Мой уровень и награды'))
    await waitFor(() => router.currentRoute.value.path === '/more/achievements')
  })

  it('в спокойном пустом доме Кузя доволен и зовёт на субботник', async () => {
    await renderRoute('/', { scenario: { name: 'empty' } })
    await waitFor(() => getByText('В доме тишь да гладь. Может, устроим субботник?'))
    expect(getByText('Кузя доволен')).toBeTruthy()
    expect(getByText('Уровень дома: 1')).toBeTruthy()
    expect(queryByText('Нужны голоса')).toBeNull()
    expect(queryByText('Ближайшее событие')).toBeNull()
    expect(queryByText(/просрочен/)).toBeNull()
    expect(getByText('Анна, вы «Новосёл»')).toBeTruthy()
  })

  it('быстрые ссылки ведут к Кузе и поиску', async () => {
    const { router } = await renderRoute('/')
    await click(getButton('Спросить Кузю'))
    await waitFor(() => router.currentRoute.value.path === '/more/assistant')
  })

  it('ссылка «Все» у события ведёт к списку событий', async () => {
    const { router } = await renderRoute('/')
    await waitFor(() => getByText('Ближайшее событие'))
    const head = getByText('Ближайшее событие').parentElement!
    await click(head.querySelector('a')!)
    await waitFor(() => router.currentRoute.value.path === '/events')
  })
})
