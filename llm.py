"""
llm.py — Groq LLM calls for Spanish definition, example sentence,
memory tip, gender (for nouns), and CEFR level.

The Spanish pipeline relies on the LLM more heavily than the JP one
because Wiktionary doesn't expose structured grammatical data the way
Jisho does for Japanese. Groq fills in everything except IPA.
"""
import os
import json
from groq import Groq

_MODEL = "llama-3.3-70b-versatile"

_PROMPT = """You are a Spanish vocabulary assistant for a YouTube channel teaching Mexican Spanish to English speakers.

Given the Spanish word "{word}" (part of speech hint: "{pos}"),
return a JSON object with EXACTLY these fields:

{{
  "definition": "Clean, one-line English definition. Pick the most common modern Mexican usage. Max 12 words.",
  "gender": "For nouns only: 'el' (masculine) or 'la' (feminine). For non-nouns return an empty string.",
  "part_of_speech": "noun, verb, adjective, adverb, etc. (in English).",
  "example_es": "ONE natural Mexican Spanish example sentence using the word. Use simple grammar suitable for beginners. Include the word naturally.",
  "example_en": "Natural English translation of the example sentence.",
  "memory_tip": "ONE creative tip in English to help remember this word — use sound associations, mnemonics, or imagery. Start with 'Think of' or 'Remember'. Max 22 words.",
  "synonyms": ["sp_synonym1", "sp_synonym2", "sp_synonym3"],
  "cefr_level": "A1, A2, B1, B2, C1, or C2 — your best estimate of this word's level."
}}

Rules:
- Return ONLY the JSON object. No explanation, no markdown.
- Example sentence must be beginner-friendly and natural Mexican Spanish.
- Memory tip must be in English (audience is English speakers learning Spanish).
- Synonyms must be Spanish words (with article for nouns, e.g. "la película").
- For verbs, give the infinitive form; for nouns include gender.

Word: {word}"""


def enrich_word_data(word: str, fallback: dict) -> dict:
    """
    Call Groq for definition, example sentence (ES+EN), memory tip,
    gender, CEFR level. Falls back to whatever word_fetcher.py
    produced if Groq is unavailable.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("  [llm] GROQ_API_KEY not set — pipeline cannot run without it for Spanish")
        return fallback

    try:
        client   = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model    = _MODEL,
            messages = [{"role": "user", "content": _PROMPT.format(
                word = fallback["word"],
                pos  = fallback.get("part_of_speech", ""),
            )}],
            temperature      = 0.7,
            max_tokens       = 500,
            response_format  = {"type": "json_object"},
        )
        raw  = response.choices[0].message.content.strip()
        data = json.loads(raw)

        for field in ("definition", "example_es", "example_en", "memory_tip"):
            if not data.get(field):
                raise ValueError(f"missing field: {field}")

        print(f"  [llm] definition  : {data['definition']}")
        print(f"  [llm] gender      : {data.get('gender', '')}")
        print(f"  [llm] cefr_level  : {data.get('cefr_level', '')}")
        print(f"  [llm] example_es  : {data['example_es']}")
        print(f"  [llm] example_en  : {data['example_en']}")
        print(f"  [llm] memory_tip  : {data['memory_tip']}")

        return {
            **fallback,
            "definition":     data["definition"],
            "gender":         data.get("gender", ""),
            "part_of_speech": data.get("part_of_speech", fallback.get("part_of_speech", "")),
            "example_es":     data["example_es"],
            "example_en":     data["example_en"],
            "memory_tip":     data["memory_tip"],
            "synonyms":       data.get("synonyms", fallback.get("synonyms", []))[:5],
            "cefr_level":     data.get("cefr_level", ""),
        }

    except Exception as e:
        print(f"  [llm] error ({e}) — falling back to stub data")
        return fallback
