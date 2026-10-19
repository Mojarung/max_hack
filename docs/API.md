# Контракт REST API

Базовый префикс: `/api/v1`. Формат: JSON, даты в ISO 8601 с часовым поясом (UTC). Интерактивная документация: `http://localhost:8000/docs`, схема `http://localhost:8000/openapi.json`.

## Аутентификация

Мини-приложение передаёт строку `window.WebApp.initData` в заголовке:

```
X-Max-Init-Data: <initData>
```

Сервер проверяет подпись HMAC-SHA256 по алгоритму MAX (ключ `HMAC_SHA256("WebAppData", BOT_TOKEN)`), срок жизни 24 часа, и создаёт пользователя при первом входе.

В мок-режиме (`MOCK_MAX=true`) вместо подписи принимается заголовок `X-Dev-User: <max_user_id>` одного из демо-жителей (`GET /dev/users`).

`GET /meta` без авторизации отвечает `{"bot_username": "id732818139220_bot", "mock": false}`. По нему мини-приложение, открытое вне MAX, выбирает: демо-жители (сервер в мок-режиме) или экран «Кузя живёт в MAX» со ссылкой на бота и демо в браузере на данных в памяти.

Дом определяется так:

1. заголовок `X-House-Id`: пускаем, только если житель состоит в этом доме (сверяется с участниками чата MAX, кэш 10 минут), иначе 403;
2. чат из `initData` (`chat.id` сопоставляется с `houses.max_chat_id`);
3. активный дом жителя (`users.active_house_id`): последний выбранный в приложении или чат, куда он писал последним. Этот же дом видит бот в личке;
4. первый настоящий дом жителя, затем демо-дом.

Перед шагом 3 сервер ищет чаты с Кузей, где состоит житель (`GET /chats/{id}/members?user_ids=...`, не чаще раза в 10 минут), и сам добавляет эти дома. Администратор или владелец чата MAX становится администратором дома, вышедший из чата теряет доступ (если Кузя администратор чата).

Для SSE (`EventSource` не умеет заголовки) те же значения передаются query-параметрами `init_data` или `dev_user`.

Ошибки: `{"detail": "<текст для человека>"}` с кодами 400/401/403/404/409/422/429.

## Профиль и дом

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/me` | `MeOut` |
| POST | `/me/onboarded` | `MeOut`, житель прошёл обучалку первого входа |
| PUT | `/me/avatar` | `MeOut`. Тело `{"preset": 1..9}` - готовая картинка, `{"preset": null}` - вернуть фото из MAX. Выбор хранится в `user.avatar` (`preset:N`, `upload` или `null`) и стоит выше фото из MAX |
| POST | `/me/avatar/photo` | `MeOut`. multipart, поле `photo`: своё фото, сжимается до 1600 px без EXIF, как фото заявок |
| GET | `/houses?refresh=true` | `HouseBrief[]`, дома жителя; `refresh` заново ищет чаты с Кузей |
| GET | `/house/pulse` | `PulseOut`, состояние маскота Кузи |
| GET | `/dev/users` | `DevUser[]`, только в мок-режиме |
| PATCH | `/house` | `MeOut`. Тело: `title`, `address`, `lat`, `lon`, `vote_threshold_pct`, `info`, `uk_name`, `uk_email`, `uk_phone`, `setup_done` (только администратор дома), `apartment` (своя квартира, любой житель). Общую демо-УК не меняет, а заводит дому свою запись |
| POST | `/house/sync` | `{"members": 40, "bot_is_admin": true}`, сверка жителей и администраторов с чатом MAX (администратор) |
| GET | `/house/geocode?q=` | `[{"title", "lat", "lon"}]`, координаты по адресу через OpenStreetMap Nominatim (администратор) |
| GET | `/people` | `Neighbour[]`, жители дома |
| GET | `/people/{id}` | `ProfileOut`: уровень, статистика помощи дому, награды, `thanks_count`, `thanked_by_me`. Только жители того же дома |
| POST | `/people/{id}/thanks` | `ProfileOut`. Спасибо соседу: +5 очков ему, не чаще раза в сутки от одного жителя (`409` при повторе). Кузя сообщает соседу в личку |
| POST | `/people/{id}/message` | `{"ok": true}`. Тело `{"text": "..."}` (1-1000 символов): Кузя пересылает сообщение соседу в личку MAX, MAX id остаётся скрытым. Одному соседу не чаще раза в минуту (`429`) |

```jsonc
// MeOut
{
  "user": {"id": 1, "max_user_id": 1001, "first_name": "Анна", "last_name": "Иванова",
           "username": "anna", "photo_url": null, "apartment": "12",
           "points": 140, "level": 3, "level_title": "Надёжный сосед", "next_level_points": 200},
  "house": {"id": 1, "title": "ЖК «Сказочный», дом 7", "address": "Ульяновск, ул. ...",
            "lat": 54.38, "lon": 48.60, "members_count": 40, "vote_threshold_pct": 15,
            "uk_name": "УК ...", "uk_email": "uk@example.org", "uk_phone": "+7 ...",
            "info": "Диспетчерская ...", "setup_done": true, "is_demo": false,
            "has_chat": true, "bot_is_admin": true},
  "role": "resident",           // resident | admin
  "mock": true                  // сервер в мок-режиме
}

