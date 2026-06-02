"""YouTube uploader — uploads the Short and files it into the right
playlist for its CEFR/theme level.

Playlist IDs are cached in playlists.json (committed back by the
workflow), so we never duplicate a playlist on subsequent runs.

OAuth scope note: this module needs the broader `youtube` scope (not
just `youtube.upload`) so it can call playlists.insert and
playlistItems.insert. Re-run setup_oauth.py if you previously generated
a token with the old upload-only scope.
"""
import json
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from config import (YT_TAGS, YT_CATEGORY_ID,
                    PLAYLIST_NAMES, PLAYLIST_DESCRIPTIONS)

# Read-write scope so we can also manage playlists, not just upload.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

PLAYLIST_CACHE = os.path.join(os.path.dirname(__file__), "playlists.json")


def _get_client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


# ---------- playlist management ----------

def _load_playlist_cache() -> dict:
    if not os.path.exists(PLAYLIST_CACHE):
        return {}
    try:
        with open(PLAYLIST_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_playlist_cache(cache: dict) -> None:
    with open(PLAYLIST_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False, sort_keys=True)


def _find_existing_playlist(yt, name: str) -> str | None:
    """Page through this channel's playlists looking for `name`. Used
    to avoid creating duplicates when playlists.json is missing/stale."""
    page = None
    while True:
        req = yt.playlists().list(part="snippet", mine=True,
                                   maxResults=50, pageToken=page)
        resp = req.execute()
        for item in resp.get("items", []):
            if item["snippet"]["title"] == name:
                return item["id"]
        page = resp.get("nextPageToken")
        if not page:
            return None


def _get_or_create_playlist(yt, level: str) -> str:
    """Return playlist ID for `level`, creating it on the channel if
    needed. Caches the result in playlists.json."""
    cache = _load_playlist_cache()
    if level in cache:
        return cache[level]

    name        = PLAYLIST_NAMES.get(level, f"Spanish · {level}")
    description = PLAYLIST_DESCRIPTIONS.get(level, "")

    # Don't create duplicates if the cache was lost — check the channel first.
    existing = _find_existing_playlist(yt, name)
    if existing:
        cache[level] = existing
        _save_playlist_cache(cache)
        print(f"  [playlist] linked existing {name!r} -> {existing}")
        return existing

    resp = yt.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title":           name,
                "description":     description,
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        },
    ).execute()
    playlist_id = resp["id"]
    cache[level] = playlist_id
    _save_playlist_cache(cache)
    print(f"  [playlist] created {name!r} -> {playlist_id}")
    return playlist_id


def _add_to_playlist(yt, video_id: str, playlist_id: str) -> None:
    try:
        yt.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind":    "youtube#video",
                        "videoId": video_id,
                    },
                },
            },
        ).execute()
        print(f"  [playlist] added {video_id} to {playlist_id}")
    except HttpError as e:
        # Don't fail the whole upload if playlist add hiccups — the video
        # is already live, we just lost the categorization for that one.
        print(f"  [playlist] WARN: could not add {video_id} to {playlist_id}: {e}")


# ---------- video upload ----------

def _build_description(word_data: dict, level: str | None = None) -> str:
    word   = word_data["word"]
    ipa    = word_data.get("ipa", "")
    gender = word_data.get("gender", "")
    pos    = word_data.get("part_of_speech", "")
    defn   = word_data["definition"]
    ex_es  = word_data.get("example_es", "")
    ex_en  = word_data.get("example_en", "")
    cefr   = word_data.get("cefr_level", "") or (level if level and not level.startswith("THEME") else "")

    headline = f"{gender} {word}".strip() if gender else word
    lines = [f"Learn the Spanish word '{headline}'!\n",
             f"Word: {headline}"]
    if ipa:
        lines.append(f"Pronunciation: {ipa}")
    if pos:
        lines.append(f"Part of Speech: {pos}")
    if cefr:
        lines.append(f"CEFR Level: {cefr}")
    lines.append(f"Meaning: {defn}")
    if ex_es:
        lines.append(f"\nExample: {ex_es}")
    if ex_en:
        lines.append(f"Translation: {ex_en}")
    if level and level in PLAYLIST_NAMES:
        lines.append(f"\nPart of: {PLAYLIST_NAMES[level]}")
    return "\n".join(lines)


def _insert(yt, video_path: str, title: str, description: str, tags: list) -> str:
    request = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title":           title,
                "description":     description,
                "tags":            tags,
                "categoryId":      YT_CATEGORY_ID,
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus":           "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=MediaFileUpload(video_path, mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def upload_long(long_path: str, word_data: dict,
                level: str | None = None) -> str:
    """Upload the 16:9 companion video and file it into the same level
    playlist as the Short. Returns the YouTube video ID."""
    word     = word_data["word"]
    gender   = word_data.get("gender", "")
    defn     = word_data["definition"]
    headline = f"{gender} {word}".strip() if gender else word

    # Title: Learn 'plátano' in Spanish — banana
    title = f"Learn '{headline}' in Spanish — {defn}"
    # YouTube title cap is 100 chars; truncate cleanly if needed
    if len(title) > 100:
        title = title[:97] + "..."

    base_tags   = YT_TAGS + [word, headline,
                              f"learn {word}", f"{word} spanish",
                              f"{word} en español", "spanish lesson",
                              "learn spanish vocabulary"]
    description = _build_description(word_data, level=level)
    yt          = _get_client()

    video_id = _insert(
        yt, long_path,
        title       = title,
        description = description,
        tags        = base_tags,
    )

    if level:
        try:
            playlist_id = _get_or_create_playlist(yt, level)
            _add_to_playlist(yt, video_id, playlist_id)
        except HttpError as e:
            print(f"  [playlist] WARN: skipped categorization ({e})")

    return video_id


def upload_short_only(short_path: str, word_data: dict,
                       level: str | None = None) -> str:
    """Upload the Short and (if `level` is given) file it into that
    level's playlist. Returns the YouTube video ID."""
    word        = word_data["word"]
    gender      = word_data.get("gender", "")
    headline    = f"{gender} {word}".strip() if gender else word
    base_tags   = YT_TAGS + [word, headline,
                              f"learn {word}", f"{word} spanish",
                              f"{word} en español"]
    description = _build_description(word_data, level=level)
    yt          = _get_client()

    title_parts = [headline, "| Spanish Word of the Day #shorts"]
    title = " ".join(title_parts)

    video_id = _insert(
        yt, short_path,
        title       = title,
        description = description + "\n\n#spanish #learnspanish #español #aprendeespañol #shorts",
        tags        = base_tags + ["shorts"],
    )

    if level:
        try:
            playlist_id = _get_or_create_playlist(yt, level)
            _add_to_playlist(yt, video_id, playlist_id)
        except HttpError as e:
            print(f"  [playlist] WARN: skipped categorization ({e})")

    return video_id
