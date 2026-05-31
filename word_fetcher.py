"""Fetch Spanish word data.

The Spanish version is simpler than the JP version because we don't
need a kanji→kana→romaji conversion. We use a lightweight Wiktionary
lookup to confirm the word exists and grab IPA when available; the
LLM enrichment step (llm.py) fills in the meaning, gender, example,
synonyms and CEFR level.
"""
import re
import requests

_WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"


def _fetch_wikitext(word: str) -> str | None:
    """Pull raw wikitext for the Spanish entry on en.wiktionary.org.
    Returns None on miss or network error."""
    try:
        resp = requests.get(
            _WIKTIONARY_API,
            params={
                "action":      "parse",
                "page":        word,
                "prop":        "wikitext",
                "format":      "json",
                "redirects":   "1",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("parse", {}).get("wikitext", {}).get("*")
    except Exception as e:
        print(f"  [word_fetcher] error: {e}")
        return None


def _extract_ipa(wikitext: str) -> str:
    """Pull an IPA transcription from a Spanish Wiktionary section."""
    if not wikitext:
        return ""
    # Find the Spanish section first; fall back to the whole page if absent.
    sp = re.search(r"==\s*Spanish\s*==(.*?)(?:^==[^=]|\Z)",
                   wikitext, re.S | re.M)
    chunk = sp.group(1) if sp else wikitext
    # {{IPA|es|/...e.../}} or {{IPA|es|[...]}}
    m = re.search(r"\{\{\s*IPA\s*\|\s*es\s*\|([^|}]+)", chunk)
    if not m:
        return ""
    raw = m.group(1).strip().strip("/[]")
    return f"/{raw}/"


def _extract_part_of_speech(wikitext: str) -> str:
    """Best-effort POS pull from the Spanish section headings."""
    if not wikitext:
        return ""
    sp = re.search(r"==\s*Spanish\s*==(.*?)(?:^==[^=]|\Z)",
                   wikitext, re.S | re.M)
    chunk = sp.group(1) if sp else wikitext
    for pos in ("Noun", "Verb", "Adjective", "Adverb",
                "Pronoun", "Preposition", "Conjunction", "Interjection"):
        if re.search(rf"^===\s*{pos}\s*===", chunk, re.M):
            return pos.lower()
    return ""


def fetch_word_data(word: str) -> dict | None:
    """Return a stub dict for the LLM enrichment step.

    Confirms the word exists in Wiktionary, captures IPA + POS when
    available, and lets llm.py fill in the rest. If Wiktionary is
    unreachable we still return a stub so the pipeline can run on
    Groq alone.
    """
    word = word.strip()
    if not word:
        return None

    wikitext = _fetch_wikitext(word)
    ipa = _extract_ipa(wikitext) if wikitext else ""
    pos = _extract_part_of_speech(wikitext) if wikitext else ""

    return {
        "word":           word,
        "ipa":            ipa,
        "gender":         "",          # filled in by llm.py for nouns
        "part_of_speech": pos,
        "definition":     "",          # filled in by llm.py
        "example_es":     "",
        "example_en":     "",
        "synonyms":       [],
        "cefr_level":     "",
        "audio_url":      None,
    }


def download_audio(url: str, dest: str) -> bool:
    """Stub — Spanish pronunciation comes from edge-tts, not Wiktionary."""
    return False
