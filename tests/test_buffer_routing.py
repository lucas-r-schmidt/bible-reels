import unittest
import tempfile
import shutil
from unittest.mock import patch
from pathlib import Path

from src.publisher.buffer_api import publish_via_buffer


class BufferRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Cria estrutura de teste: vídeo e carrossel
        self.video_file = self.temp_path / "post_0100.mp4"
        self.video_file.write_bytes(b"dummy video data")

        self.carousel_dir = self.temp_path / "carousel_0100"
        self.carousel_dir.mkdir(parents=True, exist_ok=True)
        self.slide1 = self.carousel_dir / "slide_01.png"
        self.slide1.write_bytes(b"dummy slide 1")
        self.slide2 = self.carousel_dir / "slide_02.png"
        self.slide2.write_bytes(b"dummy slide 2")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("src.publisher.buffer_api._gql")
    @patch("src.publisher.buffer_api.list_channels")
    @patch("src.publisher.buffer_api._resolve_channel_ids")
    @patch("src.publisher.webhook.resolve_public_media_url")
    def test_saint_post_defaults_to_video_reel(self, mock_resolve_url, mock_channel_ids, mock_channels, mock_gql):
        mock_channel_ids.return_value = ["ch_ig", "ch_tk", "ch_yt"]
        mock_channels.return_value = [
            {"id": "ch_ig", "service": "instagram"},
            {"id": "ch_tk", "service": "tiktok"},
            {"id": "ch_yt", "service": "youtube"},
        ]
        mock_resolve_url.return_value = "https://res.cloudinary.com/test/video.mp4"
        mock_gql.return_value = {"createPost": {"post": {"id": "buf_123"}}}

        post_data = {
            "id": 100,
            "reference": "São Francisco de Assis (04/10)",
            "verse_source": "saint",
            "video_path": str(self.video_file),
            "image_path": str(self.slide1),
            "caption": "Paz e Bem",
        }

        with patch("os.getenv", return_value=""):
            ok = publish_via_buffer(post_data, prefer_carousel=False)

        self.assertTrue(ok)
        # Verifica se o GQL foi chamado para os 3 canais (incluindo YouTube!)
        self.assertEqual(mock_gql.call_count, 3)

    @patch("src.publisher.buffer_api._gql")
    @patch("src.publisher.buffer_api.list_channels")
    @patch("src.publisher.buffer_api._resolve_channel_ids")
    @patch("src.publisher.webhook.resolve_public_media_url")
    def test_saint_post_explicit_carousel_skips_youtube(self, mock_resolve_url, mock_channel_ids, mock_channels, mock_gql):
        mock_channel_ids.return_value = ["ch_ig", "ch_tk", "ch_yt"]
        mock_channels.return_value = [
            {"id": "ch_ig", "service": "instagram"},
            {"id": "ch_tk", "service": "tiktok"},
            {"id": "ch_yt", "service": "youtube"},
        ]
        mock_resolve_url.return_value = "https://res.cloudinary.com/test/slide.png"
        mock_gql.return_value = {"createPost": {"post": {"id": "buf_123"}}}

        post_data = {
            "id": 100,
            "reference": "São Francisco de Assis (04/10)",
            "verse_source": "saint",
            "video_path": str(self.video_file),
            "image_path": str(self.slide1),
            "caption": "Paz e Bem",
        }

        with patch("os.getenv", return_value=""):
            ok = publish_via_buffer(post_data, prefer_carousel=True)

        self.assertTrue(ok)
        # YouTube é ignorado em modo carrossel, chamando apenas Instagram e TikTok (2 chamadas)
        self.assertEqual(mock_gql.call_count, 2)


if __name__ == "__main__":
    unittest.main()
