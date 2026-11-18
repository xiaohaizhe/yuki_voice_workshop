"""AI 语音工作台：豆包 + MiniMax 的本地网页语音工具。

作者：yuki。协作约定见 AGENTS.md，版本历史见 CHANGELOG.md。
"""
from __future__ import annotations

import base64
import csv
import copy
import io
import json
import math
import os
import re
import struct
import uuid
import wave
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"
CONFIG_PATH = ROOT / "config.local.json"
DATA_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
APP_VERSION = "v0.1.14"
APP_AUTHOR = "yuki"
DEFAULT_VOLUME = 2.0
EMOTION_OPTIONS = ["开心", "兴奋", "惊讶", "悲伤", "愤怒", "焦急", "害怕", "厌恶", "平静", "温柔", "严肃"]
SPEED_OPTIONS = ["0.8", "1", "1.2", "1.5"]
VOLUME_OPTIONS = ["1", "1.5", "2", "3", "4"]
MINIMAX_EMOTION_MAP = {
    "开心": "happy",
    "兴奋": "happy",
    "悲伤": "sad",
    "愤怒": "angry",
    "焦急": "fearful",
    "害怕": "fearful",
    "惊讶": "surprised",
    "厌恶": "disgusted",
    "平静": "calm",
    "calm": "calm",
    "温柔": "neutral",
    "严肃": "neutral",
    "happy": "happy",
    "sad": "sad",
    "angry": "angry",
    "fearful": "fearful",
    "disgusted": "disgusted",
    "surprised": "surprised",
    "neutral": "neutral",
}

DEFAULT_CONFIG = {
    "mock_mode": True,
    "doubao": {"app_id": "", "access_token": "", "api_key": ""},
    "minimax": {"api_key": ""},
    "voices": [
        {
            "id": "doubao_sunshine_achen",
            "name": "阳光阿辰",
            "provider": "doubao",
            "model": "seed-tts-1.0",
            "voice_id": "zh_male_qingyiyuxuan_mars_bigtts",
        },
        {
            "id": "minimax_orin_v6",
            "name": "Orin（殷姗姗 V6）",
            "provider": "minimax",
            "model": "speech-2.8-hd",
            "voice_id": "Orin_voice_yinshanshan_v6",
        },
        {
            "id": "minimax_orin_v5",
            "name": "Orin（殷姗姗 V5）",
            "provider": "minimax",
            "model": "speech-2.8-hd",
            "voice_id": "Orin_voice_yinshanshan_v5",
        },
        {
            "id": "minimax_orin_v4",
            "name": "Orin（殷姗姗 V4）",
            "provider": "minimax",
            "model": "speech-2.8-hd",
            "voice_id": "Orin_voice_yinshanshan_v4",
        },
        {
            "id": "minimax_orin_v1",
            "name": "Orin（殷姗姗 V1）",
            "provider": "minimax",
            "model": "speech-2.8-hd",
            "voice_id": "Orin_voice_yinshanshan_v1",
        },
        {
            "id": "minimax_zhangyun_001",
            "name": "张赟_惊讶",
            "provider": "minimax",
            "model": "speech-2.8-hd",
            "voice_id": "zhangyun_001",
        },
    ],
}


def deep_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def load_config():
    config = deep_copy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            config["mock_mode"] = bool(saved.get("mock_mode", True))
            for provider in ("doubao", "minimax"):
                config[provider].update(saved.get(provider, {}))
            if saved.get("voices"):
                saved_voices = [normalize_voice_entry(v) for v in saved["voices"] if isinstance(v, dict)]
                saved_voices = [v for v in saved_voices if v]
                default_ids = {v["id"] for v in config["voices"]}
                extra_voices = [v for v in saved_voices if v["id"] not in default_ids]
                overrides = {v["id"]: v for v in saved_voices if v["id"] in default_ids}
                config["voices"] = [overrides.get(v["id"], v) for v in config["voices"]] + extra_voices
        except (OSError, ValueError, TypeError):
            pass
    return config


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_voice_entry(raw):
    provider = str(raw.get("provider") or "").strip().lower()
    voice_id = str(raw.get("voice_id") or "").strip()
    if provider not in ("doubao", "minimax") or not voice_id:
        return None
    model = str(raw.get("model") or "").strip()
    if not model:
        model = "seed-tts-1.0" if provider == "doubao" else "speech-2.8-hd"
    name = str(raw.get("name") or voice_id).strip()
    local_id = str(raw.get("id") or "").strip()
    if not local_id:
        local_id = f"{provider}_{safe_name(voice_id, 'voice').lower()}"
    return {
        "id": safe_name(local_id, f"{provider}_{uuid.uuid4().hex[:8]}"),
        "name": name[:60],
        "provider": provider,
        "model": model[:80],
        "voice_id": voice_id[:160],
    }


