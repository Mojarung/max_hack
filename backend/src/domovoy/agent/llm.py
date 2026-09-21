"""Фабрика LLM. Провайдер переключается переменной LLM_PROVIDER.

- `ollama_cloud`: Ollama Cloud (https://ollama.com), бесплатный тариф, нужен OLLAMA_API_KEY;
- `ollama_local`: локальная Ollama (OLLAMA_LOCAL_URL), пока без модели в compose, подключается вручную;
- `stub`: детерминированная модель без сети (мок-режим и проверка без ключей).

При ошибке облачной модели агент автоматически падает на stub (ModelFallbackMiddleware).
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from domovoy.agent.stub import StubChatModel
from domovoy.core.config import get_settings


@lru_cache
def get_llm() -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "ollama_cloud" and s.ollama_api_key.get_secret_value():
        return ChatOllama(
            model=s.llm_model,
            base_url=s.ollama_cloud_url,
            temperature=s.llm_temperature,
            client_kwargs={
                "headers": {"Authorization": f"Bearer {s.ollama_api_key.get_secret_value()}"},
                "timeout": s.llm_timeout_seconds,
            },
        )
    if s.llm_provider == "ollama_local":
        return ChatOllama(
            model=s.llm_model,
            base_url=s.ollama_local_url,
            temperature=s.llm_temperature,
            client_kwargs={"timeout": s.llm_timeout_seconds},
        )
    return StubChatModel()


def get_stub() -> BaseChatModel:
    return StubChatModel()


def is_real_llm() -> bool:
    return not isinstance(get_llm(), StubChatModel)
