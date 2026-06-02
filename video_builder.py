import glob
import os
import random
import subprocess
import textwrap
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import *
from tts import generate_speech

AUDIO_PADDING = 0.15

# Background music — drop .mp3/.m4a/.wav files into music/ to enable
MUSIC_DIR        = os.path.join(BASE_DIR, "music")
MUSIC_VOLUME_DB  = -18     # background level relative to speech (dB)
MUSIC_FADE_SEC   = 1.5     # fade in/out duration


# ---------- font loading ----------

def _load_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS.get(style, []):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------- background ----------

def _make_bg(w: int, h: int, bg_image: Image.Image | None = None) -> Image.Image:
    if bg_image is not None:
        img = bg_image.resize((w, h), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=22))
        overlay = Image.new("RGB", (w, h), (5, 5, 18))
        img = Image.blend(img, overlay, alpha=0.62)
        return img
    return _gradient_bg(w, h, BG_TOP, BG_BOTTOM)


def _gradient_bg(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    """Vertical linear gradient between two RGB colors."""
    img  = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _make_bg_clear(w: int, h: int, bg_image: Image.Image | None = None) -> Image.Image:
    if bg_image is not None:
        img = bg_image.resize((w, h), Image.LANCZOS)
        overlay = Image.new("RGB", (w, h), (0, 0, 0))
        return Image.blend(img, overlay, alpha=0.30)
    return _make_bg(w, h)


# ---------- text helpers ----------

def _draw_centered(draw, text, font, color, y, w):
    """Draw text centered horizontally and advance y past the visual bottom.

    PIL draws text starting at the top of its bbox, so the rendered pixels
    span y to y+bbox[3]. We advance by bbox[3] (full visual height) so the
    next element starts cleanly below — using bbox[3]-bbox[1] here causes
    the next line to overlap by the font's ascent offset, which is very
    visible on big headings.
    """
    bbox = font.getbbox(text)
    tw   = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, y), text, font=font, fill=color)
    return y + bbox[3]


def _draw_wrapped(draw, text, font, color, y, w, padding=80):
    max_w = w - padding * 2
    avg_w = max(1, font.getlength("x"))
    cpl   = max(1, int(max_w / avg_w))
    lines = textwrap.wrap(text, width=cpl)
    for line in lines:
        bbox = font.getbbox(line)
        tw   = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y), line, font=font, fill=color)
        y += bbox[3] + 12
    return y


