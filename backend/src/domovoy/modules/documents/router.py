"""Документы дома (видят все жители: протоколы собраний, договор с УК, акты) и личные документы жителя.

Личный документ видит только владелец. Файл отдаётся по подписанной ссылке, которая живёт 15 минут:
её можно открыть во внешнем браузере из MAX, не передавая initData.
"""

import hashlib
import hmac
import time
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, select

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.storage import read_object, remove_object, save_document
from domovoy.modules.common_schemas import UserShort
from domovoy.modules.misc_models import Document
from domovoy.modules.users.models import User

router = APIRouter(tags=["Документы"])

Scope = Literal["house", "personal"]


class DocumentOut(BaseModel):
    id: int
    title: str
    filename: str
    content_type: str
    size: int
    scope: Scope
    author: UserShort | None
    can_delete: bool
    created_at: datetime


class LinkOut(BaseModel):
    url: str
    expires_at: int


def _sign(doc_id: int, exp: int) -> str:
    return hmac.new(get_settings().files_signing_key, f"{doc_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def doc_out(d: Document, author: User | None, user_id: int, is_admin: bool) -> DocumentOut:
    personal = d.owner_id is not None
    return DocumentOut(
        id=d.id,
        title=d.title,
        filename=d.filename,
        content_type=d.content_type,
        size=d.size,
        scope="personal" if personal else "house",
        author=UserShort.of(author) if author else None,
        can_delete=d.owner_id == user_id if personal else (is_admin or d.author_id == user_id),
        created_at=d.created_at,
    )


async def _get_visible(session: SessionDep, doc_id: int, ctx: CtxDep) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None or doc.house_id != ctx.house.id or (doc.owner_id is not None and doc.owner_id != ctx.user.id):
        raise HTTPException(404, "Документ не найден")
    return doc


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(session: SessionDep, ctx: CtxDep, scope: Scope | None = None) -> list[DocumentOut]:
    visible = or_(Document.owner_id.is_(None), Document.owner_id == ctx.user.id)
    if scope == "house":
        visible = Document.owner_id.is_(None)
    elif scope == "personal":
        visible = Document.owner_id == ctx.user.id
    rows = await session.execute(
        select(Document, User)
        .outerjoin(User, User.id == Document.author_id)
        .where(Document.house_id == ctx.house.id, visible)
        .order_by(Document.created_at.desc())
        .limit(200)
    )
    return [doc_out(d, u, ctx.user.id, ctx.is_admin) for d, u in rows.all()]


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    session: SessionDep,
    ctx: CtxDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=2, max_length=200)],
    scope: Annotated[Scope, Form()] = "personal",
) -> DocumentOut:
    if scope == "house" and not ctx.is_admin:
        raise HTTPException(403, "Документы дома загружает администратор. Личный документ можно добавить себе")
    key, content_type, size = await save_document("documents", file)
    doc = Document(
        house_id=ctx.house.id,
        owner_id=ctx.user.id if scope == "personal" else None,
        author_id=ctx.user.id,
        title=title.strip(),
        filename=(file.filename or "document")[:256],
        content_type=content_type,
        size=size,
        key=key,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc_out(doc, ctx.user, ctx.user.id, ctx.is_admin)


@router.get("/documents/{doc_id}/link", response_model=LinkOut)
async def document_link(doc_id: int, session: SessionDep, ctx: CtxDep) -> LinkOut:
    doc = await _get_visible(session, doc_id, ctx)
    exp = int(time.time()) + get_settings().files_link_ttl_seconds
    return LinkOut(url=f"/api/v1/files/{doc.id}?exp={exp}&sig={_sign(doc.id, exp)}", expires_at=exp)


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: int, session: SessionDep, ctx: CtxDep) -> Response:
    doc = await _get_visible(session, doc_id, ctx)
    if not doc_out(doc, None, ctx.user.id, ctx.is_admin).can_delete:
        raise HTTPException(403, "Удалить документ дома может администратор или тот, кто его загрузил")
    key = doc.key
    await session.delete(doc)
    await session.commit()
    await remove_object(key)
    return Response(status_code=204)


@router.get("/files/{doc_id}", include_in_schema=False)
async def download(doc_id: int, exp: int, sig: str) -> Response:
    if exp < time.time() or not hmac.compare_digest(sig, _sign(doc_id, exp)):
        raise HTTPException(403, "Ссылка устарела. Откройте документ в приложении ещё раз")
    async with get_sessionmaker()() as session:
        doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Документ не найден")
    data = await read_object(doc.key)
    return Response(
        data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(doc.filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
