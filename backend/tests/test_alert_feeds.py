"""Официальные оповещения из лент: классификатор, разбор RSS, t.me и VK, отбор новых постов, выбор домов. Без сети."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from domovoy.modules.misc_models import Alert
from domovoy.modules.safety import feeds, regions
from domovoy.modules.safety.feeds import FeedError, Post
from domovoy.modules.users.models import House

FIXTURES = Path(__file__).parent / "fixtures"

# Структура ленты «Оперативная информация» сайта 73.mchs.gov.ru: RSS 2.0, полный текст в yandex:full-text
RSS_73 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:yandex="http://news.yandex.ru">
    <channel>
        <title>Оперативная информация</title>
        <link>https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya</link>
        <lastBuildDate>Mon, 19 Oct 26 22:55:09 +0400</lastBuildDate>
        <item>
            <title>Оперативный ежедневный прогноз ЧС на 20 октября 2026 года</title>
            <description></description>
            <pubDate>Mon, 19 Oct 26 15:00:00 +0400</pubDate>
            <link>https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/5844763</link>
            <yandex:full-text>
                &lt;p style=&quot;text-align: center;&quot;&gt;&lt;b&gt;&amp;nbsp;Оперативный ежедневный прогноз
                возникновения чрезвычайных ситуаций на 20 октября 2026 г.&lt;/b&gt;&lt;/p&gt;
                &lt;p&gt;&lt;b&gt;Опасные метеорологические явления&lt;/b&gt; – не прогнозируется.&lt;/p&gt;
            </yandex:full-text>
        </item>
        <item>
            <title>Внимание! Беспилотная опасность</title>
            <description></description>
            <pubDate>Mon, 19 Oct 26 14:10:00 +0400</pubDate>
            <link>https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/5844700</link>
            <yandex:full-text>&lt;p&gt;На территории Ульяновской области объявлен режим беспилотной
            опасности.&lt;br&gt;Отойдите от окон, не снимайте БПЛА на телефон.&lt;/p&gt;</yandex:full-text>
        </item>
    </channel>
</rss>
"""


class TestClassify:
    @pytest.mark.parametrize(
        ("text", "event", "kind"),
        [
            ("Внимание! Беспилотная опасность. Отойдите от окон", "start", "drone"),
            ("В Ульяновской области объявлен режим беспилотной опасности", "start", "drone"),
            ("⚡️На территории региона введён режим «Беспилотная опасность»", "start", "drone"),
            ("❗️Угроза атаки БПЛА на территории области. Не подходите к окнам", "start", "drone"),
            ("Внимание! Ракетная опасность! Пройдите в укрытие", "start", "air"),
            ("В городе объявлена воздушная тревога", "start", "air"),
            ("Внимание всем! Слушайте экстренное сообщение", "start", "other"),
            # начало встретилось раньше слова «отбой»: это всё ещё начало
            ("Объявлен режим беспилотной опасности. Отбой сообщим дополнительно", "start", "drone"),
            ("Отбой беспилотной опасности", "end", "drone"),
            ("Режим беспилотной опасности снят. Опасность миновала", "end", "drone"),
            ("Отменён режим ракетной опасности", "end", "air"),
            ("Угроза атаки БПЛА миновала", "end", "drone"),
            ("ОТБОЙ! Угроза атаки БПЛА миновала", "end", "drone"),
        ],
    )
    def test_alerts(self, text: str, event: str, kind: str) -> None:
        verdict = feeds.classify(text)
        assert (verdict.event, verdict.kind) == (event, kind)

    @pytest.mark.parametrize(
        "text",
        [
            "Оперативный ежедневный прогноз ЧС на 20 октября 2026 года",
            "Внимание всем! Сегодня проходит проверка системы оповещения, сирены учебные",
            "Учения: отработка действий при беспилотной опасности",
            "Тренировка по сигналу «Воздушная тревога» пройдёт 3 октября",
            "‼ВНИМАНИЕ‼ Днем 5 апреля ожидается гроза с порывами ветра 15-20 м/с",
            "Огнеборцы ликвидировали пожар в Ленинском районе Ульяновска",
            "Дали отбой строительству развязки",
            "",
        ],
    )
    def test_not_an_alert(self, text: str) -> None:
        assert feeds.classify(text).event is None


class TestRss:
    def test_parses_items_of_mchs_feed(self) -> None:
        posts = feeds.parse_rss(RSS_73)
        assert [p.post_id for p in posts] == [
            "https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/5844763",
            "https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/5844700",
        ]
        forecast = posts[0]
        assert forecast.text.startswith("Оперативный ежедневный прогноз ЧС на 20 октября 2026 года")
        assert "возникновения чрезвычайных ситуаций" in forecast.text
        assert "<" not in forecast.text and "&nbsp;" not in forecast.text
        assert forecast.published_at == datetime(2026, 10, 19, 11, 0, tzinfo=UTC)
        assert forecast.url == forecast.post_id

    def test_forecast_is_not_alert_but_drone_post_is(self) -> None:
        forecast, drone = feeds.parse_rss(RSS_73)
        assert feeds.classify(forecast.text).event is None
        assert feeds.classify(drone.text) == feeds.Verdict("start", "drone")
        assert "Отойдите от окон" in drone.text

    def test_broken_xml_is_feed_error(self) -> None:
        with pytest.raises(FeedError, match="RSS не разобрать"):
            feeds.parse_rss("<rss><channel><item>")

    def test_rss_url_for_region(self) -> None:
        assert regions.mchs_rss_url("RU-ULY") == (
            "https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/rss"
        )
        assert regions.mchs_rss_url("ru-mow").startswith("https://moscow.mchs.gov.ru/")
        with pytest.raises(KeyError):
            regions.mchs_rss_url("XX-1")


