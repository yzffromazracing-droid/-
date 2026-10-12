# Facebook 毎日自動投稿

> このリポジトリには [ロト7 予想ノート](loto7/README.md)（ロト7の過去データ集計・買い目作成アプリ）も入っています。

GitHub Actions を使って、Facebook **ページ** に毎日決まった時刻（初期設定: 9:00 JST）に自動投稿します。サーバー不要・無料で動きます。

> ⚠️ Facebook の仕様により、API から投稿できるのは **Facebookページ** だけです。個人アカウント（プロフィール）への自動投稿は 2018 年以降できません。

## 仕組み

- `posts.json` に投稿内容を書いておく
- 毎日 `fb_autopost.py` が「今日の投稿」を1件選んで Graph API で投稿
  - `date` が今日の投稿があればそれを優先（記念日・告知など）
  - なければ `date` のない投稿を `start_date` から順番にローテーション

## posts.json の書き方

```json
{
  "start_date": "2026-10-01",
  "posts": [
    { "message": "おはようございます！{date}（{weekday}）" },
    { "message": "おすすめ記事", "link": "https://example.com" },
    { "message": "今日の写真", "image_url": "https://example.com/photo.jpg" },
    { "date": "2026-12-25", "message": "メリークリスマス🎄" }
  ]
}
```

| キー | 説明 |
| --- | --- |
| `message` | 本文。`{date}` → `2026年10月11日`、`{weekday}` → `日` に置換 |
| `link` | リンク付き投稿にする URL（任意） |
| `image_url` | 画像投稿にする公開 URL（任意。指定時は `message` がキャプションになる） |
| `date` | `YYYY-MM-DD`。その日だけ投稿する（任意） |

## セットアップ

### 1. Meta アプリとページアクセストークンを用意

1. [Meta for Developers](https://developers.facebook.com/apps/) でアプリを作成（ユースケース:「ページを管理」など）
2. [グラフAPIエクスプローラ](https://developers.facebook.com/tools/explorer/) で自分のアプリを選び、以下の権限でユーザートークンを取得
   - `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
3. **長期ユーザートークン**に交換:
   ```
   https://graph.facebook.com/v23.0/oauth/access_token?grant_type=fb_exchange_token&client_id={アプリID}&client_secret={アプリシークレット}&fb_exchange_token={短期トークン}
   ```
4. 長期ユーザートークンで `GET /me/accounts` を呼ぶと、各ページの `id` と `access_token` が返ります。
   この `access_token` は **有効期限なし** のページアクセストークンです。

### 2. GitHub に Secrets を登録

リポジトリの **Settings → Secrets and variables → Actions** で追加:

| 名前 | 値 |
| --- | --- |
| `FB_PAGE_ID` | ページID |
| `FB_PAGE_ACCESS_TOKEN` | ページアクセストークン |

（任意）**Variables** に `FB_GRAPH_VERSION`（例: `v23.0`）を設定すると API バージョンを変更できます。

### 3. 動作確認

**Actions → Daily Facebook Post → Run workflow** から手動実行できます。
`dry_run` にチェックを入れたままなら投稿せず内容だけ表示、外すと実際に投稿します。

## 投稿時刻の変更

`.github/workflows/daily-post.yml` の `cron` を変更します（UTC 指定。JST = UTC + 9 時間）。

```yaml
- cron: "0 0 * * *"   # 09:00 JST
- cron: "0 9 * * *"   # 18:00 JST
```

## ローカルで試す

```bash
DRY_RUN=1 python3 fb_autopost.py              # 投稿内容の確認
python3 -m unittest discover -s tests          # テスト
FB_PAGE_ID=... FB_PAGE_ACCESS_TOKEN=... python3 fb_autopost.py   # 実際に投稿
```

## 注意

- GitHub Actions の定期実行は混雑時に数分〜数十分遅れることがあります。
- リポジトリに 60 日間コミットがないと、定期実行が自動で停止されます（Actions 画面から再有効化できます）。
- トークンは絶対にコードや `posts.json` に直接書かず、Secrets に保存してください。
