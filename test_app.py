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

    def test_new_emotions_are_mapped(self):
        self.assertEqual(voice_app.normalize_minimax_emotion("惊讶"), "surprised")
        self.assertEqual(voice_app.normalize_minimax_emotion("平静"), "calm")
        self.assertEqual(voice_app.normalize_minimax_emotion("厌恶"), "disgusted")
        for name in ("惊讶", "平静", "厌恶"):
            self.assertIn(name, voice_app.EMOTION_OPTIONS)

    def test_advanced_options_are_sanitized(self):
        normalize = voice_app.normalize_minimax_options
        self.assertEqual(normalize(None), {})
        self.assertEqual(normalize({}), {})
        fields = ("pitch", "language_boost", "text_normalization_mode", "pronunciation", "format",
                  "sample_rate", "bitrate", "modify_pitch", "modify_intensity", "modify_timbre", "sound_effects")
        self.assertEqual(normalize({key: "" for key in fields}), {})
        dictionary = "\n".join(["St. Luke’s/Saint Luke’s", "没有斜杠的一行", "/缺原文", "重庆/(chong2)(qing4)"])
        options = normalize({
            "pitch": "99", "language_boost": "English", "text_normalization_mode": "quality",
            "pronunciation": dictionary, "format": "WAV", "sample_rate": "44100", "bitrate": "123",
            "modify_pitch": "-250", "modify_intensity": "0", "sound_effects": "robotic",
        })
        self.assertEqual(options["pitch"], 12)
        self.assertEqual(options["language_boost"], "English")
        self.assertEqual(options["text_normalization_mode"], "quality")
        self.assertEqual(options["pronunciation"], ["St. Luke’s/Saint Luke’s", "重庆/(chong2)(qing4)"])
        self.assertEqual(options["format"], "wav")
        self.assertEqual(options["sample_rate"], 44100)
        self.assertNotIn("bitrate", options)
        self.assertEqual(options["voice_modify"], {"pitch": -100, "sound_effects": "robotic"})
        self.assertEqual(normalize({"language_boost": "Klingon", "format": "exe", "sound_effects": "boom", "pitch": "abc"}), {})

    def test_minimax_payload_uses_advanced_options(self):
        captured = {}
        samples = {
            "mp3": b"ID3" + bytes(100),
            "wav": b"RIFF" + bytes(4) + b"WAVE" + bytes(100),
            "flac": b"fLaC" + bytes(100),
        }

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                audio = samples[self.payload["audio_setting"]["format"]]
                return {"base_resp": {"status_code": 0}, "data": {"audio": audio.hex()}}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["payload"] = json
            return FakeResponse(json)

        original = voice_app.requests.post
        voice_app.requests.post = fake_post
        try:
            config = {"minimax": {"api_key": "test"}}
            voice = {"voice_id": "v", "model": "speech-2.8-hd"}
            options = voice_app.normalize_minimax_options({
                "pitch": 2, "format": "wav", "language_boost": "English", "pronunciation": "a/b", "modify_timbre": 20,
            })
            _, mime, ext = voice_app.synthesize_minimax(config, "hi", voice, 0.9, "惊讶", 2.0, options)
            payload = captured["payload"]
            self.assertEqual((mime, ext), ("audio/wav", "wav"))
            self.assertEqual(payload["voice_setting"]["pitch"], 2)
            self.assertEqual(payload["voice_setting"]["emotion"], "surprised")
            self.assertEqual(payload["audio_setting"]["format"], "wav")
            self.assertEqual(payload["language_boost"], "English")
            self.assertEqual(payload["pronunciation_dict"], {"tone": ["a/b"]})
            self.assertEqual(payload["voice_modify"], {"timbre": 20})

            _, mime, ext = voice_app.synthesize_minimax(config, "hi", voice, 1.0, "", 2.0, {"format": "flac"})
            self.assertEqual((mime, ext), ("audio/flac", "flac"))

            # 不传高级参数时，请求体与 v0.1.13 完全一致
            _, mime, ext = voice_app.synthesize_minimax(config, "hi", voice, 1.0, "", 2.0)
            self.assertEqual((mime, ext), ("audio/mpeg", "mp3"))
            self.assertEqual(captured["payload"], {
                "model": "speech-2.8-hd",
                "text": "hi",
                "stream": False,
                "voice_setting": {"voice_id": "v", "speed": 1.0, "vol": 2.0, "pitch": 0},
                "audio_setting": {"format": "mp3", "sample_rate": 32000, "bitrate": 128000, "channel": 1},
                "text_normalization": True,
            })
        finally:
            voice_app.requests.post = original

    def test_page_has_advanced_sections(self):
        html = self.client.get("/").data.decode("utf-8")
        for marker in ("高级参数（可选）", "高级选项（可选）", "素材预检", "previewVoice", "advancedPayload", "复刻使用说明", "v0.1.14", "作者 yuki"):
            self.assertIn(marker, html)
        generated = self.client.post("/api/generate", json={
            "filename": "adv", "text": "测试", "voice_id": "minimax_orin_v6", "speed": 0.9, "volume": 2,
            "advanced": {"pitch": "abc", "format": "flac"},
        }).get_json()
        self.assertTrue(generated["success"])

    def test_voice_id_rule(self):
        rule = voice_app.VOICE_ID_RULE
        self.assertTrue(rule.fullmatch("Narrator_Li_01"))
        for bad in ("short1", "1startsWithDigit", "ends_with_dash-", "has space 01", "中文名字不可以"):
            self.assertFalse(rule.fullmatch(bad))

    def test_clone_is_blocked_in_mock_mode(self):
        response = self.client.post("/api/clone", data={"provider": "minimax", "name": "x"}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
