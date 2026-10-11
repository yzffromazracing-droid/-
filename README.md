# Facebook 毎日自動投稿

GitHub Actions を使って、Facebook **ページ** に毎日決まった時刻（初期設定: 9:00 JST）に自動投稿します。サーバー不要・無料で動きます。

> ⚠️ Facebook の仕様により、API から投稿できるのは **Facebookページ** だけです。個人アカウント（プロフィール）への自動投稿は 2018 年以降できません。

## 仕組み

毎日 `fb_autopost.py` が「今日の投稿」を1件決めて Graph API で投稿します。優先順位は次のとおりです。

1. `posts.json` に `date` が今日の投稿があればそれ（記念日・告知など）
2. `blog.json` があれば、**Claude（AI）が毎日新しいブログ記事を書いて投稿**
   - 投稿した記事は `blog/YYYY-MM-DD.md` に自動でコミットされ、過去記事と内容がかぶらないよう次回の参考にされます
   - 同じ日に2回動いても、`blog/` に今日の記事があれば二重投稿しません
3. `blog.json` がなければ、`posts.json` の `date` のない投稿を `start_date` から順番にローテーション

## blog.json の書き方（AI記事）

```json
{
  "theme": "暮らしを少し楽しくする、季節の小さな工夫やおすすめ",
  "audience": "30〜50代の、忙しいけれど日々を丁寧に過ごしたい人",
  "tone": "やわらかい「です・ます」調",
  "length": "本文 400〜600 字程度",
  "topics": ["旬の食材とかんたんな食べ方", "季節の行事や暦にまつわる話"],
  "hashtags": ["#暮らし", "#毎日ブログ"],
  "instructions": "宣伝色は出さない。"
}
```

| キー | 説明 |
| --- | --- |
| `theme` | ブログのテーマ（必須） |
| `audience` | 想定読者（任意） |
| `tone` | 文体・口調（任意） |
| `length` | 本文の長さの目安（任意） |
| `topics` | 話題の候補リスト（任意。AIはここから選ぶか、テーマに沿って自由に選ぶ） |
| `hashtags` | 投稿の最後に付けるハッシュタグ（任意） |
| `instructions` | その他の指示。お店の情報、NGワード、締めの定型文など（任意） |
| `model` | 使う Claude のモデル（任意。省略時 `claude-opus-5-5`） |

投稿は `【タイトル】` + 本文 + ハッシュタグ の形になります。AI記事をやめて定型文ローテーションに戻すには `blog.json` を削除します。

## posts.json の書き方（定型文・日付指定）

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

### 2. Claude API キーを用意（AI記事を使う場合）

[Claude Console](https://platform.claude.com/) で API キーを発行します。従量課金で、1記事あたり10円前後、毎日投稿で月300〜500円程度が目安です（記事の長さによります）。

### 3. GitHub に Secrets を登録

リポジトリの **Settings → Secrets and variables → Actions** で追加:

| 名前 | 値 |
| --- | --- |
| `FB_PAGE_ID` | ページID |
| `FB_PAGE_ACCESS_TOKEN` | ページアクセストークン |
| `ANTHROPIC_API_KEY` | Claude API キー（AI記事を使う場合） |

（任意）**Variables** に `FB_GRAPH_VERSION`（例: `v23.0`）を設定すると API バージョンを変更できます。

また **Settings → Actions → General → Workflow permissions** を「Read and write permissions」にしてください（投稿した記事を `blog/` にコミットするため）。

### 4. 動作確認

**Actions → Daily Facebook Post → Run workflow** から手動実行できます。
`dry_run` にチェックを入れたままなら投稿せず内容だけ表示（AI記事も生成して表示します）、外すと実際に投稿します。

## 投稿時刻の変更

`.github/workflows/daily-post.yml` の `cron` を変更します（UTC 指定。JST = UTC + 9 時間）。

```yaml
- cron: "0 0 * * *"   # 09:00 JST
- cron: "0 9 * * *"   # 18:00 JST
```

## ローカルで試す

```bash
pip install -r requirements.txt
ANTHROPIC_API_KEY=... DRY_RUN=1 python3 fb_autopost.py   # 投稿内容の確認
python3 -m unittest discover -s tests          # テスト
FB_PAGE_ID=... FB_PAGE_ACCESS_TOKEN=... python3 fb_autopost.py   # 実際に投稿
```

## 注意

- GitHub Actions の定期実行は混雑時に数分〜数十分遅れることがあります。
- リポジトリに 60 日間コミットがないと、定期実行が自動で停止されます（AI記事モードでは毎日記事がコミットされるので止まりません。ローテーションのみの場合は Actions 画面から再有効化できます）。
- AI が書いた記事は事実と異なる内容を含むことがあります。お店の営業情報など正確さが必要なことは `instructions` に書くか、`posts.json` の日付指定投稿を使ってください。
- トークンは絶対にコードや `posts.json` に直接書かず、Secrets に保存してください。
