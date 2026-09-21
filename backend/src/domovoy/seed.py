"""Демо-данные пилотного дома (Казань). Все данные синтетические и помечены is_demo.

Сид идемпотентен: если справочник организаций уже заполнен, ничего не делает.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select

from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.embeddings import embed
from domovoy.modules.events.models import Event, EventComment, EventParticipant
from domovoy.modules.issues.catalog import category
from domovoy.modules.issues.models import Issue, IssueUpdate, IssueVote
from domovoy.modules.market.models import Listing
from domovoy.modules.misc_models import MockChatMessage, Shelter, UserAchievement
from domovoy.modules.users.models import House, Membership, Organization, User

log = structlog.get_logger(__name__)

DEMO_CHAT_ID = -100
HOUSE_LAT, HOUSE_LON = 55.78874, 49.12214

ORGS = [
    ("uk", "УК «Домсервис» (демо)", "demo-uk@example.org", "+7 (843) 000-00-01"),
    ("gas", "Аварийная газовая служба", None, "104"),
    ("regop", "Региональный оператор по обращению с ТКО (демо)", "demo-tko@example.org", "+7 (843) 000-00-02"),
    ("municipal", "Администрация района г. Казани (демо)", "demo-adm@example.org", "+7 (843) 000-00-03"),
    ("gji", "Госжилинспекция Республики Татарстан", None, None),
]
USERS = [
    (1001, "Анна", "Иванова", "12", "admin", 260),
    (1002, "Олег", "Петров", "34", "resident", 140),
    (1003, "Мария", "Сафина", "5", "resident", 95),
    (1004, "Ильдар", "Галиев", "77", "resident", 60),
    (1005, "Светлана", "Козлова", "101", "resident", 35),
    (1006, "Тимур", "Хасанов", "56", "resident", 20),
    (1007, "Елена", "Смирнова", "88", "resident", 10),
    (1008, "Рустам", "Зарипов", "23", "resident", 0),
]
# (смещение по широте, по долготе, название, адрес, вместимость)
SHELTERS = [
    (0.0021, 0.0034, "Укрытие в подвале школы (демо)", "ул. Демонстрационная, 12", 400),
    (-0.0030, 0.0012, "Подземный переход (демо)", "пересечение ул. Примерной и ул. Тестовой", 250),
    (0.0048, -0.0041, "Укрытие ТЦ «Пример» (демо)", "ул. Макетная, 3", 800),
    (-0.0062, -0.0035, "Паркинг жилого комплекса (демо)", "ул. Образцовая, 20", 300),
    (0.0075, 0.0060, "Станция метро (демо)", "пл. Условная", 1500),
    (-0.0015, 0.0081, "Укрытие поликлиники (демо)", "ул. Шаблонная, 8", 150),
]


async def seed_demo() -> None:
    async with get_sessionmaker()() as session:
        if await session.scalar(select(func.count()).select_from(Organization)):
            return
        now = datetime.now(UTC)
        orgs = {kind: Organization(kind=kind, name=name, email=email, phone=phone) for kind, name, email, phone in ORGS}
        session.add_all(orgs.values())
        await session.flush()

        house = House(
            max_chat_id=DEMO_CHAT_ID,
            title="Дом 7 на Демонстрационной",
            address="г. Казань, ул. Демонстрационная, д. 7 (демо-адрес)",
            lat=HOUSE_LAT,
            lon=HOUSE_LON,
            members_count=40,
            vote_threshold_pct=get_settings().default_vote_threshold_pct,
            uk_org_id=orgs["uk"].id,
            is_demo=True,
        )
        session.add(house)
        users = [
            User(max_user_id=mid, first_name=fn, last_name=ln, apartment=apt, points=pts, is_demo=True)
            for mid, fn, ln, apt, _, pts in USERS
        ]
        session.add_all(users)
        await session.flush()
        session.add_all(
            Membership(user_id=u.id, house_id=house.id, role=role)
            for u, (*_, role, _pts) in zip(users, USERS, strict=True)
        )

        def issue(author: int, text: str, cat: str, status: str, votes: int, age_h: int, place: str) -> Issue:
            c = category(cat)
            org = orgs["uk"] if c.org_kind == "uk" else orgs[c.org_kind]
            created = now - timedelta(hours=age_h)
            sent = created + timedelta(hours=3) if status != "voting" else None
            item = Issue(
                house_id=house.id,
                author_id=users[author].id,
                title=text.split(".")[0],
                description=text,
                location_hint=place,
                category=cat,
                classifier_source="rules",
                classifier_confidence=0.8,
                status=status,
                votes_count=votes,
                votes_needed=6,
                responsible_org_id=org.id,
                legal_basis=c.legal_basis,
                deadline_hours=c.deadline_hours,
                sent_at=sent,
                deadline_at=sent + timedelta(hours=c.deadline_hours) if sent else None,
                resolved_at=now - timedelta(days=2) if status == "resolved" else None,
                embedding=embed(f"{text} {place}"),
                created_at=created,
            )
            return item

        issues = [
            issue(
                1,
                "Течёт крыша над 9 этажом. После дождя в подъезде лужа, штукатурка намокла.",
                "roof",
                "voting",
                4,
                20,
                "подъезд 2, 9 этаж",
            ),
            issue(
                2,
                "Сломаны качели на детской площадке. Сиденье висит на одной цепи, дети могут пораниться.",
                "yard",
                "voting",
                2,
                30,
                "детская площадка",
            ),
            issue(
                0,
                "Лифт в 3 подъезде не работает третий день. Пожилым жильцам тяжело подниматься.",
                "elevator",
                "sent",
                7,
                16,
                "подъезд 3",
            ),
            issue(
                3,
                "Не вывозят мусор. Контейнеры переполнены четвёртые сутки.",
                "garbage",
                "sent",
                8,
                80,
                "контейнерная площадка",
            ),
            issue(
                4,
                "Не горит свет на лестнице 1 подъезда. Вечером совсем темно.",
                "electricity",
                "resolved",
                6,
                200,
                "подъезд 1",
            ),
        ]
        session.add_all(issues)
        await session.flush()
        for it in issues:
            for u in users[: it.votes_count]:
                session.add(IssueVote(issue_id=it.id, user_id=u.id))
            session.add(IssueUpdate(issue_id=it.id, status="voting", note="Заявка создана", created_at=it.created_at))
            if it.sent_at:
                session.add(
                    IssueUpdate(
                        issue_id=it.id,
                        status="sent",
                        note="Порог голосов набран, обращение отправлено",
                        created_at=it.sent_at,
                    )
                )
            if it.status == "resolved":
                session.add(
                    IssueUpdate(
                        issue_id=it.id,
                        status="resolved",
                        note="УК заменила светильники",
                        created_at=it.resolved_at or now,
                    )
                )

        listings = [
            (2, "Детская коляска", "Прогулочная, в хорошем состоянии. Отдам даром, заберите из кв. 5.", 0, "kids"),
            (1, "Дрель на выходные", "Могу одолжить дрель с набором свёрл, верните в понедельник.", 0, "tools"),
            (4, "Шкаф-купе", "Ширина 1,5 м, самовывоз, помогу разобрать.", 3000, "furniture"),
            (3, "Рассада помидоров", "Черри и бычье сердце, 10 кустиков.", 150, "plants"),
            (6, "Книги для школьников", "Хрестоматии 5-7 класс, даром.", 0, "kids"),
        ]
        session.add_all(
            Listing(
                house_id=house.id,
                author_id=users[a].id,
                title=t,
                description=d,
                price=p,
                category=c,
                embedding=embed(f"{t} {d}"),
                created_at=now - timedelta(hours=5 * i + 1),
            )
            for i, (a, t, d, p, c) in enumerate(listings)
        )

        days_to_saturday = (5 - now.astimezone().weekday()) % 7 or 7
        saturday = (now + timedelta(days=days_to_saturday)).replace(hour=8, minute=0, second=0, microsecond=0)
        subbotnik = Event(
            house_id=house.id,
            author_id=users[0].id,
            title="Осенний субботник",
            description="Уберём листья, покрасим скамейки, посадим кусты. Инвентарь даёт УК, чай с нас!",
            kind="subbotnik",
            starts_at=saturday,
            place="Двор, у детской площадки",
            participants_count=5,
            comments_count=2,
            embedding=embed("субботник уборка листья скамейки двор"),
        )
        meeting = Event(
            house_id=house.id,
            author_id=users[0].id,
            title="Собрание по капремонту крыши",
            description="Обсудим перенос капремонта крыши на 2027 год и выбор подрядчика.",
            kind="meeting",
            starts_at=(now + timedelta(days=10)).replace(hour=16, minute=0, second=0, microsecond=0),
            place="Холл 1 подъезда",
            participants_count=2,
            embedding=embed("собрание капремонт крыша подрядчик"),
        )
        past = Event(
            house_id=house.id,
            author_id=users[1].id,
            title="Праздник двора",
            description="Играли в футбол, пили чай, дети рисовали мелками.",
            kind="holiday",
            starts_at=now - timedelta(days=14),
            place="Двор",
            participants_count=3,
            reminded=True,
            embedding=embed("праздник двора футбол чай"),
        )
        session.add_all([subbotnik, meeting, past])
        await session.flush()
        for ev, count in ((subbotnik, 5), (meeting, 2), (past, 3)):
            session.add_all(EventParticipant(event_id=ev.id, user_id=u.id) for u in users[:count])
        session.add_all(
            [
                EventComment(event_id=subbotnik.id, author_id=users[1].id, text="Возьму свои грабли и перчатки"),
                EventComment(event_id=subbotnik.id, author_id=users[2].id, text="Испеку пирог к чаю 🥧"),
            ]
        )

        session.add_all(
            Shelter(
                name=name,
                address=f"г. Казань, {addr}",
                lat=HOUSE_LAT + dlat,
                lon=HOUSE_LON + dlon,
                capacity=cap,
                source="demo",
            )
            for dlat, dlon, name, addr, cap in SHELTERS
        )
        session.add_all(
            [
                UserAchievement(user_id=users[0].id, code="first_issue"),
                UserAchievement(user_id=users[0].id, code="organizer"),
                UserAchievement(user_id=users[0].id, code="issue_sent"),
                UserAchievement(user_id=users[1].id, code="first_issue"),
                UserAchievement(user_id=users[1].id, code="subbotnik"),
                UserAchievement(user_id=users[2].id, code="gift"),
            ]
        )
        session.add(
            MockChatMessage(
                chat_id=DEMO_CHAT_ID,
                text=(
                    "Всем привет! Я Домовой Кузя 🏠 Обращайтесь ко мне по имени: "
                    "«Кузя, какие проблемы в доме?» или «Кузя, создай субботник в субботу в 11 у площадки»."
                ),
                buttons=[[{"type": "open_app", "text": "🏠 Открыть приложение дома", "payload": "home"}]],
            )
        )
        await session.commit()
        log.info("seed.done", house=house.title, users=len(users))
