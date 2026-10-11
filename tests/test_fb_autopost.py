import datetime as dt
import json
import sys
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


class SampleFileTest(unittest.TestCase):
    def test_sample_posts_json_is_valid(self):
        fb_autopost.load_posts(str(Path(__file__).resolve().parent.parent / "posts.json"))


if __name__ == "__main__":
    unittest.main()
