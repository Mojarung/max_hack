"""Гибридный поиск (RAG-ретривер): вектор pgvector + полнотекстовый индекс Postgres."""

from typing import Any

from sqlalchemy import Select, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core.embeddings import embed

VECTOR_WEIGHT = 0.6
TEXT_WEIGHT = 0.4
MIN_SCORE = 0.22


async def hybrid_search[M](
    session: AsyncSession,
    model: type[M],
    query: str,
    *,
    where: list[Any],
    limit: int = 10,
    min_score: float = MIN_SCORE,
) -> list[tuple[M, float]]:
    vector = embed(query)
    column: Any = model
    tsq = func.websearch_to_tsquery("russian", query)
    vec_sim = literal(1.0) - column.embedding.cosine_distance(vector)
    text_rank = func.least(func.ts_rank_cd(column.search, tsq) * 2, 1.0)
    score = (vec_sim * VECTOR_WEIGHT + text_rank * TEXT_WEIGHT).label("score")
    stmt: Select[tuple[M, float]] = (
        select(model, score).where(*where, column.embedding.is_not(None)).order_by(score.desc()).limit(limit)
    )
    rows = (await session.execute(stmt)).unique().all()
    return [(row[0], round(float(row[1]), 3)) for row in rows if float(row[1]) >= min_score]
