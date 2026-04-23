"""Generate static voice preview samples for OpenAI and Gemini voices.

Run once to populate frontend/public/voices/ with MP3 files.
Requires OPENAI_API_KEY and GEMINI_API_KEY in .env.

Usage:
    .venv/bin/python scripts/generate_voice_samples.py
"""
import asyncio
import base64
import json
import os
import struct
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OUTPUT_DIR = ROOT / "frontend" / "public" / "voices"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PREVIEW_TEXT = (
    "Hi, this is Ashley with Precise Imaging. "
    "We received your doctor's imaging order and need to schedule your appointment. "
    "Are you available now?"
)

OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"]
GEMINI_VOICES = ["Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Perseus", "Zephyr"]


def generate_openai_samples():
    """Generate MP3 samples using OpenAI TTS API."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("OPENAI_API_KEY not set, skipping OpenAI voices")
        return

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    for voice in OPENAI_VOICES:
        out_path = OUTPUT_DIR / f"openai-{voice}.mp3"
        if out_path.exists():
            print(f"  skip {out_path.name} (exists)")
            continue
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=PREVIEW_TEXT,
                response_format="mp3",
            )
            response.stream_to_file(str(out_path))
            size_kb = out_path.stat().st_size / 1024
            print(f"  OK {out_path.name} ({size_kb:.0f}KB)")
        except Exception as e:
            print(f"  FAIL {voice}: {e}")


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM16 in a WAV header."""
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, channels,
        sample_rate, sample_rate * channels * sample_width,
        channels * sample_width, sample_width * 8,
        b"data", data_size,
    )
    return header + pcm_data


async def generate_gemini_samples():
    """Generate WAV samples using Gemini Live API."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY not set, skipping Gemini voices")
        return

    try:
        from google import genai
    except ImportError:
        print("google-genai not installed, trying REST fallback")
        await _generate_gemini_samples_rest(api_key)
        return

    client = genai.Client(api_key=api_key)

    for voice in GEMINI_VOICES:
        out_path = OUTPUT_DIR / f"gemini-{voice.lower()}.wav"
        if out_path.exists():
            print(f"  skip {out_path.name} (exists)")
            continue
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=PREVIEW_TEXT,
                config=genai.types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=genai.types.SpeechConfig(
                        voice_config=genai.types.VoiceConfig(
                            prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                                voice_name=voice,
                            )
                        )
                    ),
                ),
            )
            audio_data = response.candidates[0].content.parts[0].inline_data.data
            wav_bytes = pcm_to_wav(audio_data, sample_rate=24000)
            out_path.write_bytes(wav_bytes)
            size_kb = out_path.stat().st_size / 1024
            print(f"  OK {out_path.name} ({size_kb:.0f}KB)")
        except Exception as e:
            print(f"  FAIL {voice}: {e}")


async def _generate_gemini_samples_rest(api_key: str):
    """Fallback: use Gemini REST API directly if google-genai SDK not available."""
    import httpx

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={api_key}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for voice in GEMINI_VOICES:
            out_path = OUTPUT_DIR / f"gemini-{voice.lower()}.wav"
            if out_path.exists():
                print(f"  skip {out_path.name} (exists)")
                continue
            body = {
                "contents": [{"parts": [{"text": PREVIEW_TEXT}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": voice}
                        }
                    },
                },
            }
            try:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                data = resp.json()
                audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
                pcm_data = base64.b64decode(audio_b64)
                wav_bytes = pcm_to_wav(pcm_data, sample_rate=24000)
                out_path.write_bytes(wav_bytes)
                size_kb = out_path.stat().st_size / 1024
                print(f"  OK {out_path.name} ({size_kb:.0f}KB)")
            except Exception as e:
                print(f"  FAIL {voice}: {e}")


def main():
    print("Generating OpenAI voice samples...")
    generate_openai_samples()
    print("\nGenerating Gemini voice samples...")
    asyncio.run(generate_gemini_samples())
    print(f"\nDone. Files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
