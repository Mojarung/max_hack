import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { mcpApi } from '@/api/endpoints'
import type { McpServerIn } from '@/api/types'
import { click, getButton, getByText, getField, queryByText, type, waitFor } from '@/test/dom'
import { renderRoute, useScenario } from '@/test/harness'

const PANEL_TITLE = '.v-expansion-panel-title'

async function openPanel(): Promise<void> {
  await click(await waitFor(() => document.querySelector(PANEL_TITLE)!))
}

async function openForm(): Promise<void> {
  await click(await waitFor(() => getButton('Подключить источник')))
  await waitFor(() => getByText('Новый источник (MCP-сервер)'))
}

describe('Навыки Кузи (MCP-серверы)', () => {
  it('показывает встроенный источник понятным названием', async () => {
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Жилищный навигатор'))
    expect(getByText('Паспорт дома, тарифы, капремонт')).toBeTruthy()
  })

  it('раскрытая карточка показывает адрес и что умеет сервер', async () => {
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openPanel()
    await waitFor(() => getByText('Что умеет: 3'))
    expect(getByText('housing_navigator · streamable_http')).toBeTruthy()
    expect(getByText('http://mcp:8765/mcp')).toBeTruthy()
    expect(getByText('house_passport')).toBeTruthy()
    expect(getByText('План капремонта по региональной программе')).toBeTruthy()
  })

  it('если инструменты не загрузились, пишет почему', async () => {
    vi.spyOn(mcpApi, 'tools').mockRejectedValue(
      new ApiError('http', 502, 'Сервер недоступен. Попробуйте через минуту'),
    )
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openPanel()
    await waitFor(() => getByText('Сервер недоступен. Попробуйте через минуту'))
  })

  it('форма не сохраняет неправильные имя, адрес и заголовки', async () => {
    const create = vi.spyOn(mcpApi, 'create')
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openForm()

    await click('Сохранить')
    await waitFor(() => getByText('Маленькие латинские буквы, цифры и _, первой должна быть буква'))
    expect(getByText('Адрес вида https://example.com/mcp')).toBeTruthy()

    await type(getField('Имя'), 'weather')
    await type(getField('Адрес'), 'https://mcp.example.com/mcp')
    await type(getField('Заголовки (необязательно)'), 'без двоеточия')
    await click('Сохранить')
    await waitFor(() => getByText('Каждая строка: Имя: значение'))
    expect(create).not.toHaveBeenCalled()
  })

  it('подключает новый сервер с заголовками авторизации', async () => {
    const create = vi.spyOn(mcpApi, 'create').mockImplementation(async (body: McpServerIn) => ({
      id: 7,
      name: body.name,
      transport: body.transport,
      url: body.url,
      enabled: true,
      has_headers: Object.keys(body.headers).length > 0,
    }))
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openForm()

    await type(getField('Имя'), 'weather')
    await type(getField('Адрес'), '  https://mcp.example.com/mcp ')
    await type(getField('Заголовки (необязательно)'), 'Authorization: Bearer abc\n\nX-Team: 5')
    await click('Сохранить')

    await waitFor(() => getByText('MCP-сервер добавлен'))
    expect(create).toHaveBeenCalledWith({
      name: 'weather',
      transport: 'streamable_http',
      url: 'https://mcp.example.com/mcp',
      headers: { Authorization: 'Bearer abc', 'X-Team': '5' },
    })
    // у нового сервера нет понятного названия: показываем имя
    expect(getByText('weather')).toBeTruthy()
    expect(getByText('Подключён')).toBeTruthy()
  })

  it('если сервер не добавился, говорит об этом', async () => {
    vi.spyOn(mcpApi, 'create').mockRejectedValue(
      new ApiError('http', 409, 'Сервер с таким именем уже есть'),
    )
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openForm()
    await type(getField('Имя'), 'housing_navigator')
    await type(getField('Адрес'), 'https://mcp.example.com/mcp')
    await click('Сохранить')
    await waitFor(() => getByText('Сервер не добавлен'))
    expect(getByText('Сервер с таким именем уже есть')).toBeTruthy()
  })

  it('удаление спрашивает подтверждение, после удаления список пуст', async () => {
    const remove = vi.spyOn(mcpApi, 'remove')
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openPanel()

    await click(await waitFor(() => getButton('Удалить')))
    await waitFor(() => getByText('Удалить «housing_navigator»?'))
    await click('Отмена')
    await waitFor(() => !queryByText('Удалить «housing_navigator»?'))
    expect(remove).not.toHaveBeenCalled()

    await click(getButton('Удалить'))
    await waitFor(() => getByText('Кузя перестанет пользоваться инструментами этого сервера.'))
    const dialog = document.querySelector('.v-overlay--active .v-card') as HTMLElement
    await click(getButton('Удалить', dialog))
    await waitFor(() => getByText('Сервер удалён'))
    expect(remove).toHaveBeenCalledWith(1)
    await waitFor(() => getByText('Источников пока нет'))
  })

  it('если удалить не вышло, сервер остаётся', async () => {
    vi.spyOn(mcpApi, 'remove').mockRejectedValue(
      new ApiError('http', 403, 'Недостаточно прав для этого действия'),
    )
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await openPanel()
    await click(await waitFor(() => getButton('Удалить')))
    const dialog = await waitFor(
      () => document.querySelector('.v-overlay--active .v-card') as HTMLElement,
    )
    await click(getButton('Удалить', dialog))
    await waitFor(() => getByText('Не удалось удалить'))
    expect(getByText('Жилищный навигатор')).toBeTruthy()
  })

  it('без серверов предлагает подключить первый', async () => {
    vi.spyOn(mcpApi, 'list').mockResolvedValueOnce([])
    await renderRoute('/more/mcp', { scenario: { role: 'admin' } })
    await waitFor(() => getByText('Источников пока нет'))
    expect(getByText('Подключите первый MCP-сервер')).toBeTruthy()
  })

  it('ошибка загрузки списка с повтором', async () => {
    await renderRoute('/more/mcp', { scenario: { role: 'admin', name: 'error' } })
    await waitFor(() => getByText('Кузя споткнулся на сервере. Попробуйте ещё раз'))
    useScenario({ role: 'admin' })
    await click('Попробовать ещё раз')
    await waitFor(() => getByText('Жилищный навигатор'))
  })
})
