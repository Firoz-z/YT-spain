"""Main pipeline — fetches today's Spanish word, builds video, uploads it."""
import os
import re
import sys
import random
from datetime import date, datetime, timezone

from word_fetcher import fetch_word_data
from video_builder import create_short, create_long
from image_fetcher import fetch_word_images
from llm import enrich_word_data
from uploader import upload_short_only, upload_long
from config import (TEMP_DIR, OUTPUT_DIR,
                    LEVEL_START_DATE, DAYS_PER_LEVEL, LEVEL_ORDER)

VIDEOS_PER_DAY = 4

WORDS_FILE = os.path.join(os.path.dirname(__file__), "words.txt")

UPLOAD_LOG = "uploads.md"
UPLOAD_LOG_HEADER = (
    "# Upload History\n\n"
    "Every published Short, in chronological order. Appended automatically\n"
    "by the pipeline after each successful upload.\n\n"
    "| Date | Slot | Word | IPA | Gender | Level | Meaning | Video |\n"
    "|------|------|------|-----|--------|-------|---------|-------|\n"
)


def _log_upload(word_data: dict, video_id: str, slot: int) -> None:
    """Append a row to uploads.md so we have a permanent history of what
    was published when. The GitHub Actions workflow commits this file
    back to the repo after the pipeline succeeds."""
    path = os.path.join(os.path.dirname(__file__), UPLOAD_LOG)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(UPLOAD_LOG_HEADER)
    today  = date.today().isoformat()
    word   = word_data.get("word", "")
    ipa    = word_data.get("ipa", "") or "—"
    gender = word_data.get("gender", "") or "—"
    # Prefer the curriculum section level (authoritative) over the
    # LLM's CEFR guess. For themed packs this shows e.g. "THEME-COCINA".
    level  = (word_data.get("section_level", "")
              or word_data.get("cefr_level", "")
              or "—")
    defn   = (word_data.get("definition", "") or "")
    # Markdown table cells can't contain raw pipes — escape them
    defn   = defn.replace("|", "\\|")
    url    = f"https://youtube.com/shorts/{video_id}"
    row = (f"| {today} | {slot} | {word} | {ipa} | {gender} | "
           f"{level} | {defn} | [link]({url}) |\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(row)
    print(f"  history → {UPLOAD_LOG}")


def _already_uploaded() -> set:
    """Return the set of headwords already published, parsed from
    uploads.md. Used to skip duplicates when two runs happen in the same
    slot window (manual workflow_dispatch + the scheduled cron, or a
    retried run, etc.)."""
    path = os.path.join(os.path.dirname(__file__), UPLOAD_LOG)
    if not os.path.exists(path):
        return set()
    used = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            # Markdown table row: "| 2026-04-29 | 2 | comer | ... |"
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue
            date_cell = parts[1]
            word_cell = parts[3]
            if not (len(date_cell) >= 4 and date_cell[:4].isdigit()):
                continue   # skip header / separator rows
            if word_cell:
                used.add(word_cell)
    return used


_LEVEL_HEADER_RE = re.compile(r"^#\s*=+\s*LEVEL\s*:\s*([\w\-]+)\s*=+", re.I)


def _load_words_by_level() -> dict:
    """Parse words.txt into a dict {level_code: [word, ...]}.

    Section headers look like:  # === LEVEL: A1 ===
    All other comment lines and blank lines are ignored. Words found
    before any section header are bucketed under "_UNCLASSIFIED" so
    the file is never silently empty.
    """
    sections: dict = {"_UNCLASSIFIED": []}
    current = "_UNCLASSIFIED"
    with open(WORDS_FILE, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = _LEVEL_HEADER_RE.match(line)
            if m:
                current = m.group(1).upper()
                sections.setdefault(current, [])
                continue
            if line.startswith("#"):
                continue
            sections[current].append(line)
    return sections


def _current_level(today: date | None = None) -> str:
    """Which CEFR level is active today, based on days since LEVEL_START_DATE."""
    today = today or date.today()
    days_in = (today - LEVEL_START_DATE).days
    idx = max(0, days_in // DAYS_PER_LEVEL)
    idx = min(idx, len(LEVEL_ORDER) - 1)
    return LEVEL_ORDER[idx]


def _active_words() -> tuple[list, str]:
    """Return (words for the currently active level, level code)."""
    sections = _load_words_by_level()
    level = _current_level()

    # Try the active level; if empty (e.g. user hasn't populated B2 yet),
    # fall back to the previous level so the pipeline never crashes.
    for lvl in reversed(LEVEL_ORDER[: LEVEL_ORDER.index(level) + 1]):
        if sections.get(lvl):
            return sections[lvl], lvl

    # Last-ditch: anything unclassified, otherwise everything we found.
    if sections.get("_UNCLASSIFIED"):
        return sections["_UNCLASSIFIED"], "?"
    flat = [w for v in sections.values() for w in v]
    return flat, "?"


def _get_word(slot: int) -> str:
    """Pick a Spanish word for this slot from the currently active level.

    The base position is deterministic from date + slot, but we then
    walk forward in the shuffled list past any word that's already
    appeared in uploads.md. That guarantees no repeat even when a
    manual run collides with the cron, or when VIDEOS_PER_DAY shifts
    the position formula mid-cycle.
    """
    words, level = _active_words()
    print(f"  level      : {level} ({len(words)} words in pool)")

    used = _already_uploaded()

    days        = (date.today() - date(2024, 1, 1)).days
    global_slot = days * VIDEOS_PER_DAY + slot
    cycle       = global_slot // len(words)
    position    = global_slot % len(words)

    # Walk through the shuffled list, advancing across cycle boundaries
    # if needed, until we find a word that hasn't been uploaded yet.
    for offset in range(len(words) * 4):
        c = cycle + (position + offset) // len(words)
        i = (position + offset) % len(words)
        rng = random.Random(f"{level}:{c}")   # level-scoped seed
        shuffled = words[:]
        rng.shuffle(shuffled)
        candidate = shuffled[i]
        if candidate not in used:
            return candidate

    # Astronomically unlikely — would mean every word in this tier was
    # already used across 4 full cycles. Fall back to the deterministic
    # pick (a controlled repeat).
    rng = random.Random(f"{level}:{cycle}")
    shuffled = words[:]
    rng.shuffle(shuffled)
    return shuffled[position]


def run(slot: int = 0) -> None:
    os.makedirs(TEMP_DIR,   exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    word = _get_word(slot)
    level = _current_level()
    print(f"\n[slot {slot}] word: {word}  (level: {level})")

    # 1 — fetch from Wiktionary (validates word, captures IPA + POS)
    word_data = fetch_word_data(word)
    if not word_data:
        print(f"  skipping — no data for '{word}'")
        return

    # 2 — enrich with Groq (definition, gender, example, memory tip, CEFR)
    word_data = enrich_word_data(word, word_data)
    # Stamp the section level onto the data so the uploader can file
    # the video into the right playlist and the history log reflects it.
    word_data["section_level"] = level

    if not word_data.get("definition"):
        print(f"  skipping — LLM enrichment produced no definition")
        return

    print(f"  word        : {word_data['word']}")
    print(f"  ipa         : {word_data.get('ipa', '')}")
    print(f"  gender      : {word_data.get('gender', '')}")
    print(f"  cefr        : {word_data.get('cefr_level', '')}")
    print(f"  definition  : {word_data['definition']}")

    # 3 — background images via Pexels (English keywords from definition)
    word_images = fetch_word_images(word_data, count=5)
    print(f"  images      : {len(word_images)} fetched")

    today = date.today().isoformat()

    # 4a — build Short (9:16 vertical)
    safe_name  = word_data["word"].replace(" ", "_") or "word"
    short_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{today}_s{slot}_short.mp4")
    create_short(word_data, short_path, word_images=word_images)

    # 4b — Long companion video disabled (re-enable when ready)
    # long_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{today}_s{slot}_long.mp4")
    # create_long(word_data, long_path, word_images=word_images)

    # 5a — upload Short + file into the level's playlist
    short_id = upload_short_only(short_path, word_data, level=level)
    print(f"  short  → https://youtube.com/shorts/{short_id}")

    # 5b — Long upload disabled (re-enable when ready)
    # long_id = upload_long(long_path, word_data, level=level)
    # print(f"  long   → https://youtube.com/watch?v={long_id}")

    # 6 — append to upload history (committed back by the workflow)
    _log_upload(word_data, short_id, slot)


def _slot_from_hour() -> int:
    """Map current UTC hour to a slot (0-3) matching the cron schedule.

    Cron fires at 13:00, 18:00, 23:00, 02:00 UTC — tuned for Mexico/US
    audience peaks (Mexico morning commute, lunch, US East evening, US
    late-evening prime). Each window covers up to the next cron so a
    workflow that runs slightly late still picks the right slot.
    """
    hour = datetime.now(timezone.utc).hour
    if   13 <= hour < 18:        return 0   # 1 PM UTC run
    elif 18 <= hour < 23:        return 1   # 6 PM UTC run
    elif hour >= 23 or hour < 2: return 2   # 11 PM UTC run
    else:                        return 3   # 2 AM UTC run


if __name__ == "__main__":
    slot = int(sys.argv[1]) if len(sys.argv) > 1 else _slot_from_hour()
    run(slot)
