import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as voice_app


class VoiceStudioTest(unittest.TestCase):
    def setUp(self):
        self.client = voice_app.app.test_client()

    def test_main_workflow_in_mock_mode(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        config = self.client.get("/api/config").get_json()
        self.assertTrue(config["mock_mode"])
        html = self.client.get("/").data.decode("utf-8")
        self.assertIn('<select class="remotion">', html)
        self.assertIn("声音 ID 管理", html)
        self.assertIn("text-preview", html)
        self.assertIn("markAudioError", html)
        self.assertIn("speedPresets", html)
        self.assertIn("volumePresets", html)
        voice_ids = {voice["voice_id"] for voice in config["voices"]}
        self.assertIn("Orin_voice_yinshanshan_v5", voice_ids)
        self.assertIn("Orin_voice_yinshanshan_v4", voice_ids)
        self.assertIn("Orin_voice_yinshanshan_v1", voice_ids)
        self.assertEqual(voice_app.normalize_minimax_emotion("开心"), "happy")
        self.assertEqual(voice_app.normalize_minimax_emotion("温柔"), "neutral")
        self.assertEqual(voice_app.normalize_minimax_emotion("未知情绪"), "")
        with self.assertRaises(RuntimeError):
            voice_app.validate_audio_bytes(b"not an audio file", "audio/mpeg", "测试")

        added_config = self.client.post(
            "/api/voices",
            json={
                "provider": "minimax",
                "name": "测试音色",
                "model": "speech-2.8-hd",
                "voice_id": "test_voice_id",
            },
        ).get_json()
        self.assertTrue(added_config["success"])
        added = next(v for v in added_config["voices"] if v["voice_id"] == "test_voice_id")
        deleted_config = self.client.delete(f"/api/voices/{added['id']}").get_json()
        self.assertTrue(deleted_config["success"])
        self.assertNotIn("test_voice_id", {voice["voice_id"] for voice in deleted_config["voices"]})

        template = self.client.get("/api/template")
        self.assertEqual(template.status_code, 200)
        template_bytes = template.data
        template.close()
        imported = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(template_bytes), "template.xlsx")},
            content_type="multipart/form-data",
        ).get_json()
        self.assertGreaterEqual(len(imported["rows"]), 2)
        self.assertIn("volume", imported["rows"][0])

        generated = self.client.post(
            "/api/generate",
            json={
                "filename": imported["rows"][0]["filename"],
                "text": imported["rows"][0]["text"],
                "voice_id": config["voices"][0]["id"],
                "speed": 1,
                "volume": 2,
            },
        ).get_json()
        self.assertTrue(generated["success"])
        audio = self.client.get(generated["audio_url"])
        self.assertEqual(audio.data[:4], b"RIFF")
        audio.close()

        packed = self.client.post("/api/download", json={"audio_ids": [generated["audio_id"]]})
        with zipfile.ZipFile(io.BytesIO(packed.data)) as archive:
            self.assertEqual(len(archive.namelist()), 1)
        packed.close()


if __name__ == "__main__":
    unittest.main()
