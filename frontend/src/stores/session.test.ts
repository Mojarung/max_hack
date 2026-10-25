import { describe, expect, it, vi } from 'vitest'
import { ApiError, getDevUser, getHouseId } from '@/api/client'
import { houseApi, meApi } from '@/api/endpoints'
import { notify } from '@/lib/notify'
import { breakServer, fakeMax, flushMock, setScenario, useMockBackend } from '@/test/mockBackend'
import { useIssuesStore } from './issues'
import { useSessionStore } from './session'

useMockBackend()

describe('загрузка сессии внутри MAX', () => {
  it('узнаёт жителя, его дом и список домов', async () => {
    const max = fakeMax()
    const session = useSessionStore()
    await session.init()
    expect(max.ready).toHaveBeenCalled()
    expect(session.status).toBe('ready')
    expect(session.inMax).toBe(true)
    expect(session.me?.user.first_name).toBe('Анна')
    expect(session.me?.house.title).toBe('Ленинского Комсомола, 5')
    expect(getHouseId()).toBe(1)
    expect(session.isMock).toBe(false)
    expect(session.isAdmin).toBe(false)
    expect(session.canUseDevTools).toBe(false)
    await flushMock()
    expect(session.houses.map((h) => h.title)).toEqual([
      'Ленинского Комсомола, 5',
      'Созидателей, 34',
    ])
    expect(session.housesLoading).toBe(false)
  })

  it('администратор нового дома видит, что дом надо настроить', async () => {
    setScenario({ role: 'admin', setup: true })
    fakeMax()
    const session = useSessionStore()
    await session.init()
    expect(session.isAdmin).toBe(true)
    expect(session.canManageMcp).toBe(true)
    expect(session.needsSetup).toBe(true)
  })

  it('новичку показывается обучалка, после неё больше нет', async () => {
    setScenario({ onboarding: true })
    fakeMax()
    const session = useSessionStore()
    await session.init()
    expect(session.needsOnboarding).toBe(true)
    await session.completeOnboarding()
    expect(session.needsOnboarding).toBe(false)
    expect(session.me?.user.onboarded).toBe(true)
  })

  it('если сервер не записал обучалку, житель всё равно идёт дальше', async () => {
    setScenario({ onboarding: true })
    fakeMax()
    const session = useSessionStore()
    await session.init()
    breakServer()
    await expect(session.completeOnboarding()).resolves.toBeUndefined()
    expect(session.needsOnboarding).toBe(false)
  })

  it('без связи показывает ошибку загрузки без советов про демо', async () => {
    setScenario({ name: 'boot-error' })
    fakeMax()
    const session = useSessionStore()
    await session.init()
    expect(session.status).toBe('error')
    expect(session.bootError).toBe('Нет связи с сервером. Проверьте интернет')
  })
})

describe('загрузка сессии в обычном браузере', () => {
  it('боевой сервер вне MAX: экран «Кузя живёт в MAX»', async () => {
    fakeMax(false)
    vi.spyOn(meApi, 'meta').mockResolvedValue({ bot_username: 'domovoy_kuzya_bot', mock: false })
    const session = useSessionStore()
    await session.init()
    expect(session.status).toBe('outside')
    expect(session.botUsername).toBe('domovoy_kuzya_bot')
  })

  it('демо-сервер: первый демо-житель по умолчанию', async () => {
    setScenario({ inMax: false })
    fakeMax(false)
    const session = useSessionStore()
    await session.init()
    expect(session.status).toBe('ready')
    expect(session.isMock).toBe(true)
    expect(session.canUseDevTools).toBe(true)
    expect(session.devUsers).toHaveLength(6)
    expect(session.devUserId).toBe(1001)
    expect(getDevUser()).toBe(1001)
    expect(session.currentDevUser?.first_name).toBe('Анна')
  })

  it('помнит выбранного в прошлый раз демо-жителя', async () => {
    setScenario({ inMax: false })
    fakeMax(false)
    localStorage.setItem('kuzya.devUser', '1003')
    const session = useSessionStore()
    await session.init()
    expect(session.devUserId).toBe(1003)
    expect(session.me?.user.first_name).toBe('Марина')
  })

  it('старый сервер без /meta: тоже даёт демо-жителей', async () => {
    setScenario({ inMax: false })
    fakeMax(false)
    vi.spyOn(meApi, 'meta').mockRejectedValue(new ApiError('http', 404, 'Не нашли'))
    const session = useSessionStore()
    await session.init()
    expect(session.status).toBe('ready')
    expect(session.botUsername).toBeNull()
  })

  it('без демо-жителей подсказывает, как запустить демо', async () => {
    fakeMax(false)
    vi.spyOn(meApi, 'devUsers').mockResolvedValue([])
    const session = useSessionStore()
    await session.init()
    expect(session.status).toBe('error')
    expect(session.bootError).toBe(
      'Нет демо-жителей. Для демо запустите сервер с MOCK_MAX=true или откройте приложение в MAX.',
    )
  })
})