def public_config(config):
    return {
        "mock_mode": config["mock_mode"],
        "doubao_ready": bool(config["doubao"].get("app_id") and config["doubao"].get("access_token")),
        "minimax_ready": bool(config["minimax"].get("api_key")),
        "voices": config["voices"],
    }


def safe_name(value, fallback="voice"):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(value or "")).strip(" .")
    return name[:100] or fallback


def get_voice(config, voice_ref):
    return next((v for v in config["voices"] if v["id"] == voice_ref), None)


def normalize_minimax_emotion(emotion):
    raw = str(emotion or "").strip()
    if not raw:
        return ""
    return MINIMAX_EMOTION_MAP.get(raw, "")


MINIMAX_LANGUAGES = {"auto", "Chinese", "Chinese,Yue", "English", "Japanese", "Korean"}
MINIMAX_FORMATS = {"mp3": ("audio/mpeg", "mp3"), "wav": ("audio/wav", "wav"), "flac": ("audio/flac", "flac")}
MINIMAX_SAMPLE_RATES = {8000, 16000, 22050, 24000, 32000, 44100}
MINIMAX_BITRATES = {32000, 64000, 128000, 256000}
MINIMAX_SOUND_EFFECTS = {"spacious_echo", "auditorium_echo", "lofi_telephone", "robotic"}
VOICE_ID_RULE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{6,254}[A-Za-z0-9]")


def _as_int(value, low, high):
    if value in (None, ""):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(low, min(high, number))


def normalize_minimax_options(raw):
    """把页面“高级参数”整理成 MiniMax 可接受的字段；留空或不合法的项一律忽略，保持接口默认。"""
    if not isinstance(raw, dict):
        return {}
    options = {}
    pitch = _as_int(raw.get("pitch"), -12, 12)
    if pitch:
        options["pitch"] = pitch
    language = str(raw.get("language_boost") or "").strip()
    if language in MINIMAX_LANGUAGES:
        options["language_boost"] = language
    mode = str(raw.get("text_normalization_mode") or "").strip()
    if mode in ("basic", "quality"):
        options["text_normalization_mode"] = mode
    tone = []
    for line in str(raw.get("pronunciation") or "").splitlines():
        line = line.strip()
        left, sep, right = line.partition("/")
        if sep and left.strip() and right.strip() and len(line) <= 120:
            tone.append(line)
    if tone:
        options["pronunciation"] = tone[:50]
    audio_format = str(raw.get("format") or "").strip().lower()
    if audio_format in MINIMAX_FORMATS:
        options["format"] = audio_format
    sample_rate = _as_int(raw.get("sample_rate"), 0, 10 ** 6)
    if sample_rate in MINIMAX_SAMPLE_RATES:
        options["sample_rate"] = sample_rate
    bitrate = _as_int(raw.get("bitrate"), 0, 10 ** 6)
    if bitrate in MINIMAX_BITRATES:
        options["bitrate"] = bitrate
    modify = {}
    for key in ("pitch", "intensity", "timbre"):
        number = _as_int(raw.get(f"modify_{key}"), -100, 100)
        if number:
            modify[key] = number
    effect = str(raw.get("sound_effects") or "").strip()
    if effect in MINIMAX_SOUND_EFFECTS:
        modify["sound_effects"] = effect
    if modify:
        options["voice_modify"] = modify
    return options


def make_mock_wav(text):
    sample_rate = 16000
    duration = min(2.2, max(0.65, len(text) * 0.035))
    frames = int(sample_rate * duration)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(frames):
            fade = min(1.0, i / 400, (frames - i) / 400)
            value = int(4500 * fade * math.sin(2 * math.pi * 440 * i / sample_rate))
            wav.writeframesraw(struct.pack("<h", value))
    return output.getvalue(), "audio/wav", "wav"


