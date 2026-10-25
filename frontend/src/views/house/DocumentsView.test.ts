import { beforeEach, describe, expect, it, vi } from 'vitest'
import { documentsApi } from '@/api/endpoints'
import type { DocumentOut } from '@/api/types'
import { scenario } from '@/mock/scenario'
import {
  click,
  getButton,
  getByText,
  getField,
  queryButton,
  queryByText,
  settle,
  type,
  waitFor,
} from '@/test/dom'
import { renderRoute } from '@/test/harness'

const ADMIN = { scenario: { role: 'admin' as const } }
const PROTOCOL = 'Протокол общего собрания от 12.09'
const CONTRACT = 'Договор управления с УК'

/** Выбрать файл в скрытом поле, как это делает системный диалог. */
async function pickFile(file: File): Promise<void> {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  input.dispatchEvent(new Event('change'))
  await settle()
}

/** Кнопка внутри открытой шторки (vaul рисует её в role="dialog"). */
function inDrawer(): HTMLElement {
  return document.querySelector<HTMLElement>('[role="dialog"]')!
}

beforeEach(() => {
  // URL.createObjectURL из Node не принимает Blob из jsdom: ссылка на документ из мока падала бы
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test/document')
  // переключатель вкладок прокручивает к себе страницу, а jsdom этого не умеет
  vi.spyOn(window, 'scrollBy').mockImplementation(() => undefined)
})

function doc(patch: Partial<DocumentOut>): DocumentOut {
  return {
    id: 1,
    title: 'Документ',
    filename: 'doc',
    content_type: 'application/pdf',
    size: 2048,
    scope: 'house',
    author: null,
    can_delete: false,
    created_at: '2026-10-01T10:00:00+04:00',
    ...patch,
  }
}

