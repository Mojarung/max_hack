"""Виды укрытий и подписи источников словами жителя.

kind: shelter (защитное сооружение ГО из реестра), basement (подвал), parking (подземный паркинг),
underpass (подземный переход), metro (вход в метро), bunker (бункер).
source: "demo" (точки сида), "osm" (заглублённые объекты из OpenStreetMap), "registry:<имя реестра>".
"""

KIND_TITLES = {
    "shelter": "Защитное сооружение",
    "basement": "Подвал",
    "parking": "Подземный паркинг",
    "underpass": "Подземный переход",
    "metro": "Вход в метро",
    "bunker": "Бункер",
}

REGISTRY_PREFIX = "registry:"


def kind_title(kind: str) -> str:
    return KIND_TITLES.get(kind, "Укрытие")


def registry_source(name: str) -> str:
    """Код источника реестра: «Реестр укрытий Орловской области» → «registry:Реестр укрытий Орловской области»."""
    name = name.strip()
    return name if name.startswith(REGISTRY_PREFIX) else f"{REGISTRY_PREFIX}{name}"


def source_title(source: str) -> str:
    if source.startswith(REGISTRY_PREFIX):
        return source.removeprefix(REGISTRY_PREFIX).strip() or "Реестр укрытий"
    if source == "osm":
        return "OpenStreetMap"
    return "Демо-точка"


def source_note(source: str, official: bool) -> str:
    """Короткая пометка для текста в чате: «из реестра», «по данным OpenStreetMap», «демо-точка»."""
    if official or source.startswith(REGISTRY_PREFIX):
        return "из реестра"
    if source == "osm":
        return "по данным OpenStreetMap"
    return "демо-точка"
