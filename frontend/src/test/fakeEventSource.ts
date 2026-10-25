/**
 * EventSource для тестов реального времени: запоминает созданные подключения,
 * а тест сам «открывает» их, присылает события и обрывает связь.
 */
type Listener = (event: MessageEvent<string>) => void

export class FakeEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  readonly url: string
  readyState = FakeEventSource.CONNECTING
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private readonly listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  static last(): FakeEventSource {
    const es = FakeEventSource.instances.at(-1)
    if (!es) throw new Error('EventSource ещё не создан')
    return es
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED
  }

  /** Сервер принял подключение. */
  open(): void {
    this.readyState = FakeEventSource.OPEN
    this.onopen?.()
  }

  /** Сервер прислал событие; объект уходит как JSON, строка - как есть. */
  emit(type: string, data: unknown): void {
    const raw = typeof data === 'string' ? data : JSON.stringify(data)
    this.listeners.get(type)?.forEach((listener) => listener(new MessageEvent(type, { data: raw })))
  }

  /** Обрыв: closed=true - браузер сдался и не переподключается сам. */
  fail(closed = true): void {
    this.readyState = closed ? FakeEventSource.CLOSED : FakeEventSource.CONNECTING
    this.onerror?.()
  }
}
