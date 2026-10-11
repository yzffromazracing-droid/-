#!/usr/bin/env python3
"""Facebookページへ毎日自動投稿するスクリプト。

posts.json から「今日の投稿」を1件選び、Facebook Graph API で投稿する。
blog.json があれば、日付指定のない日は Claude が毎日新しいブログ記事を書いて投稿し、
blog/YYYY-MM-DD.md に保存する。

環境変数:
  FB_PAGE_ID            投稿先FacebookページのID (必須)
  FB_PAGE_ACCESS_TOKEN  ページアクセストークン (必須)
  FB_GRAPH_VERSION      Graph APIのバージョン (省略時: v23.0)
  ANTHROPIC_API_KEY     AI記事生成に使う Claude API キー (blog.json 使用時に必須)
  POSTS_FILE            投稿データのパス (省略時: posts.json)
  BLOG_CONFIG           AI記事の設定ファイル (省略時: blog.json。無ければローテーション)
  BLOG_DIR              投稿済み記事の保存先 (省略時: blog)
  POST_TIMEZONE         「今日」を判定するタイムゾーン (省略時: Asia/Tokyo)
  DRY_RUN               "1" なら実際には投稿せず内容を表示するだけ
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

DEFAULT_GRAPH_VERSION = "v23.0"
CLAUDE_MODEL = "claude-opus-5-5"
RECENT_TITLES = 60


def load_posts(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("posts"):
        raise ValueError(f"{path} に投稿が1件もありません")
    for i, post in enumerate(data["posts"]):
        if not post.get("message") and not post.get("image_url"):
            raise ValueError(f"posts[{i}] には message か image_url が必要です")
    return data


def dated_post(data: dict, today: dt.date) -> dict | None:
    iso = today.isoformat()
    return next((p for p in data["posts"] if p.get("date") == iso), None)


def select_post(data: dict, today: dt.date) -> dict | None:
    """今日投稿する内容を選ぶ。

    1. "date" が今日の投稿があればそれを使う(記念日・告知など)。
    2. なければ "date" のない投稿を start_date からの経過日数で順番に回す。
    """
    post = dated_post(data, today)
    if post:
        return post

    rotation = [p for p in data["posts"] if not p.get("date")]
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


def load_blog_config(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    if not config.get("theme"):
        raise ValueError(f"{path} に theme を書いてください")
    return config


def recent_titles(blog_dir: str, limit: int = RECENT_TITLES) -> list[str]:
    """過去記事のタイトル(各ファイルの1行目)を新しい順に返す。"""
    files = sorted(pathlib.Path(blog_dir).glob("*.md"), reverse=True)[:limit]
    titles = []
    for f in files:
        first = f.read_text(encoding="utf-8").split("\n", 1)[0]
        titles.append(first.lstrip("# ").strip())
    return titles


ARTICLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["title", "body"],
    "additionalProperties": False,
}


def build_prompt(config: dict, today: dt.date, past_titles: list[str]) -> str:
    weekdays = "月火水木金土日"
    lines = [
        f"今日は{today.year}年{today.month}月{today.day}日（{weekdays[today.weekday()]}）です。",
        "Facebookページに投稿する、今日のブログ記事を1本書いてください。",
        "",
        f"テーマ: {config['theme']}",
    ]
    for key, label in (("audience", "読者"), ("tone", "文体・口調"), ("length", "本文の長さ")):
        if config.get(key):
            lines.append(f"{label}: {config[key]}")
    if config.get("topics"):
        lines.append("話題の候補（この中から選んでも、テーマに沿って自由に選んでもよい）:")
        lines += [f"- {t}" for t in config["topics"]]
    if config.get("instructions"):
        lines += ["", "その他の指示:", config["instructions"]]
    if past_titles:
        lines += ["", "これまでの記事タイトル（内容や切り口が重複しないようにしてください）:"]
        lines += [f"- {t}" for t in past_titles]
    lines += [
        "",
        "書き方のルール:",
        "- Facebookはマークダウンを表示しないので、見出し記号(#)や**太字**は使わず、短い段落と改行で読みやすくする",
        "- 季節感や曜日を自然に取り入れてよいが、日付が分かる事実やニュースを創作しない",
        "- 最後に読者への問いかけなど、コメントしたくなる一言を添える",
        "- ハッシュタグは本文に含めない",
        "",
        "title に記事タイトル、body に本文を入れて返してください。",
    ]
    return "\n".join(lines)


def generate_article(config: dict, today: dt.date, past_titles: list[str]) -> dict:
    import anthropic  # AI記事を使うときだけ必要

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=config.get("model") or CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": ARTICLE_SCHEMA},
        },
        messages=[{"role": "user", "content": build_prompt(config, today, past_titles)}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"記事を生成できませんでした (stop_reason={response.stop_reason})")
    text = next(b.text for b in response.content if b.type == "text")
    article = json.loads(text)
    return {"title": article["title"].strip(), "body": article["body"].strip()}


def article_message(article: dict, config: dict) -> str:
    message = f"【{article['title']}】\n\n{article['body']}"
    if config.get("hashtags"):
        message += "\n\n" + " ".join(config["hashtags"])
    return message


def save_article(blog_dir: str, today: dt.date, article: dict, post_id: str | None) -> str:
    os.makedirs(blog_dir, exist_ok=True)
    path = os.path.join(blog_dir, f"{today.isoformat()}.md")
    footer = f"\n\n<!-- facebook_post_id: {post_id} -->" if post_id else ""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {article['title']}\n\n{article['body']}{footer}\n")
    return path


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
    blog = load_blog_config(os.environ.get("BLOG_CONFIG", "blog.json"))
    blog_dir = os.environ.get("BLOG_DIR", "blog")
    dry_run = os.environ.get("DRY_RUN") == "1"

    # 記念日などの日付指定投稿 > AI記事 > ローテーション の順で使う
    article = None
    post = dated_post(data, today)
    if post is None and blog is not None:
        if os.path.exists(os.path.join(blog_dir, f"{today.isoformat()}.md")) and not dry_run:
            print(f"{today}: 今日の記事は投稿済みのためスキップします")
            return 0
        article = generate_article(blog, today, recent_titles(blog_dir))
        post = {"message": article_message(article, blog)}
    elif post is None:
        post = select_post(data, today)

    if post is None:
        print(f"{today}: 投稿する内容がないためスキップします")
        return 0

    if dry_run:
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
    post_id = result.get("post_id") or result.get("id")
    print(f"{today}: 投稿しました id={post_id}")
    if article:
        print(f"記事を保存しました: {save_article(blog_dir, today, article, post_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