def validate_audio_bytes(audio, mime, provider):
    if not audio or len(audio) < 64:
        raise RuntimeError(f"{provider} 接口返回了数据，但音频内容为空或过短，未保存为成功音频")
    head = audio[:4096]
    if mime == "audio/wav" and audio.startswith(b"RIFF") and b"WAVE" in audio[:16]:
        return
    if mime == "audio/flac" and audio.startswith(b"fLaC"):
        return
    if mime == "audio/mpeg" and (audio.startswith(b"ID3") or any(head[i] == 0xFF and head[i + 1] & 0xE0 == 0xE0 for i in range(len(head) - 1))):
        return
    raise RuntimeError(f"{provider} 接口返回了数据，但不是浏览器可播放的 MP3/WAV/FLAC 音频，请检查 Voice ID 权限或接口参数")


def synthesize_doubao(config, text, voice, speed, emotion, instruction, volume):
    speech_rate = max(-50, min(100, int((speed - 1.0) * 100)))
    params = {"format": "mp3", "sample_rate": 24000, "speech_rate": speech_rate}
    req_params = {"text": text, "speaker": voice["voice_id"], "audio_params": params}
    if instruction and voice["model"] == "seed-tts-2.0":
        req_params["additions"] = json.dumps({"context_texts": [instruction]}, ensure_ascii=False)
    payload = {"user": {"uid": "local_voice_studio"}, "req_params": req_params}
    headers = {
        "X-Api-App-Id": config["doubao"]["app_id"],
        "X-Api-Access-Key": config["doubao"]["access_token"],
        "X-Api-Resource-Id": voice["model"],
        "Content-Type": "application/json",
    }
    if config["doubao"].get("api_key"):
        headers.pop("X-Api-App-Id", None)
        headers.pop("X-Api-Access-Key", None)
        headers["X-Api-Key"] = config["doubao"]["api_key"]
    response = requests.post(
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        headers=headers,
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    audio_chunks = []
    last_error = None
    for line in response.text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("code") == 0 and obj.get("data"):
            audio_chunks.append(obj["data"])
        elif obj.get("code") not in (None, 0, 20000000):
            last_error = obj.get("message") or f"豆包错误码 {obj.get('code')}"
    if not audio_chunks:
        raise RuntimeError(last_error or "豆包接口未返回音频，请检查音色权限和参数")
    import base64
    audio = base64.b64decode("".join(audio_chunks))
    validate_audio_bytes(audio, "audio/mpeg", "豆包")
    return audio, "audio/mpeg", "mp3"


def synthesize_minimax(config, text, voice, speed, emotion, volume, options=None):
    options = options or {}
    voice_setting = {"voice_id": voice["voice_id"], "speed": speed, "vol": volume, "pitch": options.get("pitch", 0)}
    normalized_emotion = normalize_minimax_emotion(emotion)
    if normalized_emotion:
        voice_setting["emotion"] = normalized_emotion
    payload = {
        "model": voice["model"],
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "format": options.get("format", "mp3"),
            "sample_rate": options.get("sample_rate", 32000),
            "bitrate": options.get("bitrate", 128000),
            "channel": 1,
        },
        "text_normalization": True,
    }
    for field in ("language_boost", "text_normalization_mode", "voice_modify"):
        if field in options:
            payload[field] = options[field]
    if options.get("pronunciation"):
        payload["pronunciation_dict"] = {"tone": options["pronunciation"]}
    mime, ext = MINIMAX_FORMATS[options.get("format", "mp3")]
    response = requests.post(
        "https://api.minimaxi.com/v1/t2a_v2",
        headers={"Authorization": f"Bearer {config['minimax']['api_key']}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    status = data.get("base_resp", {})
    if status.get("status_code") not in (None, 0):
        status_msg = status.get("status_msg") or f"MiniMax 错误码 {status.get('status_code')}"
        if "access" in status_msg.lower() and "vc" in status_msg.lower():
            raise RuntimeError("当前 MiniMax 账号没有这个复刻音色权限，请换一个音色或使用对应账号的 API Key")
        if "invalid params" in status_msg.lower():
            raise RuntimeError(f"MiniMax 参数不被接受：{status_msg}")
        raise RuntimeError(status_msg)
    audio_hex = data.get("data", {}).get("audio")
    if not audio_hex:
        raise RuntimeError("MiniMax 接口未返回音频，请检查 Voice ID 是否属于当前账号")
    try:
        audio = bytes.fromhex(audio_hex)
    except ValueError as exc:
        raise RuntimeError("MiniMax 返回的音频内容格式异常，不是有效的十六进制音频数据") from exc
    validate_audio_bytes(audio, mime, "MiniMax")
    return audio, mime, ext


@app.get("/")
def index():
    return render_template("index.html", app_version=APP_VERSION, app_author=APP_AUTHOR)


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/api/config")
def config_get():
    return jsonify(public_config(load_config()))


@app.post("/api/config")
def config_save():
    incoming = request.get_json(force=True) or {}
    config = load_config()
    config["mock_mode"] = bool(incoming.get("mock_mode", config["mock_mode"]))
    for provider, fields in {"doubao": ("app_id", "access_token", "api_key"), "minimax": ("api_key",)}.items():
        for field in fields:
            value = incoming.get(provider, {}).get(field)
            if value not in (None, "", "••••••••"):
                config[provider][field] = str(value).strip()
    save_config(config)
    return jsonify({"success": True, **public_config(config)})


@app.post("/api/voices")
def voice_add():
    incoming = request.get_json(force=True) or {}
    voice = normalize_voice_entry(incoming)
    if not voice:
        return jsonify({"success": False, "error": "请填写服务商和 Voice ID"}), 400
    config = load_config()
    existing_ids = {item["id"] for item in config["voices"]}
    base_id = voice["id"]
    count = 2
    while voice["id"] in existing_ids:
        voice["id"] = f"{base_id}_{count}"
        count += 1
    config["voices"].append(voice)
    save_config(config)
    return jsonify({"success": True, **public_config(config)})


@app.delete("/api/voices/<voice_id>")
def voice_delete(voice_id):
    config = load_config()
    before = len(config["voices"])
    config["voices"] = [voice for voice in config["voices"] if voice["id"] != voice_id]
    if len(config["voices"]) == before:
        return jsonify({"success": False, "error": "未找到要删除的音色"}), 404
    if not config["voices"]:
        config["voices"] = deep_copy(DEFAULT_CONFIG["voices"])
    save_config(config)
    return jsonify({"success": True, **public_config(config)})


@app.post("/api/import")
def import_sheet():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"success": False, "error": "请选择 Excel 或 CSV 文件"}), 400
    suffix = Path(uploaded.filename or "").suffix.lower()
    rows = []
    if suffix == ".csv":
        text = uploaded.read().decode("utf-8-sig")
        raw_rows = list(csv.DictReader(io.StringIO(text)))
    elif suffix in (".xlsx", ".xlsm"):
        wb = load_workbook(io.BytesIO(uploaded.read()), read_only=True, data_only=True)
        ws = wb.active
        values = list(ws.iter_rows(values_only=True))
        if not values:
            raw_rows = []
        else:
            header_index = next(
                (
                    i for i, row in enumerate(values[:12])
                    if "文件名" in {str(v or "").strip() for v in row}
                    and "语音文字" in {str(v or "").strip() for v in row}
                ),
                0,
            )
            headers = [str(v or "").strip() for v in values[header_index]]
            raw_rows = [dict(zip(headers, row)) for row in values[header_index + 1:]]
    else:
        return jsonify({"success": False, "error": "仅支持 .xlsx 和 .csv 文件"}), 400
    aliases = {
        "filename": ("文件名", "filename", "name"), "text": ("语音文字", "文本", "text"),
        "voice": ("音色", "voice"), "emotion": ("情绪", "emotion"),
        "instruction": ("语气指令", "指令", "instruction"), "speed": ("语速", "speed"),
        "volume": ("音量", "volume", "vol"),
    }
    for index, raw in enumerate(raw_rows, start=1):
        normalized = {}
        for target, names in aliases.items():
            normalized[target] = next((raw.get(name) for name in names if raw.get(name) not in (None, "")), "")
        if not str(normalized["text"]).strip():
            continue
        try:
            speed = float(normalized["speed"]) if normalized["speed"] != "" else None
        except (TypeError, ValueError):
            speed = None
        try:
            volume = float(normalized["volume"]) if normalized["volume"] != "" else None
        except (TypeError, ValueError):
            volume = None
        rows.append({
            "client_id": uuid.uuid4().hex,
            "filename": safe_name(normalized["filename"], f"voice_{index:03d}"),
            "text": str(normalized["text"]).strip(),
            "voice": str(normalized["voice"]).strip(),
            "emotion": str(normalized["emotion"]).strip(),
            "instruction": str(normalized["instruction"]).strip(),
            "speed": speed,
            "volume": volume,
        })
    return jsonify({"success": True, "rows": rows})