// PulseOut
{
  "mood": "happy",              // happy | ok | worried | sad | alarm
  "score": 78,                  // 0..100, «здоровье дома»
  "level": 4, "xp": 1320, "xp_next": 1600,
  "phrase": "Дом в порядке! Субботник в субботу, приходи",
  "stats": {"open_issues": 3, "overdue_issues": 0, "resolved_30d": 5,
            "upcoming_events": 1, "active_listings": 7, "active_alert": false}
}
```

## Проблемы дома

Жизненный цикл: `voting` → (порог голосов) → `sent` → `in_progress` → `resolved`; также `rejected`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/issues?status=&q=` | | `IssueOut[]` |
| GET | `/issues/{id}` | | `IssueDetail` |
| POST | `/issues` | multipart: `description` (обяз.), `title`, `location_hint`, `photos` (до 5 файлов, jpeg/png/webp, до 10 МБ) | `IssueDetail`, 201 |
| POST | `/issues/similar` | `{"text": "..."}` | `IssueOut[]` с полем `score`, поиск дублей |
| POST | `/issues/classify` | `{"text": "..."}` | `Classification` |
| POST | `/issues/{id}/vote` | | `IssueDetail` |
| DELETE | `/issues/{id}/vote` | | `IssueDetail` |
| POST | `/issues/{id}/status` | `{"status": "in_progress"\|"resolved"\|"rejected", "note": "..."}` (автор или admin) | `IssueDetail` |

```jsonc
// IssueOut
{
  "id": 5, "title": "Течёт крыша над 9 этажом", "description": "...",
  "category": "roof", "category_title": "Кровля",
  "status": "voting", "status_title": "Идёт голосование",
  "votes_count": 3, "votes_needed": 6, "voted_by_me": false,
  "photos": ["/api/v1/media/issues/ab12.jpg"],
  "author": {"id": 1, "first_name": "Анна", "last_name": "Иванова", "photo_url": null},
  "responsible_org": {"name": "УК «Домсервис»", "kind": "uk", "kind_title": "Управляющая организация"},
  "created_at": "...", "sent_at": null, "deadline_at": null, "is_overdue": false,
  "score": null
}
// IssueDetail = IssueOut + 
{
  "legal_basis": "ПП РФ № 290, п. 7; ПП РФ № 170, п. 4.6.1.10",
  "deadline_hours": 24,
  "appeal_text": "Официальное обращение ... (появляется после отправки)",
  "appeal_channel": "test_email:uk-test@domovoy.local", // model | test_email:<адрес>: модельная интеграция
  "location_hint": "подъезд 2, 9 этаж",
  "timeline": [{"status": "voting", "status_title": "...", "note": "...", "created_at": "..."}]
}
// Classification
{"category": "roof", "category_title": "Кровля", "org_kind": "uk",
 "org_name": "УК «Домсервис»", "legal_basis": "...", "deadline_hours": 24,
 "confidence": 0.82, "source": "llm"}   // source: llm | rules
```

