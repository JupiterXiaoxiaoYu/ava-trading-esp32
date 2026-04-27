from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from ava_devicekit.providers.asr.base import ASRProvider
from ava_devicekit.providers.asr.openai_compatible import OpenAICompatibleASRConfig, OpenAICompatibleASRProvider
from ava_devicekit.providers.asr.qwen_realtime import QwenRealtimeASRConfig, QwenRealtimeASRProvider
from ava_devicekit.providers.llm.base import LLMProvider
from ava_devicekit.providers.llm.openai_compatible import OpenAICompatibleLLMConfig, OpenAICompatibleLLMProvider
from ava_devicekit.providers.pipeline import VoicePipeline
from ava_devicekit.providers.tts.base import TTSProvider
from ava_devicekit.providers.tts.alibl_stream import AliBLTTSConfig, AliBLTTSProvider
from ava_devicekit.providers.tts.mock import MockTTSProvider
from ava_devicekit.providers.tts.openai_compatible import OpenAICompatibleTTSConfig, OpenAICompatibleTTSProvider
from ava_devicekit.runtime.settings import RuntimeSettings


@dataclass(slots=True)
class ProviderBundle:
    asr: ASRProvider | None
    llm: LLMProvider | None
    tts: TTSProvider
    pipeline: VoicePipeline


def create_provider_bundle(settings: RuntimeSettings | None = None) -> ProviderBundle:
    settings = settings or RuntimeSettings.load()
    asr = create_asr_provider(settings)
    llm = create_llm_provider(settings)
    tts = create_tts_provider(settings)
    return ProviderBundle(asr=asr, llm=llm, tts=tts, pipeline=VoicePipeline(llm=llm, tts=tts))


def create_voice_pipeline(settings: RuntimeSettings | None = None) -> VoicePipeline:
    return create_provider_bundle(settings).pipeline


def create_asr_provider(settings: RuntimeSettings) -> ASRProvider | None:
    name = settings.asr_provider.lower()
    if name in {"", "none", "disabled"}:
        return None
    if name in {"custom", "class", "python"} or settings.asr_class:
        return _load_custom_provider(settings.asr_class, settings.asr_options)
    if name in {"qwen", "qwen_realtime", "qwen3-asr-flash-realtime"}:
        return QwenRealtimeASRProvider(
            QwenRealtimeASRConfig(
                api_key_env=settings.asr_api_key_env,
                model=settings.asr_model,
                base_url=settings.asr_base_url,
                language=settings.asr_language,
                sample_rate=settings.asr_sample_rate,
                **_known_options(settings.asr_options, QwenRealtimeASRConfig),
            )
        )
    if name in {"openai", "openai-compatible", "whisper", "transcription"}:
        return OpenAICompatibleASRProvider(
            OpenAICompatibleASRConfig(
                base_url=settings.asr_base_url,
                api_key_env=settings.asr_api_key_env,
                model=settings.asr_model,
                language=settings.asr_language,
                timeout_sec=int(settings.asr_options.get("timeout_sec") or 30),
                response_format=str(settings.asr_options.get("response_format") or "json"),
            )
        )
    raise ValueError(f"unsupported ASR provider: {settings.asr_provider}")


def create_llm_provider(settings: RuntimeSettings) -> LLMProvider | None:
    name = settings.llm_provider.lower()
    if name in {"", "none", "disabled"}:
        return None
    if name in {"custom", "class", "python"} or settings.llm_class:
        return _load_custom_provider(settings.llm_class, settings.llm_options)
    if name in {"openai", "openai-compatible", "compatible"}:
        return OpenAICompatibleLLMProvider(
            OpenAICompatibleLLMConfig(
                base_url=settings.llm_base_url,
                api_key_env=settings.llm_api_key_env,
                model=settings.llm_model,
                timeout_sec=settings.llm_timeout_sec,
                **_known_options(settings.llm_options, OpenAICompatibleLLMConfig, exclude={"base_url", "api_key_env", "model", "timeout_sec"}),
            )
        )
    raise ValueError(f"unsupported LLM provider: {settings.llm_provider}")


def create_tts_provider(settings: RuntimeSettings) -> TTSProvider:
    name = settings.tts_provider.lower()
    if name in {"", "mock", "none", "disabled"}:
        return MockTTSProvider()
    if name in {"custom", "class", "python"} or settings.tts_class:
        return _load_custom_provider(settings.tts_class, settings.tts_options)
    if name in {"alibl", "alibl-tts", "alibl_stream", "aliyun-bailian", "cosyvoice"}:
        return AliBLTTSProvider(
            AliBLTTSConfig(
                api_key_env=settings.tts_api_key_env,
                ws_url=settings.tts_base_url,
                model=settings.tts_model,
                voice=settings.tts_voice,
                response_format=settings.tts_format,
                timeout_sec=settings.tts_timeout_sec,
                **_known_options(settings.tts_options, AliBLTTSConfig, exclude={"api_key_env", "ws_url", "model", "voice", "response_format", "timeout_sec"}),
            )
        )
    if name in {"openai", "openai-compatible", "compatible"}:
        return OpenAICompatibleTTSProvider(
            OpenAICompatibleTTSConfig(
                base_url=settings.tts_base_url,
                api_key_env=settings.tts_api_key_env,
                model=settings.tts_model,
                voice=settings.tts_voice,
                response_format=settings.tts_format,
                timeout_sec=settings.tts_timeout_sec,
                **_known_options(settings.tts_options, OpenAICompatibleTTSConfig, exclude={"base_url", "api_key_env", "model", "voice", "response_format", "timeout_sec"}),
            )
        )
    raise ValueError(f"unsupported TTS provider: {settings.tts_provider}")


def _load_custom_provider(class_path: str, options: dict[str, Any] | None = None):
    if not class_path:
        raise ValueError("custom provider requires `class` or `class_path`")
    module_name, sep, attr = class_path.replace(":", ".").rpartition(".")
    if not sep or not module_name or not attr:
        raise ValueError(f"invalid provider class path: {class_path}")
    cls = getattr(importlib.import_module(module_name), attr)
    options = options or {}
    try:
        return cls(**options)
    except TypeError:
        return cls(options)


def _known_options(options: dict[str, Any] | None, config_cls: type, *, exclude: set[str] | None = None) -> dict[str, Any]:
    if not options:
        return {}
    allowed = set(getattr(config_cls, "__dataclass_fields__", {}).keys())
    allowed -= exclude or set()
    return {k: v for k, v in options.items() if k in allowed}
