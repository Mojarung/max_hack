"""Укрытия без сети: разбор ответа Overpass, подписи, откат маршрута на прямую, разбор CSV реестра."""

import time

import pytest

from domovoy.modules.safety import routing, service
from domovoy.modules.safety.catalog import kind_title, registry_source, source_note, source_title
from domovoy.modules.safety.geo import cell_key, haversine_m
from domovoy.modules.safety.importer import ImportError_, parse_csv
from domovoy.modules.safety.osm import (
    OVERPASS_QUERY,
    bbox_around,
    encode_osm_id,
    osm_object_url,
    parse_element,
    parse_elements,
)

PARKING_NODE = {
    "type": "node",
    "id": 123,
    "lat": 54.3857,
    "lon": 48.606,
    "tags": {
        "amenity": "parking",
        "parking": "underground",
        "name": "Паркинг ТЦ «Аквамолл»",
        "addr:street": "Московское шоссе",
        "addr:housenumber": "108",
        "capacity": "350",
    },
}
UNDERPASS_WAY = {
    "type": "way",
    "id": 114371009,
    "center": {"lat": 54.3747467, "lon": 48.581048},
    "tags": {"highway": "footway", "tunnel": "yes", "layer": "-1"},
}


class TestOverpassParsing:
    def test_parking_node_with_name_and_address(self) -> None:
        item = parse_element(PARKING_NODE)
        assert item is not None
        assert item.kind == "parking"
        assert item.name == "Паркинг ТЦ «Аквамолл»"
        assert item.address == "Московское шоссе, 108"
        assert item.capacity == 350
        assert (item.lat, item.lon) == (54.3857, 48.606)
        assert item.osm_id == encode_osm_id("node", 123)
        assert item.url == "https://www.openstreetmap.org/node/123"

    def test_way_takes_center_and_default_name(self) -> None:
        item = parse_element(UNDERPASS_WAY)
        assert item is not None
        assert item.kind == "underpass"
        assert item.name == "Подземный переход"
        assert item.address == ""
        assert item.capacity is None
        assert item.lat == pytest.approx(54.3747467)
        assert osm_object_url(item.osm_id) == "https://www.openstreetmap.org/way/114371009"

    def test_way_without_center_is_dropped(self) -> None:
        assert parse_element({"type": "way", "id": 1, "tags": {"highway": "footway", "tunnel": "yes"}}) is None

    def test_unrelated_object_is_dropped(self) -> None:
        tags = {"amenity": "parking", "parking": "surface"}
        assert parse_element({"type": "node", "id": 1, "lat": 1.0, "lon": 1.0, "tags": tags}) is None
        assert parse_element({"type": "node", "id": 1, "lat": 1.0, "lon": 1.0, "tags": {"highway": "footway"}}) is None

    @pytest.mark.parametrize(
        ("tags", "kind"),
        [
            ({"shelter_type": "bomb_shelter"}, "shelter"),
            ({"bunker_type": "bomb_shelter", "building": "bunker"}, "shelter"),
            ({"building": "bunker"}, "bunker"),
            ({"railway": "subway_entrance"}, "metro"),
            ({"highway": "steps", "tunnel": "yes"}, "underpass"),
        ],
    )
    def test_kind_by_tags(self, tags: dict[str, str], kind: str) -> None:
        item = parse_element({"type": "node", "id": 7, "lat": 55.0, "lon": 37.0, "tags": tags})
        assert item is not None and item.kind == kind

    def test_underpass_segments_merge_into_one_point(self) -> None:
        # один переход в OSM нарезан на отрезки в 10-30 м друг от друга
        segments = [
            {**UNDERPASS_WAY, "id": 1, "center": {"lat": 54.37475, "lon": 48.58105}},
            {**UNDERPASS_WAY, "id": 2, "center": {"lat": 54.37490, "lon": 48.58110}},
            {**UNDERPASS_WAY, "id": 3, "center": {"lat": 54.37500, "lon": 48.58120}},
            # другой переход в километре
            {**UNDERPASS_WAY, "id": 4, "center": {"lat": 54.38400, "lon": 48.58120}},
            PARKING_NODE,
        ]
        kinds = [(s.kind, s.osm_id // 10) for s in parse_elements(segments)]
        assert kinds == [("underpass", 1), ("underpass", 4), ("parking", 123)]

    def test_bbox_widens_with_latitude(self) -> None:
        south, west, north, east = bbox_around(54.3857, 48.606, 2500)
        assert north - south == pytest.approx(0.0449, abs=0.0002)
        # на 54° градус долготы короче, поэтому по долготе рамка шире
        assert east - west == pytest.approx(0.0771, abs=0.0005)
        query = OVERPASS_QUERY.format(timeout=20, south=south, west=west, north=north, east=east)
        assert f"[bbox:{south},{west},{north},{east}]" in query and "around" not in query

    def test_encoding_keeps_types_apart(self) -> None:
        assert encode_osm_id("node", 5) != encode_osm_id("way", 5) != encode_osm_id("relation", 5)
        assert osm_object_url(encode_osm_id("relation", 42)) == "https://www.openstreetmap.org/relation/42"


class TestTitles:
    @pytest.mark.parametrize(
        ("kind", "title"),
        [
            ("shelter", "Защитное сооружение"),
            ("basement", "Подвал"),
            ("parking", "Подземный паркинг"),
            ("underpass", "Подземный переход"),
            ("metro", "Вход в метро"),
            ("bunker", "Бункер"),
            ("unknown", "Укрытие"),
        ],
    )
    def test_kind_title(self, kind: str, title: str) -> None:
        assert kind_title(kind) == title

    def test_source_title_and_note(self) -> None:
        assert source_title("osm") == "OpenStreetMap"
        assert source_title("demo") == "Демо-точка"
        assert source_title("registry:Реестр укрытий Орловской области") == "Реестр укрытий Орловской области"
        assert source_note("osm", False) == "по данным OpenStreetMap"
        assert source_note("registry:X", True) == "из реестра"
        assert registry_source("Реестр") == "registry:Реестр"
        assert registry_source("registry:Реестр") == "registry:Реестр"


class TestGeo:
    def test_cell_key_groups_nearby_points(self) -> None:
        assert cell_key(54.3857, 48.606) == cell_key(54.3999, 48.6199) == "54.38:48.60"
        assert cell_key(54.4001, 48.606) == "54.40:48.60"

    def test_haversine(self) -> None:
        assert haversine_m(54.3857, 48.606, 54.3868, 48.609) == pytest.approx(230, abs=5)


class TestFetchBackoff:
    async def test_failed_cell_is_not_retried_for_ten_minutes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = 0

        async def failing(*_: float) -> list[object] | None:
            nonlocal calls
            calls += 1
            return None

        monkeypatch.setattr(service.osm, "fetch_shelters", failing)
        service._failed_at.clear()
        cell = "99.00:99.00"
        assert await service._fetch_cell(99.0, 99.0, cell) is None
        assert calls == 1
        assert service.recently_failed(cell)
        assert not service.recently_failed(cell, now=time.monotonic() + service.RETRY_AFTER_S + 1)
        service._failed_at.clear()

    async def test_success_clears_failure_mark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def ok(*_: float) -> list[object]:
            return []

        monkeypatch.setattr(service.osm, "fetch_shelters", ok)
        cell = "98.00:98.00"
        service._failed_at[cell] = time.monotonic()
        assert await service._fetch_cell(98.0, 98.0, cell) == []
        assert not service.recently_failed(cell)


OSRM_RESPONSE = {
    "code": "Ok",
    "routes": [
        {
            "distance": 229.3,
            "duration": 55.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[48.60615, 54.385585], [48.607394, 54.386138], [48.608958, 54.386833]],
            },
        }
    ],
}