## Барахолка

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/listings?q=&category=&free=true&scope=` | | `ListingOut[]`. `scope`: `active` (по умолчанию, в продаже и забронированные), `mine` (свои, включая закрытые), `closed` (завершённые) |
| GET | `/listings/{id}` | | `ListingOut` |
| POST | `/listings` | multipart: `title`, `description`, `price` (0 = даром), `category`, `photos` | `ListingOut`, 201 |
| PATCH | `/listings/{id}` | `{"status": "active"\|"reserved"\|"closed"}` (только автор) | `ListingOut` |
| DELETE | `/listings/{id}` | | 204 |
| POST | `/listings/{id}/contact` | `{"message": "..."}` бот пишет продавцу в личку | `{"ok": true}` |

Категории (`GET /listings/categories`): `furniture`, `electronics`, `kids`, `clothes`, `tools`, `plants`, `food`, `services`, `other`.

```jsonc
// ListingOut
{"id": 3, "title": "Детская коляска", "description": "...", "price": 0, "is_free": true,
 "category": "kids", "category_title": "Детское", "status": "active",
 "photos": ["/api/v1/media/listings/x.jpg"],
 "author": {"id": 2, "first_name": "Олег", "last_name": "...", "photo_url": null, "apartment": "34"},
 "is_mine": false, "created_at": "..."}
```

## События двора

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/events?scope=upcoming\|past` | | `EventOut[]` |
| GET | `/events/{id}` | | `EventDetail` |
| POST | `/events` | `{"title","description","kind","starts_at","place","max_participants"?}` | `EventDetail`, 201 |
| PATCH | `/events/{id}` | `{"description": "..."}`, только организатор или администратор | `EventDetail`, 403 для остальных |
| POST | `/events/{id}/photos` | multipart: `photos` (файлы), всего у события не больше 5 фото | `EventDetail` |
| DELETE | `/events/{id}/photos/{index}` | номер фото с нуля | `EventDetail` |
| POST | `/events/{id}/join` | | `EventDetail` |
| DELETE | `/events/{id}/join` | | `EventDetail` |
| GET | `/events/{id}/comments` | | `CommentOut[]` |
| POST | `/events/{id}/comments` | `{"text": "..."}` | `CommentOut`, 201, или 422 если модерация отклонила |

`kind`: `subbotnik`, `meeting`, `holiday`, `sport`, `kids`, `other`.

```jsonc
// EventOut
{"id": 1, "title": "Осенний субботник", "description": "...", "kind": "subbotnik",
 "kind_title": "Субботник", "starts_at": "...", "place": "Двор, у детской площадки",
 "max_participants": null, "participants_count": 8, "joined_by_me": true,
 "comments_count": 4, "author": {...}, "created_at": "..."}
// EventDetail = EventOut + {"participants": [UserShort]}
// CommentOut
{"id": 1, "event_id": 1, "author": {...}, "text": "Возьму грабли", "created_at": "..."}
```

## Ачивки

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/achievements` | `{"items": AchievementOut[], "leaderboard": LeaderRow[]}` |

```jsonc
// AchievementOut
{"code": "first_issue", "title": "Зоркий глаз", "description": "Сообщил о первой проблеме",
 "icon": "mdi-eye", "points": 20, "earned": true, "awarded_at": "..."}
// LeaderRow
{"rank": 1, "user": {...}, "points": 320, "level_title": "Хранитель дома"}
```

## Безопасность

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/shelters?lat=&lon=` | | `ShelterOut[]`, отсортированы по расстоянию |
| GET | `/alerts/active` | | `AlertOut` или `null` |
| POST | `/alerts` | `{"kind": "drone", "message": "..."}` (admin или мок-режим) | `AlertOut` |
| POST | `/alerts/{id}/end` | | `AlertOut` |

```jsonc
// ShelterOut
{"id": 1, "name": "Укрытие (подвал школы № 12)", "address": "...", "lat": 54.38, "lon": 48.60,
 "capacity": 300, "kind": "shelter", "distance_m": 420,
 "yandex_url": "https://yandex.ru/maps/?rtext=54.38,48.60~54.381,48.605&rtt=pd",
 "osm_url": "https://www.openstreetmap.org/?mlat=...&mlon=...#map=18/..."}
// AlertOut
{"id": 1, "kind": "drone", "kind_title": "Беспилотная опасность", "message": "...",
 "active": true, "created_at": "...", "ended_at": null}
```

