import os
import re
import html
import requests

from config import DOWNLOADS_DIR

INSTAGRAM_COOKIES_PATH = os.path.join(os.path.dirname(__file__), "www.instagram.com_cookies.txt")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
}


def _load_cookies() -> dict:
    cookies = {}
    if not os.path.exists(INSTAGRAM_COOKIES_PATH):
        return cookies
    with open(INSTAGRAM_COOKIES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    return cookies


def is_instagram_photo_post(url: str) -> bool:
    return "instagram.com" in url and any(
        seg in url for seg in ("/p/", "/reel/", "/reels/", "/stories/")
    )


def _extract_shortcode(url: str) -> str:
    m = re.search(r"instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"instagram\.com/stories/[^/]+/(\d+)", url)
    if m:
        return m.group(1)
    raise Exception("Не удалось определить ID поста Instagram")


def _find_display_urls(page_text: str) -> list:
    urls = []
    for m in re.finditer(r'"display_url":"([^"]+)"', page_text):
        u = html.unescape(m.group(1).replace("\\u0026", "&").replace("\\/", "/"))
        if u not in urls:
            urls.append(u)
    if not urls:
        m = re.search(r'<meta property="og:image" content="([^"]+)"', page_text)
        if m:
            urls.append(html.unescape(m.group(1)))
    return urls


def _fetch_via_embed(shortcode: str, cookies: dict) -> list:
    page_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    resp = requests.get(page_url, headers=HEADERS, cookies=cookies, timeout=15)
    resp.raise_for_status()
    return _find_display_urls(resp.text)


def _fetch_via_page(shortcode: str, cookies: dict) -> list:
    page_url = f"https://www.instagram.com/p/{shortcode}/"
    resp = requests.get(page_url, headers=HEADERS, cookies=cookies, timeout=15)
    resp.raise_for_status()
    return _find_display_urls(resp.text)


def _fetch_story_via_api(user_url_part: str, cookies: dict) -> list:
    profile_url = f"https://www.instagram.com/{user_url_part}/"
    resp = requests.get(profile_url, headers=HEADERS, cookies=cookies, timeout=15)
    resp.raise_for_status()
    m = re.search(r'"user_id":"(\d+)"', resp.text) or re.search(r'"id":"(\d+)"', resp.text)
    if not m:
        return []
    user_id = m.group(1)

    api_url = f"https://i.instagram.com/api/v1/feed/reels_media/?reel_ids={user_id}"
    api_resp = requests.get(api_url, headers=HEADERS, cookies=cookies, timeout=15)
    if api_resp.status_code != 200:
        return []

    urls = []
    for m in re.finditer(r'"url":"([^"]+\.jpg[^"]*)"', api_resp.text):
        u = html.unescape(m.group(1).replace("\\u0026", "&").replace("\\/", "/"))
        if u not in urls:
            urls.append(u)
    return urls


def download_instagram_photos(url: str) -> list:
    cookies = _load_cookies()

    if "/stories/" in url:
        m = re.search(r"instagram\.com/stories/([^/]+)/", url)
        if not m:
            raise Exception("Не удалось найти фото в посте Instagram")
        image_urls = _fetch_story_via_api(m.group(1), cookies)
        prefix = m.group(1)
    else:
        shortcode = _extract_shortcode(url)
        prefix = shortcode
        image_urls = _fetch_via_embed(shortcode, cookies)
        if not image_urls:
            image_urls = _fetch_via_page(shortcode, cookies)

    if not image_urls:
        raise Exception("Не удалось найти фото в посте Instagram")

    paths = []
    for idx, img_url in enumerate(image_urls, start=1):
        img_resp = requests.get(img_url, headers=HEADERS, cookies=cookies, timeout=20)
        img_resp.raise_for_status()
        path = os.path.join(DOWNLOADS_DIR, f"{prefix}_{idx}.jpg")
        with open(path, "wb") as f:
            f.write(img_resp.content)
        paths.append(path)

    return paths