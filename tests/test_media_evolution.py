from pathlib import Path
import tempfile
import unittest
from PIL import Image

from src.media_gen.image_builder import generate_multi_scene_video_frames
from src.media_gen.tts import select_voice_profile
from src.media_gen.video_builder import detect_theme, select_audio_track, AUDIO_THEME_MAP
from src.collector.backgrounds import _prompt_hash


class TestMediaEvolution(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def test_voice_profile_selection(self):
        # Marian / Female Saints
        v, r, p = select_voice_profile("novena", "Nossa Senhora Aparecida", "Ó Mãe querida")
        self.assertEqual(v, "pt-BR-FranciscaNeural")
        self.assertEqual(r, "-4%")
        self.assertEqual(p, "-1Hz")

        v, r, p = select_voice_profile("saint", "Santa Dulce dos Pobres", "Vida de caridade")
        self.assertEqual(v, "pt-BR-FranciscaNeural")

        # Gospel
        v, r, p = select_voice_profile("gospel", "Evangelho segundo São Lucas", "Naquele tempo")
        self.assertEqual(v, "pt-BR-AntonioNeural")
        self.assertEqual(r, "-5%")
        self.assertEqual(p, "-2Hz")

        # Prayer / Psalm
        v, r, p = select_voice_profile("prayer", "Salmo 23", "O Senhor é meu pastor")
        self.assertEqual(v, "pt-BR-AntonioNeural")
        self.assertEqual(r, "-5%")

        # Saint male
        v, r, p = select_voice_profile("saint", "São Francisco de Assis", "História e devoção")
        self.assertEqual(v, "pt-BR-AntonioNeural")
        self.assertEqual(r, "-2%")

    def test_audio_theme_worship_and_categories(self):
        self.assertIn("worship", AUDIO_THEME_MAP)
        self.assertIn("worship_bondade_de_deus.mp3", AUDIO_THEME_MAP["worship"])
        self.assertIn("worship_acaso_nao_sabeis.mp3", AUDIO_THEME_MAP["novena"])

        # Detect theme
        self.assertEqual(detect_theme(text="Evangelho segundo Mateus"), "gospel")
        self.assertEqual(detect_theme(text="Salmo 91"), "psalm")
        self.assertEqual(detect_theme(text="Oração da noite"), "prayer")
        self.assertEqual(detect_theme(text="São Bento abençoai"), "saint")

    def test_generate_multi_scene_video_frames(self):
        # Cria 3 imagens fake
        imgs = []
        for i in range(1, 4):
            img_p = self.tmp_dir / f"test_bg_{i}.png"
            Image.new("RGB", (1080, 1920), color=(20 * i, 30 * i, 40 * i)).save(img_p)
            imgs.append(img_p)

        out_scenes = generate_multi_scene_video_frames(
            post_id=999,
            reference="Salmo 91",
            badge_text="SALMO DO DIA",
            hook_title="REFÚGIO E FORTALEZA",
            bg_images=imgs,
            output_dir=self.tmp_dir / "scenes"
        )
        self.assertEqual(len(out_scenes), 3)
        for sc in out_scenes:
            self.assertTrue(sc.is_file())
            self.assertGreater(sc.stat().st_size, 1000)

    def test_backgrounds_prompt_hash(self):
        h1 = _prompt_hash("Sacred church candle 8k")
        h2 = _prompt_hash("sacred church candle 8k  ")
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
