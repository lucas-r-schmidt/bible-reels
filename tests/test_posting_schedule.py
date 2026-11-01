import unittest

from config.posting_schedule import DAILY_JOBS, MORNING, SAINT_CAROUSEL, SAINT_VIDEO
from src.media_gen.media_policy import media_format, prefers_carousel, supports_carousel


class PostingScheduleTests(unittest.TestCase):
    def test_expected_daily_jobs_are_registered(self):
        expected = [
            "06:30", "08:30", "10:00", "12:00", "15:00",
            "18:00", "19:15", "20:30", "23:15",
        ]
        self.assertEqual([time for time, _ in DAILY_JOBS], expected)

    def test_morning_saint_and_analytics_times(self):
        self.assertEqual(MORNING, "06:30")
        self.assertEqual(SAINT_CAROUSEL, "08:30")
        self.assertEqual(SAINT_VIDEO, "20:30")

    def test_schedule_has_unique_times(self):
        times = [time for time, _ in DAILY_JOBS]
        self.assertEqual(len(times), len(set(times)))

    def test_content_media_policy_defaults_to_video(self):
        # Por padrão, todos os fluxos normais usam formato de vídeo vertical
        self.assertFalse(prefers_carousel("santo"))
        self.assertFalse(prefers_carousel("gospel"))
        self.assertEqual(media_format("oracao"), "video")
        self.assertEqual(media_format("bible"), "video")
        self.assertEqual(media_format("community"), "video")

    def test_content_media_policy_explicit_carousel(self):
        # Apenas fontes capazes geram carrossel quando explicit_carousel=True
        self.assertTrue(supports_carousel("santo"))
        self.assertTrue(supports_carousel("gospel"))
        self.assertTrue(supports_carousel("oracao"))
        self.assertFalse(supports_carousel("bible"))

        self.assertTrue(prefers_carousel("santo", explicit_carousel=True))
        self.assertTrue(prefers_carousel("gospel", explicit_carousel=True))
        self.assertEqual(media_format("oracao", explicit_carousel=True), "carousel")
        self.assertEqual(media_format("bible", explicit_carousel=True), "video")


if __name__ == "__main__":
    unittest.main()