describe('Документы: житель', () => {
  it('показывает документы дома с датой и размером, без кнопок удаления и загрузки', async () => {
    await renderRoute('/more/documents')
    await waitFor(() => getByText(PROTOCOL))
    expect(getByText(CONTRACT)).toBeTruthy()
    expect(getByText(/Протоколы собраний, договор управления, акты/)).toBeTruthy()
    // 184 320 байт - 180 КБ, загружен за 9 дней до «сейчас»
    expect(getByText('12 октября · 180 КБ')).toBeTruthy()
    expect(queryButton(`Удалить ${PROTOCOL}`)).toBeNull()
    expect(queryButton('Загрузить')).toBeNull()
  })

  it('открывает документ по временной ссылке через MAX', async () => {
    const { max } = await renderRoute('/more/documents')
    await click(await waitFor(() => getButton(`Открыть ${PROTOCOL}`)))
    await waitFor(() => max.openLink.mock.calls.length > 0)
    expect(max.openLink).toHaveBeenCalledWith(expect.stringMatching(/^blob:/))
    expect(getByText('Открываю документ...')).toBeTruthy()
  })

  it('относительную ссылку с сервера дополняет адресом сайта', async () => {
    const { max } = await renderRoute('/more/documents')
    vi.spyOn(documentsApi, 'link').mockResolvedValue({ url: '/files/801', expires_at: 0 })
    await click(await waitFor(() => getButton(`Открыть ${PROTOCOL}`)))
    await waitFor(() => max.openLink.mock.calls.length > 0)
    expect(max.openLink).toHaveBeenCalledWith(`${window.location.origin}/files/801`)
  })

  it('в обычном браузере открывает документ в новой вкладке', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    await renderRoute('/more/documents', { scenario: { inMax: false } })
    await click(await waitFor(() => getButton(`Открыть ${CONTRACT}`)))
    await waitFor(() => open.mock.calls.length > 0)
    expect(open).toHaveBeenCalledWith(
      expect.stringMatching(/^blob:/),
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('если ссылку получить не удалось, говорит об этом', async () => {
    await renderRoute('/more/documents')
    vi.spyOn(documentsApi, 'link').mockRejectedValue(new Error('Ссылка устарела'))
    await click(await waitFor(() => getButton(`Открыть ${PROTOCOL}`)))
    await waitFor(() => getByText('Не удалось открыть документ'))
    expect(getByText('Ссылка устарела')).toBeTruthy()
  })

  it('пустой список документов дома: житель ничего загрузить не может', async () => {
    vi.spyOn(documentsApi, 'list').mockResolvedValue([])
    await renderRoute('/more/documents')
    await waitFor(() => getByText('Документов дома пока нет'))
    expect(getByText('Администратор дома ещё ничего не загрузил')).toBeTruthy()
    expect(queryButton('Загрузить')).toBeNull()
  })

  it('вкладка «Мои»: пусто и предлагает загрузить квитанцию', async () => {
    await renderRoute('/more/documents')
    await waitFor(() => getByText(PROTOCOL))
    await click('Мои')
    await waitFor(() => getByText('Личных документов нет'))
    expect(getByText('Квитанции, акты, паспорт квартиры. Их видите только вы.')).toBeTruthy()
    expect(getByText('Храните здесь квитанции, акты и паспорт квартиры')).toBeTruthy()
    expect(queryByText(PROTOCOL)).toBeNull()
  })

  it('загружает личный документ: имя файла становится названием', async () => {
    await renderRoute('/more/documents')
    await click('Мои')
    await click(await waitFor(() => getButton('Загрузить')))
    await waitFor(() => getByText('Новый документ'))
    // без файла отправить нельзя
    expect(getButton('Загрузить', inDrawer()).hasAttribute('disabled')).toBe(true)

    await pickFile(new File(['квитанция'], 'kvitanciya-oktyabr.pdf', { type: 'application/pdf' }))
    expect(getButton('kvitanciya-oktyabr.pdf', inDrawer())).toBeTruthy()
    expect(getField('Название', inDrawer()).value).toBe('kvitanciya-oktyabr')
    // житель не выбирает, кому виден документ
    expect(queryByText('Документ дома: видят все жители')).toBeNull()

    await click(getButton('Загрузить', inDrawer()))
    await waitFor(() => getByText('Документ загружен'))
    expect(getByText('Его видите только вы')).toBeTruthy()
    await waitFor(() => getButton('Открыть kvitanciya-oktyabr'))
  })

  it('название короче двух букв не даёт загрузить файл', async () => {
    await renderRoute('/more/documents')
    await click('Мои')
    await click(await waitFor(() => getButton('Загрузить')))
    await pickFile(new File(['x'], 'scan.jpg', { type: 'image/jpeg' }))
    await type(getField('Название', inDrawer()), 'А')
    expect(getButton('Загрузить', inDrawer()).hasAttribute('disabled')).toBe(true)
  })

  it('ошибка загрузки списка: показывает причину и загружает заново по кнопке', async () => {
    await renderRoute('/more/documents', { scenario: { name: 'error' } })
    await waitFor(() => getByText('Не получилось загрузить'))
    expect(getByText('Кузя споткнулся на сервере. Попробуйте ещё раз')).toBeTruthy()
    scenario.name = 'default'
    await click('Попробовать ещё раз')
    await waitFor(() => getByText(PROTOCOL))
  })

  it('подбирает значок по типу файла и пишет большой размер в мегабайтах', async () => {
    vi.spyOn(documentsApi, 'list').mockResolvedValue([
      doc({ id: 1, title: 'Таблица показаний', content_type: 'application/vnd.ms-excel' }),
      doc({ id: 2, title: 'Акт осмотра', content_type: 'application/msword' }),
      doc({ id: 3, title: 'Фото счётчика', content_type: 'image/png', size: 2_621_440 }),
      doc({ id: 4, title: 'Заметка', content_type: 'text/plain', size: 10 }),
    ])
    await renderRoute('/more/documents')
    const row = (title: string) => getButton(`Открыть ${title}`)
    await waitFor(() => row('Таблица показаний'))
    expect(row('Таблица показаний').querySelector('.mdi-file-excel-outline')).toBeTruthy()
    expect(row('Акт осмотра').querySelector('.mdi-file-word-outline')).toBeTruthy()
    expect(row('Фото счётчика').querySelector('.mdi-file-image-outline')).toBeTruthy()
    expect(row('Заметка').querySelector('.mdi-file-document-outline')).toBeTruthy()
    expect(getByText(/2,5 МБ/)).toBeTruthy()
    // совсем маленький файл всё равно не «0 КБ»
    expect(getByText(/· 1 КБ/)).toBeTruthy()
  })
})

describe('Документы: администратор', () => {
  it('удаляет документ дома после подтверждения', async () => {
    await renderRoute('/more/documents', ADMIN)
    await click(await waitFor(() => getButton(`Удалить ${PROTOCOL}`)))
    await waitFor(() => getByText(`Удалить «${PROTOCOL}»?`))
    expect(getByText(/Вернуть не получится/)).toBeTruthy()
    await click(getButton('Удалить', inDrawer()))
    await waitFor(() => getByText('Документ удалён'))
    await waitFor(() => !queryButton(`Открыть ${PROTOCOL}`))
    expect(getButton(`Открыть ${CONTRACT}`)).toBeTruthy()
  })

  it('кнопка «Оставить» закрывает вопрос и ничего не удаляет', async () => {
    await renderRoute('/more/documents', ADMIN)
    await click(await waitFor(() => getButton(`Удалить ${CONTRACT}`)))
    await waitFor(() => getByText(`Удалить «${CONTRACT}»?`))
    await click(getButton('Оставить', inDrawer()))
    await waitFor(() => !queryByText(`Удалить «${CONTRACT}»?`))
    expect(getButton(`Открыть ${CONTRACT}`)).toBeTruthy()
  })

  it('удалив все документы, видит приглашение загрузить протокол', async () => {
    vi.spyOn(documentsApi, 'list').mockResolvedValue([])
    await renderRoute('/more/documents', ADMIN)
    await waitFor(() => getByText('Документов дома пока нет'))
    expect(getByText('Загрузите протокол собрания или договор управления')).toBeTruthy()
    expect(getButton('Загрузить')).toBeTruthy()
  })

  it('загружает документ дома, который видят все жители', async () => {
    await renderRoute('/more/documents', ADMIN)
    await waitFor(() => getByText(PROTOCOL))
    // плавающая кнопка над списком
    await click(getButton('Загрузить'))
    await waitFor(() => getByText('Документ дома: видят все жители'))
    const houseRadio = document.querySelector<HTMLInputElement>('input[value="house"]')!
    expect(houseRadio.checked).toBe(true)

    await pickFile(new File(['акт'], 'akt.docx', { type: 'application/msword' }))
    await type(getField('Название', inDrawer()), 'Акт весеннего осмотра')
    await click(getButton('Загрузить', inDrawer()))
    await waitFor(() => getByText('Документ загружен'))
    expect(getByText('Его видят все жители дома')).toBeTruthy()
    await waitFor(() => getButton('Открыть Акт весеннего осмотра'))
  })

  it('личный документ администратора после загрузки открывает вкладку «Мои»', async () => {
    await renderRoute('/more/documents', ADMIN)
    await waitFor(() => getByText(PROTOCOL))
    await click(getButton('Загрузить'))
    await waitFor(() => getByText('Личный: вижу только я'))
    await click(document.querySelector<HTMLInputElement>('input[value="personal"]')!)
    await pickFile(new File(['x'], 'pasport.pdf', { type: 'application/pdf' }))
    await click(getButton('Загрузить', inDrawer()))
    await waitFor(() => getByText('Его видите только вы'))
    await waitFor(() => getButton('Открыть pasport'))
    expect(document.querySelector('[role="radio"][aria-checked="true"]')?.textContent).toContain(
      'Мои',
    )
  })

  it('сервер не принял документ дома: показывает причину', async () => {
    await renderRoute('/more/documents', ADMIN)
    await waitFor(() => getByText(PROTOCOL))
    scenario.role = 'resident'
    await click(getButton('Загрузить'))
    await pickFile(new File(['x'], 'plan.pdf', { type: 'application/pdf' }))
    await click(getButton('Загрузить', inDrawer()))
    await waitFor(() => getByText('Не удалось загрузить'))
    expect(getByText('Документы дома загружает администратор')).toBeTruthy()
  })

  it('ошибку удаления показывает тостом и оставляет документ в списке', async () => {
    await renderRoute('/more/documents', ADMIN)
    vi.spyOn(documentsApi, 'remove').mockRejectedValue(new Error('Нет связи с сервером'))
    await click(await waitFor(() => getButton(`Удалить ${PROTOCOL}`)))
    await waitFor(() => getByText(`Удалить «${PROTOCOL}»?`))
    await click(getButton('Удалить', inDrawer()))
    await waitFor(() => getByText('Нет связи с сервером'))
    expect(getButton(`Открыть ${PROTOCOL}`)).toBeTruthy()
  })
})
