"""Каталог ачивок, очков за действия и уровней жителя."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AchievementDef:
    code: str
    title: str
    description: str
    icon: str
    points: int
    action: str
    threshold: int


ACHIEVEMENTS: tuple[AchievementDef, ...] = (
    AchievementDef(
        "first_issue", "Зоркий глаз", "Сообщил о первой проблеме дома", "mdi-eye-outline", 20, "issue_created", 1
    ),
    AchievementDef(
        "issue_sent",
        "Дело сдвинулось",
        "Твоя заявка набрала голоса и ушла исполнителю",
        "mdi-send-check",
        50,
        "issue_sent",
        1,
    ),
    AchievementDef(
        "issue_resolved",
        "Починили!",
        "Проблема, о которой ты сообщил, решена",
        "mdi-hammer-wrench",
        50,
        "issue_resolved",
        1,
    ),
    AchievementDef("voter_10", "Голос дома", "Поддержал 10 заявок соседей", "mdi-vote", 30, "issue_voted", 10),
    AchievementDef(
        "first_vote", "Не проходи мимо", "Первый голос за заявку соседа", "mdi-thumb-up-outline", 10, "issue_voted", 1
    ),
    AchievementDef("gift", "Щедрая душа", "Отдал вещь соседям даром", "mdi-gift-outline", 30, "listing_free", 1),
    AchievementDef(
        "market_5",
        "Хозяйственный",
        "Разместил 5 объявлений на барахолке",
        "mdi-storefront-outline",
        30,
        "listing_created",
        5,
    ),
    AchievementDef("organizer", "Организатор", "Создал событие для двора", "mdi-calendar-star", 40, "event_created", 1),
    AchievementDef("subbotnik", "Чистый двор", "Записался на субботник", "mdi-broom", 30, "subbotnik_joined", 1),
    AchievementDef(
        "social_3", "Душа компании", "Записался на 3 события двора", "mdi-account-group", 30, "event_joined", 3
    ),
    AchievementDef(
        "talker_10",
        "Живое общение",
        "Оставил 10 вежливых комментариев",
        "mdi-comment-text-multiple-outline",
        15,
        "comment_created",
        10,
    ),
)

BY_CODE = {a.code: a for a in ACHIEVEMENTS}

ACTION_POINTS: dict[str, int] = {
    "issue_created": 10,
    "issue_voted": 2,
    "issue_sent": 20,
    "issue_resolved": 20,
    "listing_created": 5,
    "listing_free": 10,
    "event_created": 15,
    "event_joined": 5,
    "subbotnik_joined": 10,
    "comment_created": 1,
}

LEVELS: tuple[tuple[int, str], ...] = (
    (0, "Новосёл"),
    (50, "Сосед"),
    (120, "Надёжный сосед"),
    (200, "Активист"),
    (320, "Душа двора"),
    (500, "Хранитель дома"),
    (750, "Старейшина"),
    (1000, "Легенда дома"),
)


def level_for(points: int) -> tuple[int, str, int | None]:
    """Возвращает номер уровня, название и порог следующего уровня."""
    level = 1
    for i, (threshold, _) in enumerate(LEVELS):
        if points >= threshold:
            level = i + 1
    title = LEVELS[level - 1][1]
    next_points = LEVELS[level][0] if level < len(LEVELS) else None
    return level, title, next_points
