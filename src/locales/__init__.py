"""
Internationalization (i18n) module for multi-language support.

Usage:
    from locales import t, set_language

    set_language('en_US')  # or 'zh_CN'
    logger.info(t('log.device_connected', device_id='xxx'))
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

# Default language
_current_language = 'en_US'

# Cache for loaded language files
_translations: Dict[str, Dict[str, str]] = {}

# Locales directory path
_locales_dir = Path(__file__).parent


def _load_language(lang: str) -> Dict[str, str]:
    """
    Load language file from JSON.

    Args:
        lang: Language code (e.g., 'en_US', 'zh_CN')

    Returns:
        Dictionary of translations
    """
    if lang in _translations:
        return _translations[lang]

    lang_file = _locales_dir / f"{lang}.json"
    if not lang_file.exists():
        # Fallback to English if language file not found
        lang_file = _locales_dir / "en_US.json"
        if not lang_file.exists():
            return {}

    try:
        with open(lang_file, 'r', encoding='utf-8') as f:
            _translations[lang] = json.load(f)
        return _translations[lang]
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load language file {lang_file}: {e}")
        return {}


def set_language(lang: str) -> None:
    """
    Set the current language.

    Args:
        lang: Language code (e.g., 'en_US', 'zh_CN')
    """
    global _current_language
    _current_language = lang
    # Preload the language file
    _load_language(lang)


def get_language() -> str:
    """
    Get the current language code.

    Returns:
        Current language code
    """
    return _current_language


def t(key: str, **kwargs: Any) -> str:
    """
    Translate a key to the current language.

    Args:
        key: Translation key (e.g., 'log.device_connected')
        **kwargs: Placeholder values (e.g., device_id='xxx')

    Returns:
        Translated string with placeholders replaced

    Example:
        t('log.device_connected', device_id='abc123')
        # Returns: "Device connected: abc123" (en_US)
        # Returns: "设备已连接: abc123" (zh_CN)
    """
    translations = _load_language(_current_language)

    # Get translation or return key as fallback
    text = translations.get(key)

    if text is None:
        # Try fallback to English
        if _current_language != 'en_US':
            en_translations = _load_language('en_US')
            text = en_translations.get(key)

        # If still not found, return the key itself
        if text is None:
            return key

    # Replace placeholders
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            # If placeholder replacement fails, return text as-is
            pass

    return text


def get_available_languages() -> list:
    """
    Get list of available language codes.

    Returns:
        List of language codes
    """
    languages = []
    for f in _locales_dir.glob("*.json"):
        languages.append(f.stem)
    return sorted(languages)


# Auto-detect language from environment variable
def _init_language():
    """Initialize language from environment variable."""
    env_lang = os.environ.get('LANG', '')
    if 'zh' in env_lang.lower():
        set_language('zh_CN')
    else:
        set_language('en_US')


# Initialize on module load
_init_language()
