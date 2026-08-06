"""Pure visitor-message localization contract.

Only public text enters this module. Tour state, profile fields, evidence,
source identifiers and tool payloads are deliberately outside its interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable


TranslateFn = Callable[[str, str], str]
_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

LANGUAGE_NAMES = {
    "zh": "简体中文",
    "en": "English",
    "ko": "한국어",
    "ja": "日本語",
    "yue": "粤语（书面粤语）",
    "fr": "français",
    "de": "Deutsch",
    "es": "español",
    "th": "ภาษาไทย",
    "ru": "русский язык",
    "ar": "العربية",
    "it": "italiano",
    "pt": "português",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
    "ms": "Bahasa Melayu",
    "hi": "हिन्दी",
}


@dataclass(frozen=True)
class VisitorLocalizationResult:
    public_text: str
    target_language: str
    status: str
    api_called: bool


def target_language_name(language: str | None) -> str:
    if language is None:
        return "English"
    normalized = str(language).strip()
    return LANGUAGE_NAMES.get(normalized.casefold(), normalized)


def _valid_translation(source: str, translated: str) -> bool:
    value = str(translated or "").strip()
    if not value:
        return False
    # Translation may reorder prose, but explicit Arabic numerals must remain.
    return set(_NUMBER.findall(source)).issubset(_NUMBER.findall(value))


def localize_visitor_text(
    text: str,
    language: str | None,
    translate: TranslateFn,
    *,
    already_bilingual: bool = False,
) -> VisitorLocalizationResult:
    """Return one localized public message without mutating any guide state."""
    source = str(text or "").strip()
    if not source:
        return VisitorLocalizationResult(source, target_language_name(language), "empty", False)

    if language is None:
        if already_bilingual:
            return VisitorLocalizationResult(source, "zh+en", "already_bilingual", False)
        source_is_chinese = bool(_CJK.search(source))
        target = "English" if source_is_chinese else "简体中文"
        try:
            translated = str(translate(source, target) or "").strip()
        except Exception:
            translated = ""
        if not _valid_translation(source, translated):
            fallback = (
                f"{source}\n\nEnglish translation is temporarily unavailable."
                if source_is_chinese
                else f"中文翻译暂时不可用。\n\n{source}"
            )
            return VisitorLocalizationResult(fallback, "zh+en", "translation_unavailable", True)
        bilingual = (
            f"{source}\n\n{translated}"
            if source_is_chinese
            else f"{translated}\n\n{source}"
        )
        return VisitorLocalizationResult(bilingual, "zh+en", "translated", True)

    normalized = str(language).strip().casefold()
    target = target_language_name(language)
    if normalized == "zh" and _CJK.search(source):
        return VisitorLocalizationResult(source, target, "source_already_target", False)
    if normalized == "en" and not _CJK.search(source) and _LATIN.search(source):
        return VisitorLocalizationResult(source, target, "source_already_target", False)
    try:
        translated = str(translate(source, target) or "").strip()
    except Exception:
        translated = ""
    if not _valid_translation(source, translated):
        return VisitorLocalizationResult(source, target, "translation_unavailable", True)
    return VisitorLocalizationResult(translated, target, "translated", True)
