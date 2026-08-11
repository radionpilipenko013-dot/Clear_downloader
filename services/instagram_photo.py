import os
import re
import html
import json
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

LOGIN_WALL_MARKERS = (
    "Log in to Instagram",
    "loginForm",
    "Войти в Instagram",
    "Ещё не зарегистрированы",
)


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


def is_instagram_reel(url: str) -> bool:
    return "instagram.com" in url and ("/reel/" in url or "/reels/" in url)


def _extract_shortcode(url: str) -> str:
    m = re.search(r"instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"instagram\.com/stories/[^/]+/(\d+)", url)
    if m:
        return m.group(1)
    raise Exception("Не удалось определить ID поста Instagram")


def _looks_like_login_wall(text: str) -> bool:
    return any(marker in text for marker in LOGIN_WALL_MARKERS)


def _find_display_urls(page_text: str) -> list:
    urls = []

    for m in re.finditer(r'"display_url":"([^"]+)"', page_text):
        u = html.unescape(m.group(1).replace("\\u0026", "&").replace("\\/", "/"))
        if u not in urls:
            urls.append(u)
    if urls:
        return urls

    for m in re.finditer(r'"image_versions2":\s*\{\s*"candidates":\s*\[\s*\{\s*"url":\s*"([^"]+)"', page_text):
        u = html.unescape(m.group(1).replace("\\u0026", "&").replace("\\/", "/"))
        if u not in urls:
            urls.append(u)
    if urls:
        return urls

    ld_matches = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', page_text, re.DOTALL
    )
    for block in ld_matches:
        try:
            data = json.loads(block)
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            img = item.get("image")
            if isinstance(img, str) and img not in urls:
                urls.append(img)
            elif isinstance(img, list):
                for i in img:
                    if isinstance(i, str) and i not in urls:
                        urls.append(i)
    if urls:
        return urls

    m = re.search(r'<meta property="og:image" content="([^"]+)"', page_text)
    if m:
        urls.append(html.unescape(m.group(1)))

    return urls


def _fetch(url: str, cookies: dict) -> str:
    resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=15)
    print(f"[instagram_photo.py] GET {url} -> status={resp.status_code} len={len(resp.text)}")
    resp.raise_for_status()
    return resp.text


def _fetch_story_via_api(user_url_part: str, cookies: dict) -> list:
    profile_text = _fetch(f"https://www.instagram.com/{user_url_part}/", cookies)
    m = re.search(r'"user_id":"(\d+)"', profile_text) or re.search(r'"id":"(\d+)"', profile_text)
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
    has_cookies = bool(cookies)
    print(f"[instagram_photo.py] cookies_loaded={has_cookies} count={len(cookies)}")

    if "/stories/" in url:
        m = re.search(r"instagram\.com/stories/([^/]+)/", url)
        if not m:
            raise Exception("Не удалось найти фото в посте Instagram")
        if not has_cookies:
            raise Exception(
                "Instagram: для скачивания сторис нужны куки (www.instagram.com_cookies.txt)"
            )
        prefix = m.group(1)
        image_urls = _fetch_story_via_api(m.group(1), cookies)
    else:
        shortcode = _extract_shortcode(url)
        prefix = shortcode

        embed_text = _fetch(f"https://www.instagram.com/p/{shortcode}/embed/captioned/", cookies)
        embed_login_wall = _looks_like_login_wall(embed_text)
        print(f"[instagram_photo.py] embed login_wall={embed_login_wall}")
        image_urls = [] if embed_login_wall else _find_display_urls(embed_text)
        print(f"[instagram_photo.py] embed image_urls found={len(image_urls)}")

        if not image_urls:
            page_text = _fetch(f"https://www.instagram.com/p/{shortcode}/", cookies)
            page_login_wall = _looks_like_login_wall(page_text)
            print(f"[instagram_photo.py] page login_wall={page_login_wall}")
            if page_login_wall and not has_cookies:
                raise Exception(
                    "Instagram: для этого поста нужны куки (www.instagram.com_cookies.txt) "
                    "— анонимный доступ заблокирован"
                )
            image_urls = _find_display_urls(page_text)
            print(f"[instagram_photo.py] page image_urls found={len(image_urls)}")

    if not image_urls:
        if not has_cookies:
            raise Exception(
                "Instagram: не удалось найти фото. Добавьте www.instagram.com_cookies.txt и попробуйте снова"
            )
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