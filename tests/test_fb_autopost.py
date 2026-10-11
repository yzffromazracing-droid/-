import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fb_autopost  # noqa: E402

DATA = {
    "start_date": "2026-10-01",
    "posts": [
        {"message": "A"},
        {"message": "B", "link": "https://example.com"},
        {"message": "C", "image_url": "https://example.com/c.jpg"},
        {"date": "2026-12-25", "message": "X"},
    ],
}


class SelectPostTest(unittest.TestCase):
    def test_rotates_undated_posts(self):
        got = [
            fb_autopost.select_post(DATA, dt.date(2026, 10, d))["message"]
            for d in range(1, 6)
        ]
        self.assertEqual(got, ["A", "B", "C", "A", "B"])

    def test_dated_post_wins(self):
        post = fb_autopost.select_post(DATA, dt.date(2026, 12, 25))
        self.assertEqual(post["message"], "X")

    def test_no_rotation_returns_none(self):
        data = {"posts": [{"date": "2026-12-25", "message": "X"}]}
        self.assertIsNone(fb_autopost.select_post(data, dt.date(2026, 10, 1)))


class RenderTest(unittest.TestCase):
    def test_placeholders(self):
        self.assertEqual(
            fb_autopost.render("{date}（{weekday}）", dt.date(2026, 10, 11)),
            "2026年10月11日（日）",
        )


class PublishTest(unittest.TestCase):
    def _publish(self, post):
        res = mock.MagicMock()
        res.__enter__.return_value = res
        res.read.return_value = json.dumps({"id": "1_2"}).encode()
        with mock.patch("urllib.request.urlopen", return_value=res) as urlopen:
            fb_autopost.publish(post, "123", "tok", "v23.0", dt.date(2026, 10, 1))
        return urlopen.call_args[0][0]

    def test_text_post_uses_feed(self):
        req = self._publish({"message": "hi", "link": "https://example.com"})
        self.assertEqual(req.full_url, "https://graph.facebook.com/v23.0/123/feed")
        self.assertIn(b"link=https", req.data)

    def test_image_post_uses_photos(self):
        req = self._publish({"message": "hi", "image_url": "https://example.com/a.jpg"})
        self.assertEqual(req.full_url, "https://graph.facebook.com/v23.0/123/photos")
        self.assertIn(b"caption=hi", req.data)


BLOG = {"theme": "暮らし", "tone": "です・ます", "hashtags": ["#a", "#b"]}
ARTICLE = {"title": "秋の朝", "body": "本文です。"}


class BlogTest(unittest.TestCase):
    def test_prompt_includes_config_and_past_titles(self):
        prompt = fb_autopost.build_prompt(BLOG, dt.date(2026, 10, 11), ["前の記事"])
        self.assertIn("2026年10月11日（日）", prompt)
        self.assertIn("テーマ: 暮らし", prompt)
        self.assertIn("文体・口調: です・ます", prompt)
        self.assertIn("- 前の記事", prompt)

    def test_article_message_adds_hashtags(self):
        self.assertEqual(
            fb_autopost.article_message(ARTICLE, BLOG),
            "【秋の朝】\n\n本文です。\n\n#a #b",
        )

    def test_save_and_read_back_titles(self):
        with tempfile.TemporaryDirectory() as d:
            fb_autopost.save_article(d, dt.date(2026, 10, 10), {"title": "古い", "body": "x"}, "1_2")
            fb_autopost.save_article(d, dt.date(2026, 10, 11), ARTICLE, None)
            self.assertEqual(fb_autopost.recent_titles(d), ["秋の朝", "古い"])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        d = self.dir.name
        with open(os.path.join(d, "posts.json"), "w") as f:
            json.dump(DATA, f)
        with open(os.path.join(d, "blog.json"), "w") as f:
            json.dump(BLOG, f)
        self.env = {
            "POSTS_FILE": os.path.join(d, "posts.json"),
            "BLOG_CONFIG": os.path.join(d, "blog.json"),
            "BLOG_DIR": os.path.join(d, "blog"),
            "FB_PAGE_ID": "123",
            "FB_PAGE_ACCESS_TOKEN": "tok",
        }

    def _run(self, today):
        now = dt.datetime.combine(today, dt.time(9))
        with mock.patch.dict(os.environ, self.env), \
                mock.patch.object(fb_autopost.dt, "datetime", wraps=dt.datetime) as fake_dt, \
                mock.patch.object(fb_autopost, "generate_article", return_value=ARTICLE) as gen, \
                mock.patch.object(fb_autopost, "publish", return_value={"id": "1_2"}) as pub, \
                mock.patch("sys.stdout"):
            fake_dt.now.return_value = now
            self.assertEqual(fb_autopost.main(), 0)
        return gen, pub

    def test_generates_posts_and_saves_article(self):
        gen, pub = self._run(dt.date(2026, 10, 11))
        gen.assert_called_once()
        self.assertTrue(pub.call_args[0][0]["message"].startswith("【秋の朝】"))
        saved = os.path.join(self.env["BLOG_DIR"], "2026-10-11.md")
        with open(saved, encoding="utf-8") as f:
            self.assertIn("facebook_post_id: 1_2", f.read())

    def test_skips_when_already_posted_today(self):
        self._run(dt.date(2026, 10, 11))
        gen, pub = self._run(dt.date(2026, 10, 11))
        gen.assert_not_called()
        pub.assert_not_called()

    def test_dated_post_overrides_ai(self):
        gen, pub = self._run(dt.date(2026, 12, 25))
        gen.assert_not_called()
        self.assertEqual(pub.call_args[0][0]["message"], "X")


class SampleFileTest(unittest.TestCase):
    def test_sample_posts_json_is_valid(self):
        fb_autopost.load_posts(str(Path(__file__).resolve().parent.parent / "posts.json"))

    def test_sample_blog_json_is_valid(self):
        fb_autopost.load_blog_config(str(Path(__file__).resolve().parent.parent / "blog.json"))


if __name__ == "__main__":
    unittest.main()
