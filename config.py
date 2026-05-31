import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Curriculum progression
# ---------------------------------------------------------------------------
# The pipeline auto-advances one CEFR level every DAYS_PER_LEVEL days,
# starting from LEVEL_START_DATE. Once the final level is reached the
# curriculum stays there (no further escalation). Words in words.txt are
# grouped into sections like "# === LEVEL: A1 ===" — pipeline.py reads
# the active section and shuffles within it.
LEVEL_START_DATE  = date(2026, 5, 12)
DAYS_PER_LEVEL    = 50
LEVEL_ORDER       = [
    # CEFR ladder — beginner → mastery
    "A1", "A2", "B1", "B2", "C1", "C2",
    # Themed packs (keep going forever beyond CEFR mastery)
    "THEME-COCINA",       # food, cooking, ingredients, dishes
    "THEME-VIAJES",       # travel, transport, accommodation, sightseeing
    "THEME-NEGOCIOS",     # business, finance, entrepreneurship
    "THEME-TECNOLOGIA",   # tech, internet, social media, AI
    "THEME-CULTURA",      # Mexican / Latin culture, festivities, folklore
]

# Short (9:16 vertical)
WIDTH  = 1080
HEIGHT = 1920
FPS    = 30

# Long video (16:9 horizontal)
LONG_WIDTH  = 1920
LONG_HEIGHT = 1080

# Color palette (dark theme — warm Latin tones inspired by terracotta/sunset)
# Default gradient used by every scene EXCEPT the hook.
BG_TOP     = (20, 12, 28)
BG_BOTTOM  = (45, 22, 30)

# Hook frame uses a punchier, warmer gradient so the opening frame
# stands out before the cooler middle scenes take over. Currently a
# "honey & mustard" yellow palette — dark amber up top fading to a
# saturated golden mustard, dark enough that white text reads cleanly.
HOOK_BG_TOP    = (50, 38, 15)         # deep dark amber
HOOK_BG_BOTTOM = (175, 130, 35)       # warm golden mustard

WORD_COLOR        = (255, 255, 255)
IPA_COLOR         = (255, 180, 90)    # warm amber for phonetic transcription
GENDER_COLOR      = (255, 210, 130)   # gold for el/la articles
DEFINITION_COLOR  = (220, 220, 220)
EXAMPLE_COLOR     = (210, 190, 170)
BRAND_COLOR       = (200, 110, 70)    # warm orange — for dark middle scenes
HOOK_BRAND_COLOR  = (60, 25, 10)      # deep espresso-rust — for the gold hook

# Short scene durations (seconds)
SCENE1_DUR = 2.0
SCENE2_DUR = 2.5
SCENE3_DUR = 6.5
SCENE4_DUR = 3.0

# Long video scene durations (seconds)
LONG_SCENE1_DUR =  3.0
LONG_SCENE2_DUR =  4.0
LONG_SCENE3_DUR = 10.0
LONG_SCENE4_DUR = 10.0

# Paths
TEMP_DIR   = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Font search order — Spanish uses Latin-1 + IPA, so any decent
# Unicode font works. Noto Sans on Linux (CI) and Helvetica on macOS.
FONT_PATHS = {
    "bold": [
        # Linux (GitHub Actions)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf",
        # macOS (local testing)
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
    "italic": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    ],
}

# YouTube metadata
YT_TAGS = [
    "spanish", "learn spanish", "spanish vocabulary", "español",
    "spanish lesson", "spanish word of the day", "cefr",
    "spanish pronunciation", "spanish language", "shorts",
    "mexican spanish", "aprende español",
]
YT_CATEGORY_ID = "27"   # Education
YT_CHANNEL_NAME = "@EverydaySpanish"

# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------
# Each level gets its own YouTube playlist. The uploader creates the
# playlist on first upload for that level and caches the playlist ID in
# playlists.json (committed back by the workflow so we never duplicate).
# Display names appear on the channel page and in playlist URLs.
PLAYLIST_NAMES = {
    "A1":               "Spanish Level 1 · A1 — Beginner Basics",
    "A2":               "Spanish Level 2 · A2 — Elementary Conversation",
    "B1":               "Spanish Level 3 · B1 — Intermediate",
    "B2":               "Spanish Level 4 · B2 — Upper-Intermediate",
    "C1":               "Spanish Level 5 · C1 — Advanced",
    "C2":               "Spanish Level 6 · C2 — Mastery",
    "THEME-COCINA":     "Spanish Theme · Cocina y Comida",
    "THEME-VIAJES":     "Spanish Theme · Viajes y Lugares",
    "THEME-NEGOCIOS":   "Spanish Theme · Negocios y Trabajo",
    "THEME-TECNOLOGIA": "Spanish Theme · Tecnología e Internet",
    "THEME-CULTURA":    "Spanish Theme · Cultura Mexicana",
}

PLAYLIST_DESCRIPTIONS = {
    "A1": "Every Spanish-Word-of-the-Day Short for absolute beginners. "
          "Greetings, family, body, numbers, colors, days, basic verbs, food, home.",
    "A2": "Elementary conversational Spanish — school, work, weather, "
          "clothing, transport, feelings, hobbies.",
    "B1": "Intermediate Spanish — broader topics, abstract ideas, opinions, planning.",
    "B2": "Upper-intermediate Spanish — abstract reasoning, society, current affairs.",
    "C1": "Advanced Spanish — nuanced, literary, professional, idiomatic vocabulary.",
    "C2": "Mastery-level Spanish — rare, formal, literary, technical, archaic words.",
    "THEME-COCINA":     "Spanish vocabulary for cooking — ingredients, techniques, classic dishes.",
    "THEME-VIAJES":     "Spanish vocabulary for travel — transport, accommodation, sightseeing.",
    "THEME-NEGOCIOS":   "Spanish vocabulary for business — corporate, finance, entrepreneurship.",
    "THEME-TECNOLOGIA": "Spanish vocabulary for tech — devices, software, internet, social media.",
    "THEME-CULTURA":    "Spanish vocabulary about Mexican culture — festivities, folklore, art, food.",
}