describe('смена демо-жителя', () => {
  async function demoSession() {
    setScenario({ inMax: false })
    fakeMax(false)
    const session = useSessionStore()
    await session.init()
    return session
  }

  it('переключает жителя, сбрасывает данные и запоминает выбор', async () => {
    const success = vi.spyOn(notify, 'success')
    const session = await demoSession()
    const issues = useIssuesStore()
    await issues.load()
    await session.switchUser(1002)
    expect(session.devUserId).toBe(1002)
    expect(session.me?.user.first_name).toBe('Ильдар')
    expect(session.userKey).toBe(1)
    expect(localStorage.getItem('kuzya.devUser')).toBe('1002')
    expect(issues.items).toEqual([])
    expect(success).toHaveBeenCalledWith('Теперь вы: Ильдар')
  })

  it('выбор того же жителя ничего не делает', async () => {
    const session = await demoSession()
    await session.switchUser(1001)
    expect(session.userKey).toBe(0)
  })

  it('при ошибке возвращает прежнего жителя', async () => {
    const error = vi.spyOn(notify, 'error')
    const session = await demoSession()
    vi.spyOn(meApi, 'me').mockRejectedValueOnce(new ApiError('network', 0, 'Нет связи'))
    await session.switchUser(1004)
    expect(session.devUserId).toBe(1001)
    expect(getDevUser()).toBe(1001)
    expect(error).toHaveBeenCalledWith(expect.any(ApiError), 'Не удалось сменить жителя')
  })
})

describe('переключение домов', () => {
  it('переключает дом и отмечает его текущим', async () => {
    const success = vi.spyOn(notify, 'success')
    fakeMax()
    const session = useSessionStore()
    await session.init()
    await flushMock()
    await session.switchHouse(2)
    expect(session.me?.house.title).toBe('Созидателей, 34')
    expect(getHouseId()).toBe(2)
    expect(session.userKey).toBe(1)
    expect(session.houses.find((h) => h.is_current)?.id).toBe(2)
    expect(success).toHaveBeenCalledWith('Дом: Созидателей, 34')
  })

  it('тот же дом не переключает', async () => {
    fakeMax()
    const session = useSessionStore()
    await session.init()
    await session.switchHouse(1)
    expect(session.userKey).toBe(0)
  })

  it('при ошибке остаётся в прежнем доме', async () => {
    const error = vi.spyOn(notify, 'error')
    fakeMax()
    const session = useSessionStore()
    await session.init()
    vi.spyOn(meApi, 'me').mockRejectedValueOnce(new ApiError('http', 500, 'Сбой'))
    await session.switchHouse(2)
    expect(getHouseId()).toBe(1)
    expect(session.me?.house.id).toBe(1)
    expect(error).toHaveBeenCalledWith(expect.any(ApiError), 'Не удалось переключить дом')
  })

  it('житель вышел из чата дома: сервер сам подбирает доступный дом', async () => {
    fakeMax()
    const session = useSessionStore()
    await session.init()
    const real = meApi.me
    const spy = vi
      .spyOn(meApi, 'me')
      .mockRejectedValueOnce(new ApiError('http', 403, 'Вы не состоите в чате дома'))
      .mockImplementation(real)
    await session.refreshMe()
    expect(spy).toHaveBeenCalledTimes(2)
    expect(session.me?.house.id).toBe(1)
  })

  it('другие ошибки при обновлении профиля пробрасываются', async () => {
    fakeMax()
    const session = useSessionStore()
    await session.init()
    vi.spyOn(meApi, 'me').mockRejectedValueOnce(new ApiError('http', 500, 'Сбой'))
    await expect(session.refreshMe()).rejects.toThrow('Сбой')
  })

  it('обновление списка домов просит сервер поискать чаты заново', async () => {
    fakeMax()
    const spy = vi.spyOn(houseApi, 'list')
    const session = useSessionStore()
    const pending = session.loadHouses(true)
    expect(session.housesLoading).toBe(true)
    await pending
    expect(spy).toHaveBeenCalledWith(true)
    expect(session.housesLoading).toBe(false)
  })
})
