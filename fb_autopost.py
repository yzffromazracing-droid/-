#!/usr/bin/env python3
"""Facebookページへ毎日自動投稿するスクリプト。

posts.json から「今日の投稿」を1件選び、Facebook Graph API で投稿する。
標準ライブラリのみで動作する。

環境変数:
  FB_PAGE_ID            投稿先FacebookページのID (必須)
  FB_PAGE_ACCESS_TOKEN  ページアクセストークン (必須)
  FB_GRAPH_VERSION      Graph APIのバージョン (省略時: v23.0)
  POSTS_FILE            投稿データのパス (省略時: posts.json)
  POST_TIMEZONE         「今日」を判定するタイムゾーン (省略時: Asia/Tokyo)
  DRY_RUN               "1" なら実際には投稿せず内容を表示するだけ
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

DEFAULT_GRAPH_VERSION = "v23.0"


def load_posts(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("posts"):
        raise ValueError(f"{path} に投稿が1件もありません")
    for i, post in enumerate(data["posts"]):
        if not post.get("message") and not post.get("image_url"):
            raise ValueError(f"posts[{i}] には message か image_url が必要です")
    return data


def select_post(data: dict, today: dt.date) -> dict | None:
    """今日投稿する内容を選ぶ。

    1. "date" が今日の投稿があればそれを使う(記念日・告知など)。
    2. なければ "date" のない投稿を start_date からの経過日数で順番に回す。
    """
    posts = data["posts"]
    iso = today.isoformat()
    for post in posts:
        if post.get("date") == iso:
            return post

    rotation = [p for p in posts if not p.get("date")]
    if not rotation:
        return None
    start = dt.date.fromisoformat(data.get("start_date", "2026-01-01"))
    return rotation[(today - start).days % len(rotation)]


def render(text: str, today: dt.date) -> str:
    weekdays = "月火水木金土日"
    return (
        text.replace("{date}", f"{today.year}年{today.month}月{today.day}日")
        .replace("{weekday}", weekdays[today.weekday()])
    )


def publish(post: dict, page_id: str, token: str, version: str, today: dt.date) -> dict:
    message = render(post.get("message", ""), today)
    if post.get("image_url"):
        endpoint = f"{page_id}/photos"
        params = {"url": post["image_url"], "caption": message}
    else:
        endpoint = f"{page_id}/feed"
        params = {"message": message}
        if post.get("link"):
            params["link"] = post["link"]
    params["access_token"] = token

    req = urllib.request.Request(
        f"https://graph.facebook.com/{version}/{endpoint}",
        data=urllib.parse.urlencode(params).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Graph APIエラー (HTTP {e.code}): {body}") from None


def main() -> int:
    tz = ZoneInfo(os.environ.get("POST_TIMEZONE", "Asia/Tokyo"))
    today = dt.datetime.now(tz).date()
    data = load_posts(os.environ.get("POSTS_FILE", "posts.json"))

    post = select_post(data, today)
    if post is None:
        print(f"{today}: 投稿する内容がないためスキップします")
        return 0

    if os.environ.get("DRY_RUN") == "1":
        print(f"[DRY RUN] {today} の投稿内容:")
        print(render(post.get("message", ""), today))
        for key in ("image_url", "link"):
            if post.get(key):
                print(f"{key}: {post[key]}")
        return 0

    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        print("FB_PAGE_ID と FB_PAGE_ACCESS_TOKEN を設定してください", file=sys.stderr)
        return 1

    version = os.environ.get("FB_GRAPH_VERSION") or DEFAULT_GRAPH_VERSION
    result = publish(post, page_id, token, version, today)
    print(f"{today}: 投稿しました id={result.get('post_id') or result.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