@app.get("/api/template")
def template_download():
    output = build_template_workbook()
    return send_file(output, as_attachment=True, download_name="AI语音批量生成模板.xlsx")


def build_template_workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = "批量语音"
    ws.append(["文件名", "语音文字", "音色", "情绪", "语气指令", "语速", "音量"])
    ws.append(["chapter01_orin", "欢迎来到新的故事。", "", "", "", "", ""])
    ws.append(["chapter01_hagrid", "快跟我来，我们要迟到了！", "阳光阿辰", "兴奋", "急切但友好", 1.0, DEFAULT_VOLUME])
    ws.freeze_panes = "A2"
    for cell in ws[1]:
        font = copy.copy(cell.font)
        font.bold = True
        cell.font = font
    widths = [24, 56, 28, 16, 32, 12, 12]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = width
    config = load_config()
    voice_names = [voice["name"] for voice in config["voices"]]
    validations = {
        "C2:C300": voice_names,
        "D2:D300": EMOTION_OPTIONS,
        "F2:F300": SPEED_OPTIONS,
        "G2:G300": VOLUME_OPTIONS,
    }
    for range_ref, values in validations.items():
        formula = '"' + ",".join(values) + '"'
        validation = DataValidation(type="list", formula1=formula, allow_blank=True)
        validation.error = "请从下拉选项中选择，或留空使用网页默认值。"
        validation.errorTitle = "参数选项"
        ws.add_data_validation(validation)
        validation.add(range_ref)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


