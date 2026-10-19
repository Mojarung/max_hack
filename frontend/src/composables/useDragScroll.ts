/**
 * Горизонтальные ленты чипов (`.chips-scroll`) и карусели фото (`.photo-carousel`) листаются и мышью:
 * перетаскиванием, а ленты чипов ещё и колесом. Пальцем их и так листает браузер; на ПК без этого
 * ленту не прокрутить, а колесо уводит страницу.
 */
const SELECTOR = '.chips-scroll, .photo-carousel'
// Колесо листает вбок только ленты чипов: над фото в списке оно должно прокручивать страницу
const WHEEL_SELECTOR = '.chips-scroll'
// Сдвиг мыши, после которого нажатие считается перетаскиванием, а не кликом по чипу
const DRAG_THRESHOLD_PX = 6

export function installDragScroll(): void {
  let strip: HTMLElement | null = null
  let startX = 0
  let startScroll = 0
  let dragged = false

  document.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return
    const el = (e.target as Element | null)?.closest<HTMLElement>(SELECTOR)
    if (!el || el.scrollWidth <= el.clientWidth) return
    strip = el
    startX = e.clientX
    startScroll = el.scrollLeft
    dragged = false
  })

  document.addEventListener('pointermove', (e) => {
    if (!strip) return
    const dx = e.clientX - startX
    if (!dragged && Math.abs(dx) < DRAG_THRESHOLD_PX) return
    dragged = true
    strip.classList.add('chips-scroll--dragging')
    strip.scrollLeft = startScroll - dx
  })

  const stop = () => {
    strip?.classList.remove('chips-scroll--dragging')
    strip = null
  }
  document.addEventListener('pointerup', stop)
  document.addEventListener('pointercancel', stop)

  // после перетаскивания отпускание кнопки не должно нажимать чип под курсором
  document.addEventListener(
    'click',
    (e) => {
      if (!dragged) return
      dragged = false
      e.stopPropagation()
      e.preventDefault()
    },
    true,
  )

  // колесо мыши над лентой листает её вбок, пока есть куда; дальше - страницу
  document.addEventListener(
    'wheel',
    (e) => {
      const el = (e.target as Element | null)?.closest<HTMLElement>(WHEEL_SELECTOR)
      if (!el || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
      const max = el.scrollWidth - el.clientWidth
      if (max <= 0) return
      const next = el.scrollLeft + e.deltaY
      if ((e.deltaY < 0 && el.scrollLeft <= 0) || (e.deltaY > 0 && el.scrollLeft >= max)) return
      e.preventDefault()
      el.scrollLeft = Math.max(0, Math.min(max, next))
    },
    { passive: false },
  )
}
