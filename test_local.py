"""
Local test runner — generates a video for a single word WITHOUT uploading.

Usage:
  python test_local.py             # uses default test word
  python test_local.py querer       # specific word
  python test_local.py película     # any word from words.txt or your own

Prerequisites:
  - ffmpeg installed (brew install ffmpeg on macOS)
  - pip install -r requirements.txt
  - GROQ_API_KEY env var (required — Groq fills in definition / example / tip)
  - Optional: PEXELS_API_KEY env var for background images

The output MP4 is saved to ./output/ — open it to preview.
"""
import os
import sys
from datetime import date

from word_fetcher import fetch_word_data
from video_builder import create_short
from image_fetcher import fetch_word_images
from llm import enrich_word_data
from config import TEMP_DIR, OUTPUT_DIR


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "comer"

    os.makedirs(TEMP_DIR,   exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n=== Testing pipeline for: {word} ===\n")

    print("[1/4] Fetching from Wiktionary...")
    word_data = fetch_word_data(word)
    if not word_data:
        print(f"  ERROR: no data for '{word}'")
        return 1
    print(f"  word        : {word_data['word']}")
    print(f"  ipa         : {word_data.get('ipa', '')}")
    print(f"  pos (hint)  : {word_data.get('part_of_speech', '')}")

    print("\n[2/4] Enriching via Groq LLM (requires GROQ_API_KEY)...")
    word_data = enrich_word_data(word, word_data)
    if not word_data.get("definition"):
        print("  ERROR: LLM enrichment produced no definition — set GROQ_API_KEY")
        return 1

    print("\n[3/4] Fetching background images from Pexels...")
    word_images = fetch_word_images(word_data, count=5)
    print(f"  images     : {len(word_images)} fetched")

    print("\n[4/4] Building video (TTS + frames + ffmpeg)...")
    today = date.today().isoformat()
    safe_name = word_data["word"].replace(" ", "_") or "test"
    output_path = os.path.join(OUTPUT_DIR, f"TEST_{safe_name}_{today}.mp4")
    create_short(word_data, output_path, word_images=word_images)

    print(f"\n=== DONE ===")
    print(f"Video: {output_path}")
    print(f"Open with: open '{output_path}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
