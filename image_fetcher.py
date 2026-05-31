import os
import requests
from io import BytesIO
from PIL import Image

_STOP = {
    "a","an","the","of","in","to","is","are","was","that","which",
    "or","and","for","with","by","as","at","on","it","its","be",
    "this","from","used","one","also","not","but","have","has",
    "something","someone","especially","usually","often","very",
}


def _def_keywords(word_data: dict) -> str:
    """Extract key words from English definition for Pexels search."""
    defn = word_data.get("definition", "")
    words = [w.strip(".,;()") for w in defn.split()
             if w.strip(".,;()").lower() not in _STOP and len(w) > 2]
    keywords = words[:4]
    if not keywords:
        keywords.append("mexico")
    return " ".join(keywords)


def fetch_word_images(word_data: dict, count: int = 5) -> list:
    """Fetch portrait images via Pexels using English definition keywords."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return []
    query = _def_keywords(word_data)
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": count, "orientation": "portrait"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        photos = resp.json().get("photos", [])
        images = []
        for photo in photos:
            url = (photo.get("src", {}).get("large2x")
                   or photo.get("src", {}).get("large")
                   or photo.get("src", {}).get("medium"))
            if not url:
                continue
            img_resp = requests.get(url, timeout=15)
            if img_resp.status_code == 200:
                images.append(Image.open(BytesIO(img_resp.content)).convert("RGB"))
        return images
    except Exception:
        return []