def _draw_brand(draw, w, h, color=None):
    scale   = min(w / 1080, h / 1920)
    f_brand = _load_font("regular", int(34 * scale))
    brand_y = h - int(110 * (h / 1920))
    bbox    = f_brand.getbbox(YT_CHANNEL_NAME)
    draw.text(((w - (bbox[2] - bbox[0])) // 2, brand_y),
              YT_CHANNEL_NAME, font=f_brand, fill=color or BRAND_COLOR)


def _headline(word_data: dict) -> str:
    """Word with article prefixed for nouns: 'la película', 'comer'."""
    gender = word_data.get("gender", "")
    word   = word_data["word"]
    return f"{gender} {word}".strip() if gender else word


# ---------- frame builders ----------

def _make_hook_frame(word_data: dict, w: int, h: int) -> Image.Image:
    scale  = min(w / 1080, h / 1920)
    # Hook gets its own warmer "sunset" gradient — punchy opener that
    # makes the cooler middle scenes feel calmer by contrast.
    img    = _gradient_bg(w, h, HOOK_BG_TOP, HOOK_BG_BOTTOM)
    draw   = ImageDraw.Draw(img)
    # Dark brand on gold reads better than the orange-on-dark of the
    # other scenes — pass the override explicitly.
    _draw_brand(draw, w, h, color=HOOK_BRAND_COLOR)

    f_hook   = _load_font("regular", int(52 * scale))
    f_word   = _load_font("bold",    int(150 * scale))
    f_ipa    = _load_font("italic",  int(50 * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")

    h_top   = f_hook.getbbox("Do you know what")[3]
    h_word  = int(f_word.getbbox(headline)[3] * 1.05)
    h_ipa   = f_ipa.getbbox(ipa)[3] if ipa else 0
    h_bot   = f_hook.getbbox("means?")[3]

    gap_outer = int(44 * scale)
    gap_inner = int(18 * scale)
    total = (h_top + gap_outer + h_word
             + (gap_inner + h_ipa if ipa else 0)
             + gap_outer + h_bot)
    y = (h - total) // 2

    y = _draw_centered(draw, "Do you know what", f_hook,
                       DEFINITION_COLOR, y, w) + gap_outer
    _draw_centered(draw, headline, f_word, WORD_COLOR, y, w)
    y += h_word
    if ipa:
        y += gap_inner
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w)
    y += gap_outer
    _draw_centered(draw, "means?", f_hook, DEFINITION_COLOR, y, w)
    return img


def _make_word_frame(word_data: dict, w: int, h: int,
                      bg_image: Image.Image | None = None) -> Image.Image:
    """Show the word large, with IPA + part of speech beneath."""
    scale  = min(w / 1080, h / 1920)
    img    = _make_bg(w, h, bg_image)
    draw   = ImageDraw.Draw(img)
    _draw_brand(draw, w, h)

    f_word = _load_font("bold",    int(180 * scale))
    f_ipa  = _load_font("italic",  int(64 * scale))
    f_pos  = _load_font("regular", int(50 * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")
    pos      = word_data.get("part_of_speech", "")

    h_word = f_word.getbbox(headline)[3]
    h_ipa  = f_ipa.getbbox(ipa)[3] if ipa else 0
    h_pos  = f_pos.getbbox(pos)[3] if pos else 0
    gap    = int(36 * scale)
    total  = h_word + (gap + h_ipa if ipa else 0) + (gap + h_pos if pos else 0)
    y      = (h - total) // 2

    y = _draw_centered(draw, headline, f_word, WORD_COLOR, y, w) + gap
    if ipa:
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w) + gap
    if pos:
        _draw_centered(draw, pos, f_pos, GENDER_COLOR, y, w)
    return img


# ---------- shared layout helpers ----------

def _wrapped_height(font, text: str, w: int, padding: int = 80) -> int:
    """Predict the total rendered height (px) of `_draw_wrapped` output."""
    if not text:
        return 0
    max_w = w - padding * 2
    avg_w = max(1, font.getlength("x"))
    cpl   = max(1, int(max_w / avg_w))
    lines = textwrap.wrap(text, width=cpl)
    if not lines:
        return 0
    h = sum(font.getbbox(line)[3] for line in lines)
    h += 12 * (len(lines) - 1)
    return h


def _draw_title_block(draw, word_data: dict, w: int, scale: float,
                       y: int, *, word_size: int, ipa_size: int) -> tuple:
    """Draw the (headline, optional IPA) block at the top of a middle frame.

    Returns (new_y, total_block_height). The block height is what should
    have been added to total_h to make vertical centering correct.
    """
    f_word = _load_font("bold",   int(word_size * scale))
    f_ipa  = _load_font("italic", int(ipa_size  * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")

    inner_gap = int(14 * scale)
    h_word    = f_word.getbbox(headline)[3]
    h_ipa     = f_ipa.getbbox(ipa)[3] if ipa else 0
    block_h   = h_word + (inner_gap + h_ipa if ipa else 0)

    y = _draw_centered(draw, headline, f_word, WORD_COLOR, y, w)
    if ipa:
        y += inner_gap
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w)
    return y, block_h


def _make_definition_frame(word_data: dict, w: int, h: int,
                            bg_image: Image.Image | None = None) -> Image.Image:
    """Definition scene — vertically centered in the YouTube safe zone
    (top 6% to bottom 82%; bottom 18% is reserved for YouTube's overlay UI)."""
    scale  = min(w / 1080, h / 1920)
    img    = _make_bg(w, h, bg_image)
    draw   = ImageDraw.Draw(img)
    _draw_brand(draw, w, h)

    f_word  = _load_font("bold",    int(130 * scale))
    f_ipa   = _load_font("italic",  int(56 * scale))
    f_label = _load_font("regular", int(50 * scale))
    f_def   = _load_font("regular", int(68 * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")
    pos      = word_data.get("part_of_speech", "")
    defn     = word_data.get("definition", "")

    # Pre-compute total content height so we can vertically center it.
    inner_gap        = int(14 * scale)
    gap_title_label  = int(34 * scale)
    gap_after_label  = int(20 * scale)
    gap_after_line   = int(40 * scale)

    h_word  = f_word.getbbox(headline)[3]
    h_ipa   = f_ipa.getbbox(ipa)[3] if ipa else 0
    h_label = f_label.getbbox(pos)[3] if pos else 0
    h_def   = _wrapped_height(f_def, defn, w)

    title_h = h_word + (inner_gap + h_ipa if ipa else 0)
    total_h = (title_h
               + (gap_title_label + h_label if pos else gap_title_label)
               + gap_after_label + gap_after_line
               + h_def)

    safe_top    = int(h * 0.06)
    safe_bottom = int(h * 0.82)
    y = max(safe_top, safe_top + (safe_bottom - safe_top - total_h) // 2)

    y = _draw_centered(draw, headline, f_word, WORD_COLOR, y, w)
    if ipa:
        y += inner_gap
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w)
    y += gap_title_label
    if pos:
        y = _draw_centered(draw, pos, f_label, GENDER_COLOR, y, w) + gap_after_label
    lx1, lx2 = w // 5, 4 * w // 5
    draw.line([(lx1, y + 8), (lx2, y + 8)], fill=(55, 55, 75), width=2)
    y += gap_after_line
    if defn:
        _draw_wrapped(draw, defn, f_def, DEFINITION_COLOR, y, w)
    return img


def _make_example_frame(word_data: dict, w: int, h: int,
                         bg_image: Image.Image | None = None) -> Image.Image:
    """Example scene — vertically centered in the safe zone so the short
    doesn't feel top-heavy on a phone screen."""
    scale  = min(w / 1080, h / 1920)
    img    = _make_bg(w, h, bg_image)
    draw   = ImageDraw.Draw(img)
    _draw_brand(draw, w, h)

    f_word  = _load_font("bold",    int(96 * scale))
    f_ipa   = _load_font("italic",  int(46 * scale))
    f_label = _load_font("regular", int(46 * scale))
    f_es    = _load_font("regular", int(64 * scale))
    f_en    = _load_font("italic",  int(52 * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")
    example_es = word_data.get("example_es", "")
    example_en = word_data.get("example_en", "")

    inner_gap        = int(12 * scale)
    gap_title_label  = int(32 * scale)
    gap_after_label  = int(18 * scale)
    gap_after_line   = int(36 * scale)
    gap_between_ex   = int(28 * scale)

    h_word  = f_word.getbbox(headline)[3]
    h_ipa   = f_ipa.getbbox(ipa)[3] if ipa else 0
    h_label = f_label.getbbox("Example")[3]
    h_es    = _wrapped_height(f_es, example_es, w)
    h_en    = _wrapped_height(f_en, f'"{example_en}"' if example_en else "", w)

    title_h = h_word + (inner_gap + h_ipa if ipa else 0)
    total_h = (title_h
               + gap_title_label + h_label + gap_after_label
               + gap_after_line + h_es
               + (gap_between_ex + h_en if example_en else 0))

    safe_top    = int(h * 0.06)
    safe_bottom = int(h * 0.82)
    y = max(safe_top, safe_top + (safe_bottom - safe_top - total_h) // 2)

    y = _draw_centered(draw, headline, f_word, WORD_COLOR, y, w)
    if ipa:
        y += inner_gap
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w)
    y += gap_title_label
    y = _draw_centered(draw, "Example", f_label, GENDER_COLOR, y, w) + gap_after_label
    draw.line([(w // 5, y + 8), (4 * w // 5, y + 8)], fill=(55, 55, 75), width=2)
    y += gap_after_line

    if example_es:
        y = _draw_wrapped(draw, example_es, f_es, DEFINITION_COLOR, y, w) + gap_between_ex
    if example_en:
        _draw_wrapped(draw, f'"{example_en}"', f_en, EXAMPLE_COLOR, y, w)
    return img


def _make_synonyms_frame(word_data: dict, w: int, h: int,
                          bg_image: Image.Image | None = None) -> Image.Image:
    """Synonyms scene — vertically centered with larger type so the
    layout fills the visual frame instead of clustering at the top."""
    scale  = min(w / 1080, h / 1920)
    img    = _make_bg(w, h, bg_image)
    draw   = ImageDraw.Draw(img)
    _draw_brand(draw, w, h)

    f_word  = _load_font("bold",    int(110 * scale))
    f_ipa   = _load_font("italic",  int(48 * scale))
    f_label = _load_font("regular", int(48 * scale))
    f_syn   = _load_font("bold",    int(78 * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")
    syns     = word_data.get("synonyms", [])[:3]

    inner_gap        = int(14 * scale)
    gap_title_label  = int(36 * scale)
    gap_after_label  = int(20 * scale)
    gap_after_line   = int(40 * scale)
    gap_between_syns = int(36 * scale)

    h_word  = f_word.getbbox(headline)[3]
    h_ipa   = f_ipa.getbbox(ipa)[3] if ipa else 0
    h_label = f_label.getbbox("Related")[3]

    title_h = h_word + (inner_gap + h_ipa if ipa else 0)
    syn_h   = (sum(f_syn.getbbox(s)[3] for s in syns)
               + gap_between_syns * max(0, len(syns) - 1))
    total_h = (title_h
               + gap_title_label + h_label + gap_after_label
               + gap_after_line
               + syn_h)

    safe_top    = int(h * 0.06)
    safe_bottom = int(h * 0.82)
    y = max(safe_top, safe_top + (safe_bottom - safe_top - total_h) // 2)

    y = _draw_centered(draw, headline, f_word, WORD_COLOR, y, w)
    if ipa:
        y += inner_gap
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w)
    y += gap_title_label
    y = _draw_centered(draw, "Related", f_label, GENDER_COLOR, y, w) + gap_after_label
    draw.line([(w // 5, y + 8), (4 * w // 5, y + 8)], fill=(55, 55, 75), width=2)
    y += gap_after_line

    for j, syn in enumerate(syns):
        y = _draw_centered(draw, syn, f_syn, WORD_COLOR, y, w)
        if j < len(syns) - 1:
            y += gap_between_syns
    return img


def _make_tip_frame(word_data: dict, tip: str, w: int, h: int,
                     bg_image: Image.Image | None = None) -> Image.Image:
    """Memory-tip scene — vertically centered within the safe zone."""
    scale  = min(w / 1080, h / 1920)
    img    = _make_bg_clear(w, h, bg_image)
    draw   = ImageDraw.Draw(img)
    _draw_brand(draw, w, h)

    f_word  = _load_font("bold",    int(110 * scale))
    f_ipa   = _load_font("italic",  int(48 * scale))
    f_label = _load_font("regular", int(48 * scale))
    f_tip   = _load_font("italic",  int(58 * scale))

    headline = _headline(word_data)
    ipa      = word_data.get("ipa", "")

    inner_gap        = int(14 * scale)
    gap_title_label  = int(36 * scale)
    gap_after_label  = int(20 * scale)
    gap_after_line   = int(40 * scale)

    h_word  = f_word.getbbox(headline)[3]
    h_ipa   = f_ipa.getbbox(ipa)[3] if ipa else 0
    h_label = f_label.getbbox("Memory Tip")[3]
    h_tip   = _wrapped_height(f_tip, tip, w)

    title_h = h_word + (inner_gap + h_ipa if ipa else 0)
    total_h = (title_h
               + gap_title_label + h_label + gap_after_label
               + gap_after_line
               + h_tip)

    safe_top    = int(h * 0.06)
    safe_bottom = int(h * 0.82)
    y = max(safe_top, safe_top + (safe_bottom - safe_top - total_h) // 2)

    y = _draw_centered(draw, headline, f_word, WORD_COLOR, y, w)
    if ipa:
        y += inner_gap
        y = _draw_centered(draw, ipa, f_ipa, IPA_COLOR, y, w)
    y += gap_title_label
    y = _draw_centered(draw, "Memory Tip", f_label, GENDER_COLOR, y, w) + gap_after_label
    draw.line([(w // 5, y + 8), (4 * w // 5, y + 8)], fill=(55, 55, 75), width=2)
    y += gap_after_line
    if tip:
        _draw_wrapped(draw, tip, f_tip, DEFINITION_COLOR, y, w)
    return img


# ---------- audio ----------

def get_audio_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _tts_with_retry(text: str, path: str, lang: str = "es",
                    rate: str = "+0%", retries: int = 4) -> None:
    for attempt in range(retries):
        try:
            generate_speech(text, path, rate=rate, lang=lang)
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def _multi_tts(segments: list, out: str, default_gap: float = 0.05,
               trim_silence: bool = False) -> None:
    """Generate TTS for each segment and concatenate them.

    segments = [{"text": str, "lang": "en"|"es", "rate": "+0%",
                 "pause_after": 0.0 (optional)}, ...]
    """
    audio_paths = []
    for i, seg in enumerate(segments):
        raw  = out + f".raw{i}.mp3"
        path = out + f".seg{i}.mp3"
        if trim_silence:
            _tts_with_retry(seg["text"], raw,
                            lang=seg.get("lang", "en"),
                            rate=seg.get("rate", "+0%"))
            subprocess.run([
                "ffmpeg", "-y", "-i", raw,
                "-af",
                "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-40dB:"
                "stop_periods=-1:stop_duration=0.05:stop_threshold=-40dB",
                "-q:a", "4", "-acodec", "libmp3lame",
                path,
            ], check=True, capture_output=True)
            os.remove(raw)
        else:
            _tts_with_retry(seg["text"], path,
                            lang=seg.get("lang", "en"),
                            rate=seg.get("rate", "+0%"))
        audio_paths.append(path)

    if len(audio_paths) == 1:
        os.replace(audio_paths[0], out)
        return

    silences = []
    for i in range(len(segments) - 1):
        gap = segments[i].get("pause_after", default_gap)
        if gap <= 0.001:
            silences.append(None)
            continue
        sil = out + f".sil{i}.mp3"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", f"{gap:.3f}", "-q:a", "9", "-acodec", "libmp3lame",
            sil,
        ], check=True, capture_output=True)
        silences.append(sil)

    interleaved = []
    for i, audio in enumerate(audio_paths):
        interleaved.append(audio)
        if i < len(silences) and silences[i] is not None:
            interleaved.append(silences[i])

    cmd = ["ffmpeg", "-y"]
    for inp in interleaved:
        cmd += ["-i", inp]

    n = len(interleaved)
    aformat = "".join(
        f"[{i}:a]aformat=sample_rates=44100:channel_layouts=mono[a{i}];"
        for i in range(n)
    )
    concat_in = "".join(f"[a{i}]" for i in range(n))
    fc = aformat + concat_in + f"concat=n={n}:v=0:a=1[out]"

    cmd += ["-filter_complex", fc, "-map", "[out]", out]
    subprocess.run(cmd, check=True, capture_output=True)

    for p in audio_paths + [s for s in silences if s]:
        if os.path.exists(p):
            os.remove(p)


def _render_one_scene(img: Image.Image, audio: str, duration: float,
                      out: str, w: int, h: int) -> None:
    """Render a single scene with tightly-aligned audio."""
    png = out + ".png"
    img.save(png)
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", png,
        "-i", audio,
        "-af", f"apad,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "1",
        "-vf", f"scale={w}:{h},fps={FPS},setpts=PTS-STARTPTS",
        "-vsync", "cfr",
        "-t", f"{duration:.3f}",
        out,
    ], check=True, capture_output=True)
    os.remove(png)


def _concat_clips(clips: list, output: str) -> None:
    """Concat clips with re-encoding to keep audio/video locked in sync."""
    lst = output + ".list.txt"
    with open(lst, "w") as f:
        for p in clips:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", lst,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "1",
        "-vsync", "cfr", "-r", str(FPS),
        "-movflags", "+faststart",
        output,
    ], check=True, capture_output=True)
    os.remove(lst)


# ---------- background music ----------

def _select_music_track() -> str | None:
    """Pick a random music file from MUSIC_DIR. Returns None if the
    directory is empty or missing — pipeline runs without music in that
    case (no breakage)."""
    if not os.path.isdir(MUSIC_DIR):
        return None
    tracks = []
    for ext in ("*.mp3", "*.m4a", "*.wav", "*.ogg", "*.aac"):
        tracks.extend(glob.glob(os.path.join(MUSIC_DIR, ext)))
    if not tracks:
        return None
    return random.choice(tracks)


def _mix_background_music(video_in: str, music_path: str, video_out: str) -> None:
    """Overlay music under speech, looped if shorter than the video,
    trimmed to video length, fades in at the start and out at the end."""
    dur = get_audio_duration(video_in)
    fade_out_start = max(0.0, dur - MUSIC_FADE_SEC)
    music_filter = (
        f"[1:a]volume={MUSIC_VOLUME_DB}dB,"
        f"afade=t=in:st=0:d={MUSIC_FADE_SEC},"
        f"afade=t=out:st={fade_out_start:.3f}:d={MUSIC_FADE_SEC}[m];"
        f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]"
    )
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_in,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", music_filter,
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest", "-movflags", "+faststart",
        video_out,
    ], check=True, capture_output=True)


# ---------- public API ----------

def create_short(word_data: dict, output_path: str,
                 word_images: list = None) -> None:
    os.makedirs(TEMP_DIR, exist_ok=True)

    word    = word_data["word"]
    pos     = word_data.get("part_of_speech", "")
    defn    = word_data["definition"]
    syns    = word_data.get("synonyms", [])
    tip     = word_data.get("memory_tip", "")
    images  = word_images or []
    headline = _headline(word_data)

    def img(i):
        return images[i] if i < len(images) else (images[-1] if images else None)

    img_slot = 0

    # Scene 1: hook — single English voice reading the Spanish word inline
    specs = [{
        "frame": _make_hook_frame(word_data, WIDTH, HEIGHT),
        "segments": [
            {"text": f"Do you know what {word} means in Spanish?",
             "lang": "en", "rate": "+15%"},
        ],
    }]

    # Scene 2: pronunciation — say the word in Spanish twice
    specs.append({
        "frame": _make_word_frame(word_data, WIDTH, HEIGHT),
        "segments": [
            {"text": headline, "lang": "es", "rate": "+0%",
             "pause_after": 0.30},
            {"text": headline, "lang": "es", "rate": "+0%"},
        ],
    })

    # Scene 3: definition
    specs.append({
        "frame": _make_definition_frame(word_data, WIDTH, HEIGHT, bg_image=img(img_slot)),
        "segments": [
            {"text": (f"{pos}. " if pos else "") + defn + ".",
             "lang": "en", "rate": "+10%"},
        ],
    })
    img_slot += 1

    # Scene 4: example sentence
    example_es = word_data.get("example_es", "")
    example_en = word_data.get("example_en", "")
    if example_es:
        ex_segments = [{"text": example_es, "lang": "es", "rate": "+0%"}]
        if example_en:
            ex_segments.append({"text": f"In English: {example_en}",
                                 "lang": "en", "rate": "+10%"})
        specs.append({
            "frame":    _make_example_frame(word_data, WIDTH, HEIGHT, img(img_slot)),
            "segments": ex_segments,
        })
        img_slot += 1

    # Scene 5: synonyms — EN intro then each related word in Spanish
    if syns:
        syn_segments = [
            {"text": "Related words.", "lang": "en", "rate": "+10%",
             "pause_after": 0.25},
        ]
        top = syns[:3]
        for j, s in enumerate(top):
            syn_segments.append({
                "text": s, "lang": "es", "rate": "+0%",
                "pause_after": 0.25 if j < len(top) - 1 else 0.0,
            })
        specs.append({
            "frame":    _make_synonyms_frame(word_data, WIDTH, HEIGHT, img(img_slot)),
            "segments": syn_segments,
        })
        img_slot += 1

    # Scene 6: memory tip
    if tip:
        specs.append({
            "frame": _make_tip_frame(word_data, tip, WIDTH, HEIGHT, img(img_slot)),
            "segments": [
                {"text": f"Memory tip. {tip}", "lang": "en", "rate": "+10%"},
            ],
        })

    # Scene 7: recap — final pronunciation
    specs.append({
        "frame": _make_word_frame(word_data, WIDTH, HEIGHT),
        "segments": [
            {"text": headline, "lang": "es", "rate": "+0%"},
        ],
    })

    # Render each scene: build audio (multi-segment) then mux with frame
    clip_paths = []
    for i, spec in enumerate(specs):
        apath = os.path.join(TEMP_DIR, f"short_a_{i}.mp3")
        _multi_tts(spec["segments"], apath,
                   trim_silence=spec.get("trim_silence", False))

        dur  = get_audio_duration(apath) + AUDIO_PADDING
        clip = os.path.join(TEMP_DIR, f"short_clip_{i}.mp4")
        _render_one_scene(spec["frame"], apath, dur, clip, WIDTH, HEIGHT)
        clip_paths.append(clip)

        if os.path.exists(apath):
            os.remove(apath)

    # Step 1: concat all scene clips into one continuous video
    music = _select_music_track()
    if music:
        pre_music = output_path + ".no_music.mp4"
        _concat_clips(clip_paths, pre_music)
        print(f"  [music] mixing {os.path.basename(music)}")
        _mix_background_music(pre_music, music, output_path)
        os.remove(pre_music)
    else:
        _concat_clips(clip_paths, output_path)

    for p in clip_paths:
        if os.path.exists(p):
            os.remove(p)


def create_long(word_data: dict, output_path: str,
                word_images: list = None) -> None:
    """Render a 16:9 companion video (LONG_WIDTH × LONG_HEIGHT) with the
    same scene structure as create_short but in landscape format.

    The audio content is identical — same hook, pronunciation, definition,
    example, synonyms, memory tip — so viewers who watch both formats get
    a consistent lesson in their preferred aspect ratio.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)

    word     = word_data["word"]
    pos      = word_data.get("part_of_speech", "")
    defn     = word_data["definition"]
    syns     = word_data.get("synonyms", [])
    tip      = word_data.get("memory_tip", "")
    images   = word_images or []
    headline = _headline(word_data)

    W, H = LONG_WIDTH, LONG_HEIGHT

    def img(i):
        return images[i] if i < len(images) else (images[-1] if images else None)

    img_slot = 0

    # Scene 1: hook
    specs = [{
        "frame": _make_hook_frame(word_data, W, H),
        "segments": [
            {"text": f"Do you know what {word} means in Spanish?",
             "lang": "en", "rate": "+15%"},
        ],
    }]

    # Scene 2: pronunciation — say the word in Spanish twice
    specs.append({
        "frame": _make_word_frame(word_data, W, H),
        "segments": [
            {"text": headline, "lang": "es", "rate": "+0%",
             "pause_after": 0.30},
            {"text": headline, "lang": "es", "rate": "+0%"},
        ],
    })

    # Scene 3: definition
    specs.append({
        "frame": _make_definition_frame(word_data, W, H, bg_image=img(img_slot)),
        "segments": [
            {"text": (f"{pos}. " if pos else "") + defn + ".",
             "lang": "en", "rate": "+10%"},
        ],
    })
    img_slot += 1

    # Scene 4: example sentence
    example_es = word_data.get("example_es", "")
    example_en = word_data.get("example_en", "")
    if example_es:
        ex_segments = [{"text": example_es, "lang": "es", "rate": "+0%"}]
        if example_en:
            ex_segments.append({"text": f"In English: {example_en}",
                                 "lang": "en", "rate": "+10%"})
        specs.append({
            "frame":    _make_example_frame(word_data, W, H, img(img_slot)),
            "segments": ex_segments,
        })
        img_slot += 1

    # Scene 5: synonyms
    if syns:
        syn_segments = [
            {"text": "Related words.", "lang": "en", "rate": "+10%",
             "pause_after": 0.25},
        ]
        top = syns[:3]
        for j, s in enumerate(top):
            syn_segments.append({
                "text": s, "lang": "es", "rate": "+0%",
                "pause_after": 0.25 if j < len(top) - 1 else 0.0,
            })
        specs.append({
            "frame":    _make_synonyms_frame(word_data, W, H, img(img_slot)),
            "segments": syn_segments,
        })
        img_slot += 1

    # Scene 6: memory tip
    if tip:
        specs.append({
            "frame": _make_tip_frame(word_data, tip, W, H, img(img_slot)),
            "segments": [
                {"text": f"Memory tip. {tip}", "lang": "en", "rate": "+10%"},
            ],
        })

    # Scene 7: recap pronunciation + sign-off
    specs.append({
        "frame": _make_word_frame(word_data, W, H),
        "segments": [
            {"text": headline, "lang": "es", "rate": "+0%",
             "pause_after": 0.25},
            {"text": "Now you know! Keep learning Spanish with Everyday Spanish.",
             "lang": "en", "rate": "+10%"},
        ],
    })

    # Render
    clip_paths = []
    for i, spec in enumerate(specs):
        apath = os.path.join(TEMP_DIR, f"long_a_{i}.mp3")
        _multi_tts(spec["segments"], apath,
                   trim_silence=spec.get("trim_silence", False))

        dur  = get_audio_duration(apath) + AUDIO_PADDING
        clip = os.path.join(TEMP_DIR, f"long_clip_{i}.mp4")
        _render_one_scene(spec["frame"], apath, dur, clip, W, H)
        clip_paths.append(clip)

        if os.path.exists(apath):
            os.remove(apath)

    music = _select_music_track()
    if music:
        pre_music = output_path + ".no_music.mp4"
        _concat_clips(clip_paths, pre_music)
        print(f"  [music] mixing {os.path.basename(music)}")
        _mix_background_music(pre_music, music, output_path)
        os.remove(pre_music)
    else:
        _concat_clips(clip_paths, output_path)

    for p in clip_paths:
        if os.path.exists(p):
            os.remove(p)