class TestRouting:
    def test_parse_osrm_swaps_lon_lat(self) -> None:
        route = routing.parse_osrm(OSRM_RESPONSE)
        assert route is not None
        assert route.provider == "osrm"
        assert route.distance_m == 229 and route.duration_s == 55
        assert route.points[0] == (54.385585, 48.60615)
        assert len(route.points) == 3

    def test_parse_osrm_rejects_no_route(self) -> None:
        assert routing.parse_osrm({"code": "NoRoute", "routes": []}) is None
        assert routing.parse_osrm({"code": "Ok", "routes": [{"geometry": {"coordinates": [[1, 2]]}}]}) is None

    def test_straight_route_estimates_walk_at_5_kmh(self) -> None:
        route = routing.straight_route(54.3857, 48.606, 54.3868, 48.609)
        assert route.provider == "straight"
        assert route.distance_m == pytest.approx(230, abs=5)
        assert route.duration_s == pytest.approx(route.distance_m / (5000 / 3600), abs=1)
        assert route.points == [(54.3857, 48.606), (54.3868, 48.609)]

    async def test_walking_route_falls_back_to_straight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def broken(*_: float) -> routing.RouteOut | None:
            return None

        monkeypatch.setattr(routing, "_osrm_route", broken)
        routing._cache.clear()
        route = await routing.walking_route(54.3857, 48.606, 54.3868, 48.609)
        assert route.provider == "straight"
        assert len(route.points) == 2

    async def test_walking_route_caches_osrm_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = 0

        async def fake(*_: float) -> routing.RouteOut | None:
            nonlocal calls
            calls += 1
            return routing.parse_osrm(OSRM_RESPONSE)

        monkeypatch.setattr(routing, "_osrm_route", fake)
        routing._cache.clear()
        first = await routing.walking_route(54.3857, 48.606, 54.3868, 48.609)
        second = await routing.walking_route(54.38571, 48.60601, 54.3868, 48.609)
        assert first == second and first.provider == "osrm"
        assert calls == 1


class TestImporterCsv:
    def test_parses_semicolon_csv_with_bom_and_blank_coordinates(self) -> None:
        text = (
            "﻿name;address;lat;lon;capacity;kind\n"
            "Подвал школы № 12;Орёл, ул. Ленина, 12;52,96712;36,0638;400;basement\n"
            "Паркинг ТЦ;Орёл, Кромское шоссе, 4;;;800;parking\n"
            ";пустая строка без названия;;;;\n"
        )
        rows = parse_csv(text)
        assert [r.name for r in rows] == ["Подвал школы № 12", "Паркинг ТЦ"]
        assert rows[0].lat == pytest.approx(52.96712) and rows[0].lon == pytest.approx(36.0638)
        assert rows[0].capacity == 400 and rows[0].kind == "basement"
        assert rows[1].lat is None and rows[1].lon is None and rows[1].kind == "parking"

    def test_kind_defaults_to_shelter(self) -> None:
        rows = parse_csv("name,address\nУкрытие,Город\n")
        assert rows[0].kind == "shelter" and rows[0].capacity is None

    def test_missing_required_column(self) -> None:
        with pytest.raises(ImportError_, match="address"):
            parse_csv("name,lat,lon\nX,1,2\n")

    def test_unknown_kind_reports_line(self) -> None:
        with pytest.raises(ImportError_, match="строка 2"):
            parse_csv("name,address,kind\nX,Y,cave\n")

    def test_half_coordinates_rejected(self) -> None:
        with pytest.raises(ImportError_, match="обе координаты"):
            parse_csv("name,address,lat,lon\nX,Y,52.1,\n")