class TestTelegramWeb:
    def test_parses_two_posts_from_public_page(self) -> None:
        page = (FIXTURES / "tme_mchs_ulyanovsk.html").read_text(encoding="utf-8")
        posts = feeds.parse_telegram_html(page, "mchs_ulyanovsk")
        assert [p.post_id for p in posts] == ["14140", "14143"]
        storm = posts[0]
        assert storm.text.startswith("‼ВНИМАНИЕ‼")
        assert "ожидается гроза" in storm.text
        assert "<" not in storm.text
        # <br/> стали переносами строк, подпись про подписку осталась в конце текста
        assert "\n" in storm.text and storm.text.rstrip().endswith("| ВК")
        assert storm.published_at == datetime(2026, 4, 5, 6, 51, 23, tzinfo=UTC)
        assert storm.url == "https://t.me/mchs_ulyanovsk/14140"
        assert posts[1].text.startswith("#оперативно")
        # штормовое предупреждение и пожар не тревога о БПЛА
        assert all(feeds.classify(p.text).event is None for p in posts)

    def test_page_without_posts(self) -> None:
        assert feeds.parse_telegram_html("<html><body><div class='tgme_page'>нет канала</div></body></html>", "x") == []


class TestVk:
    def test_parses_wall_get_response(self) -> None:
        data = {
            "response": {
                "count": 2,
                "items": [
                    {"id": 10, "owner_id": -123, "date": 1_790_000_000, "text": "Отбой беспилотной опасности"},
                    {"id": 9, "owner_id": -123, "date": 1_789_999_000, "text": "Внимание! Беспилотная опасность"},
                ],
            }
        }
        posts = feeds.parse_vk_wall(data)
        assert [p.post_id for p in posts] == ["10", "9"]
        assert posts[0].url == "https://vk.com/wall-123_10"
        assert posts[0].published_at == datetime.fromtimestamp(1_790_000_000, UTC)

    def test_api_error_is_feed_error(self) -> None:
        with pytest.raises(FeedError, match="access_token"):
            feeds.parse_vk_wall({"error": {"error_code": 5, "error_msg": "invalid access_token"}})


def post(post_id: str, minutes_ago: int, now: datetime, text: str = "...") -> Post:
    return Post(post_id=post_id, text=text, published_at=now - timedelta(minutes=minutes_ago), url="")


class TestSelectNew:
    NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

    def test_numeric_ids_newer_than_last(self) -> None:
        posts = [post("103", 1, self.NOW), post("101", 30, self.NOW), post("102", 10, self.NOW)]
        fresh = feeds.select_new(posts, "101", self.NOW)
        assert [p.post_id for p in fresh] == ["102", "103"]
        assert feeds.newest_post_id(posts) == "103"

    def test_first_run_takes_only_very_recent_posts(self) -> None:
        posts = [post("5", 5, self.NOW), post("4", 90, self.NOW)]
        assert [p.post_id for p in feeds.select_new(posts, None, self.NOW)] == ["5"]

    def test_old_posts_never_start_alerts(self) -> None:
        posts = [post("7", 60 * 5, self.NOW)]
        assert feeds.select_new(posts, "6", self.NOW) == []

    def test_rss_links_are_compared_by_position(self) -> None:
        posts = [post("https://x/3", 1, self.NOW), post("https://x/2", 5, self.NOW), post("https://x/1", 9, self.NOW)]
        assert [p.post_id for p in feeds.select_new(posts, "https://x/2", self.NOW)] == ["https://x/3"]
        # последняя известная ссылка уже вытеснена из ленты: берём всё свежее
        assert len(feeds.select_new(posts, "https://x/0", self.NOW)) == 3


class TestDispatch:
    def test_houses_without_active_alert_of_this_kind(self) -> None:
        houses = [House(id=1, title="Дом 7", region="RU-ULY"), House(id=2, title="Дом 9", region="RU-ULY")]
        active = [Alert(house_id=1, kind="drone", active=True), Alert(house_id=2, kind="air", active=True)]
        assert [h.id for h in feeds.houses_to_alert(houses, active, "drone")] == [2]
        assert [h.id for h in feeds.houses_to_alert(houses, active, "air")] == [1]

    def test_global_alert_blocks_everyone(self) -> None:
        houses = [House(id=1, title="Дом 7", region="RU-ULY")]
        assert feeds.houses_to_alert(houses, [Alert(house_id=None, kind="drone", active=True)], "drone") == []

    def test_message_is_short_and_names_the_source(self) -> None:
        text = "Внимание! " + "Беспилотная опасность. " * 40
        message = feeds.alert_message(text, "МЧС Ульяновской области (Telegram)")
        body, _, source = message.partition("\n\nИсточник: ")
        assert len(body) <= feeds.MESSAGE_CHARS + 1 and body.endswith("…")
        assert source == "МЧС Ульяновской области (Telegram)"
        assert feeds.alert_message("Отбой", "МЧС") == "Отбой\n\nИсточник: МЧС"


class TestRegions:
    def test_catalog_is_consistent(self) -> None:
        codes = [r.code for r in regions.REGIONS.values()]
        assert len(codes) == len(set(codes)) >= 85
        assert all(code.startswith("RU-") for code in codes)
        numbers = [r.mchs for r in regions.REGIONS.values()]
        assert len(numbers) == len(set(numbers))
        assert regions.REGIONS["RU-ULY"].name == "Ульяновская область"

    def test_normalize(self) -> None:
        assert regions.normalize_code(" ru-uly ") == "RU-ULY"
        assert regions.normalize_code("") is None
        assert regions.normalize_code("Ульяновск") is None
        assert regions.region_name("RU-ULY") == "Ульяновская область"
        assert regions.region_name("RU-XXX") is None