## Поиск и ассистент

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/search?q=` | | `{"issues": IssueOut[], "events": EventOut[], "listings": ListingOut[]}` |
| POST | `/assistant/chat` | `{"message": "..."}` | `{"reply": "...", "tools_used": ["search_issues"]}` |

## Объявления дома

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/announcements` | | `AnnouncementOut[]`, закреплённые сверху |
| POST | `/announcements` | `{"title", "text", "pin"}`; `pin` только для администратора | `AnnouncementOut`, 201. Кузя публикует объявление в чате дома (и закрепляет при `pin`) |
| PATCH | `/announcements/{id}` | `{"pinned": true}` (администратор) | `AnnouncementOut` |
| DELETE | `/announcements/{id}` | автор или администратор | 204 |

В чате объявление создаёт агент: «@бот сделай объявление о субботнике в субботу в 11» (инструмент `create_announcement`; с датой заодно создаётся событие с кнопкой «Иду»).

## Документы

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/documents?scope=house\|personal` | | `DocumentOut[]`: документы дома и свои личные |
| POST | `/documents` | multipart: `file`, `title`, `scope` (`house` только администратор) | `DocumentOut`, 201. PDF, Word, Excel, ODT, TXT, фото; до 20 МБ; у фото удаляется EXIF |
| GET | `/documents/{id}/link` | | `{"url": "/api/v1/files/{id}?exp=...&sig=...", "expires_at"}`, ссылка живёт 15 минут |
| DELETE | `/documents/{id}` | личный: владелец; дома: администратор или загрузивший | 204 |

Чужие личные документы недоступны (404). Файл отдаётся только по подписанной HMAC ссылке.

## Реалтайм (SSE)

`GET /realtime/stream?house_id=1&dev_user=1001` (или `init_data=...`). Поток `text/event-stream`, событие имеет `event: <тип>` и `data: <json>`:

`issue.created`, `issue.updated`, `listing.created`, `listing.updated`, `event.created`, `event.updated`, `comment.created`, `announcement.created`, `announcement.updated`, `alert.started`, `alert.ended`, `achievement.awarded` (data содержит `user_id`), `pulse.changed`, `chat.message` (эмулятор чата). Каждые 15 секунд приходит `ping`.

## Эмулятор чата (только мок-режим)

Позволяет пройти сценарии бота без MAX. Сообщения идут через тот же обработчик, что и реальные апдейты MAX.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/dev/chat/messages?chat_id=` | | `ChatMessage[]` |
| POST | `/dev/chat/send` | `{"chat_id": -100, "user_id": 1001, "text": "...", "photos": ["data:image/jpeg;base64,..."]}`: до 3 фото, бот получает их вложениями `image`, как из MAX; нужен текст или фото | `{"ok": true}` |
| POST | `/dev/chat/callback` | `{"chat_id": -100, "user_id": 1001, "message_id": "m1", "payload": "..."}` | `{"ok": true}` |
| GET | `/dev/chats` | | `[{"chat_id": -100, "title": "Чат дома 7", "type": "chat"}, {"chat_id": 1001, "title": "Личка с ботом", "type": "dialog"}]` |

```jsonc
// ChatMessage
{"id": "m12", "chat_id": -100, "from": {"user_id": 1001, "name": "Анна Иванова"} /* null = бот */,
 "text": "...", "buttons": [[{"type": "callback", "text": "Голосую", "payload": "vote:5"},
                             {"type": "open_app", "text": "Открыть", "payload": "issue_5"}]],
 "deleted": false, "notice": null, "created_at": "..."}
```

## MCP-серверы агента

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/mcp/servers` | | `McpServerOut[]` |
| POST | `/mcp/servers` | `{"name", "transport": "streamable_http"\|"sse", "url", "headers": {}}` (admin) | `McpServerOut` |
| DELETE | `/mcp/servers/{id}` | | 204 |
| GET | `/mcp/servers/{id}/tools` | | `[{"name", "description"}]` |

## Медиа

`GET /media/{key}` отдаёт файл из MinIO (прокси, чтобы мини-приложению не нужен был прямой доступ к S3).