@app.post("/api/generate")
def generate():
    payload = request.get_json(force=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"success": False, "error": "语音文字不能为空"}), 400
    if len(text) > 10000:
        return jsonify({"success": False, "error": "单条文字不能超过 10000 字符"}), 400
    config = load_config()
    voice = get_voice(config, payload.get("voice_id"))
    if not voice:
        return jsonify({"success": False, "error": "未找到所选音色"}), 400
    speed = max(0.5, min(2.0, float(payload.get("speed") or 1.0)))
    volume = max(0.1, min(10.0, float(payload.get("volume") or DEFAULT_VOLUME)))
    try:
        if config["mock_mode"]:
            audio, mime, ext = make_mock_wav(text)
        elif voice["provider"] == "doubao":
            if not public_config(config)["doubao_ready"]:
                raise RuntimeError("请先在接口配置中填写豆包 App ID 和 Access Token")
            audio, mime, ext = synthesize_doubao(config, text, voice, speed, str(payload.get("emotion", "")), str(payload.get("instruction", "")), volume)
        else:
            if not public_config(config)["minimax_ready"]:
                raise RuntimeError("请先在接口配置中填写 MiniMax API Key")
            audio, mime, ext = synthesize_minimax(
                config, text, voice, speed, str(payload.get("emotion", "")), volume,
                normalize_minimax_options(payload.get("advanced")),
            )
        validate_audio_bytes(audio, mime, "模拟模式" if config["mock_mode"] else voice["provider"])
        audio_id = uuid.uuid4().hex
        path = AUDIO_DIR / f"{audio_id}.{ext}"
        path.write_bytes(audio)
        meta = {"id": audio_id, "filename": safe_name(payload.get("filename"), "voice"), "ext": ext, "mime": mime}
        (AUDIO_DIR / f"{audio_id}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return jsonify({"success": True, "audio_id": audio_id, "audio_url": f"/api/audio/{audio_id}", "ext": ext, "mock": config["mock_mode"]})
    except requests.RequestException as exc:
        return jsonify({"success": False, "error": f"接口连接失败：{exc}"}), 502
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


def audio_meta(audio_id):
    if not re.fullmatch(r"[a-f0-9]{32}", audio_id or ""):
        return None
    meta_path = AUDIO_DIR / f"{audio_id}.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


@app.get("/api/audio/<audio_id>")
def audio_get(audio_id):
    meta = audio_meta(audio_id)
    if not meta:
        return jsonify({"error": "音频不存在"}), 404
    path = AUDIO_DIR / f"{audio_id}.{meta['ext']}"
    return send_file(path, mimetype=meta["mime"], as_attachment=request.args.get("download") == "1", download_name=f"{meta['filename']}.{meta['ext']}")


@app.post("/api/download")
def download_selected():
    ids = (request.get_json(force=True) or {}).get("audio_ids", [])
    output = io.BytesIO()
    used = set()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for audio_id in ids:
            meta = audio_meta(audio_id)
            if not meta:
                continue
            base = safe_name(meta["filename"])
            candidate = f"{base}.{meta['ext']}"
            count = 2
            while candidate.lower() in used:
                candidate = f"{base}_{count}.{meta['ext']}"
                count += 1
            used.add(candidate.lower())
            archive.write(AUDIO_DIR / f"{audio_id}.{meta['ext']}", candidate)
    if not used:
        return jsonify({"success": False, "error": "没有可下载的音频"}), 400
    output.seek(0)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(output, mimetype="application/zip", as_attachment=True, download_name=f"AI语音_{stamp}.zip")



@app.post("/api/clone/status")
def clone_status():
    config = load_config()
    data = request.get_json() or {}
    speaker = str(data.get("speaker_id", ""))
    if not re.fullmatch(r"S_[A-Za-z0-9_]+", speaker) or not config["doubao"].get("api_key"):
        return jsonify(error="请填写音色 ID 并配置豆包 API Key"), 400
    try:
        r = requests.post("https://openspeech.bytedance.com/api/v3/tts/get_voice", headers={"X-Api-Key": config["doubao"]["api_key"], "X-Api-Request-Id": str(uuid.uuid4())}, json={"speaker_id": speaker}, timeout=60)
        r.raise_for_status()
        result = r.json()
        if result.get("status") not in (2, 4):
            return jsonify(error="音色尚不可用，当前状态：" + str(result.get("status"))), 400
        voice = normalize_voice_entry({"provider": "doubao", "voice_id": speaker, "name": data.get("name") or speaker, "model": "seed-icl-2.0"})
        config["voices"] = [v for v in config["voices"] if not (v["provider"] == "doubao" and v["voice_id"] == speaker)] + [voice]
        save_config(config)
        return jsonify(public_config(config))
    except (requests.RequestException, ValueError):
        return jsonify(error="查询失败，请检查豆包密钥和音色权限"), 400

@app.post("/api/clone")
def clone_voice():
    config = load_config()
    if config["mock_mode"]:
        return jsonify(error="请先在设置中关闭模拟模式并配置 MiniMax API Key"), 400
    provider = request.form.get("provider", "minimax")
    if provider not in ("doubao", "minimax"):
        return jsonify(error="不支持的接口"), 400
    key = config[provider].get("api_key")
    if not key or request.form.get("consent") != "yes":
        return jsonify(error="请配置 MiniMax 密钥，并确认拥有声音使用授权"), 400
    name = request.form.get("name", "").strip()
    upload = request.files.get("audio")
    if not name or not upload:
        return jsonify(error="请输入音色名称并上传音频"), 400
    try:
        audio = upload.read()
        with wave.open(io.BytesIO(audio)) as w:
            duration = w.getnframes() / w.getframerate()
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or not 10 <= duration <= 300:
                raise ValueError("素材须为单声道 WAV，合计 10 秒至 5 分钟")
        if len(audio) > 20 * 1024 * 1024:
            raise ValueError("合并后的素材不能超过 20 MB")
        if provider == "doubao":
            speaker = request.form.get("speaker_id", "").strip()
            if not re.fullmatch(r"S_[A-Za-z0-9_]+", speaker):
                raise ValueError("请输入控制台中的预付费 S_ 音色 ID")
            if len(audio) > 10 * 1024 * 1024:
                raise ValueError("豆包素材最大10MB，请缩短录音")
            headers = {"X-Api-Key": key, "X-Api-Request-Id": str(uuid.uuid4())}
            response = requests.post("https://openspeech.bytedance.com/api/v3/tts/voice_clone", headers=headers,
                json={"speaker_id": speaker, "audio": {"data": base64.b64encode(audio).decode(), "format": "wav"}, "language": int(request.form.get("language", "0"))}, timeout=180)
            response.raise_for_status()
            result = response.json()
            if result.get("code", 0) != 0:
                raise ValueError(str(result.get("message", "豆包复刻失败")))
            if result.get("status") not in (2, 4):
                return jsonify(error="豆包尚未完成训练，请稍后使用“查询豆包状态”按钮，不要重复复刻。"), 400
            voice = normalize_voice_entry({"name": name, "provider": "doubao", "voice_id": speaker, "model": "seed-icl-2.0"})
            config = load_config()
            config["voices"] = [v for v in config["voices"] if not (v["provider"] == "doubao" and v["voice_id"] == speaker)] + [voice]
            save_config(config)
            return jsonify(public_config(config))
        headers = {"Authorization": "Bearer " + key}
        def checked(response):
            response.raise_for_status()
            result = response.json()
            if result.get("base_resp", {}).get("status_code", -1) != 0:
                raise ValueError("MiniMax：" + str(result.get("base_resp", {}).get("status_msg", "接口失败")))
            return result
        # 高级选项全部可留空；留空时与旧版行为一致（随机 voice_id、开启降噪与音量归一化、不试听）
        voice_id = request.form.get("custom_voice_id", "").strip()
        if voice_id and not VOICE_ID_RULE.fullmatch(voice_id):
            raise ValueError("自定义 voice_id 需 8～256 位：字母开头，只含字母、数字、-、_，且不能以 - 或 _ 结尾")
        if voice_id and any(v["provider"] == "minimax" and v["voice_id"] == voice_id for v in config["voices"]):
            raise ValueError("这个 voice_id 已在音色列表中，请换一个名字")
        voice_id = voice_id or "Clone" + uuid.uuid4().hex
        clone_payload = {
            "voice_id": voice_id,
            "need_noise_reduction": request.form.get("noise_reduction", "yes") != "no",
            "need_volume_normalization": request.form.get("volume_normalization", "yes") != "no",
        }
        preview_text = request.form.get("preview_text", "").strip()
        if len(preview_text) > 300:
            raise ValueError("试听文字请控制在 300 字以内")
        prompt_upload = request.files.get("prompt_audio")
        prompt_text = request.form.get("prompt_text", "").strip()
        prompt_audio = prompt_upload.read() if prompt_upload else b""
        if prompt_audio:
            if not prompt_text:
                raise ValueError("使用示例音频时，请填写它对应的文字")
            with wave.open(io.BytesIO(prompt_audio)) as w:
                if w.getnframes() / w.getframerate() >= 8:
                    raise ValueError("示例音频需短于 8 秒")
        result = checked(requests.post("https://api.minimax.cn/v1/files/upload", headers=headers,
            data={"purpose": "voice_clone"}, files={"file": ("samples.wav", audio, "audio/wav")}, timeout=120))
        clone_payload["file_id"] = int(result["file"]["file_id"])
        if prompt_audio:
            prompt_result = checked(requests.post("https://api.minimax.cn/v1/files/upload", headers=headers,
                data={"purpose": "prompt_audio"}, files={"file": ("prompt.wav", prompt_audio, "audio/wav")}, timeout=120))
            clone_payload["clone_prompt"] = {"prompt_audio": int(prompt_result["file"]["file_id"]), "prompt_text": prompt_text}
        if preview_text:
            clone_payload["text"] = preview_text
            clone_payload["model"] = "speech-2.8-hd"
        clone_result = checked(requests.post("https://api.minimax.cn/v1/voice_clone", headers=headers, json=clone_payload, timeout=180))
        voice = normalize_voice_entry({"name": name, "provider": "minimax", "voice_id": voice_id, "model": "speech-2.8-hd"})
        config = load_config()
        config["voices"].append(voice)
        save_config(config)
        return jsonify({**public_config(config), "voice_id": voice_id, "demo_audio": str(clone_result.get("demo_audio") or "")})
    except (ValueError, KeyError, wave.Error) as exc:
        return jsonify(error=str(exc)), 400
    except requests.RequestException:
        return jsonify(error="接口请求失败，请检查密钥、权限、余额及网络；请求可能已提交，请先核查控制台，避免重复扣费。"), 400

if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    port = int(os.environ.get("VOICE_STUDIO_PORT", "8765"))
    Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
