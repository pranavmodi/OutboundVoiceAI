from fastapi import FastAPI, Request, Query, HTTPException, Form
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from twilio.twiml.voice_response import VoiceResponse
from twilio.base.exceptions import TwilioRestException

from .tts import generate_tts_mp3, generate_ai_audio, generate_ai_response_audio
from .llm import generate_ai_reply
from .twilio_call import place_outbound_call


app = FastAPI(title="AI Outbound Voice POC", version="0.1.0")

# Legacy static (kept for compatibility)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Audio directory under app/
AUDIO_DIR = Path(__file__).resolve().parent / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.post("/call")
@app.get("/call")
def call(
    to: str = Query(..., description="Destination phone number in E.164, e.g. +15551234567"),
    base_url: str = Query(..., description="Public base URL (e.g. your ngrok https URL)"),
):
    """
    Trigger an outbound call. Twilio will request TwiML from {base_url}/voice.
    """
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="base_url must start with http:// or https://")

    twiml_url = base_url.rstrip("/") + "/voice"
    try:
        call_sid = place_outbound_call(to_number=to, twiml_url=twiml_url)
    except TwilioRestException as e:
        # Surface Twilio error clearly to the client
        raise HTTPException(
            status_code=502,
            detail={
                "message": getattr(e, "msg", str(e)),
                "code": getattr(e, "code", "twilio_error"),
                "status": getattr(e, "status", 502),
            },
        )
    return {"status": "initiated", "call_sid": call_sid, "twiml_url": twiml_url}


@app.post("/voice")
@app.get("/voice")
def voice(request: Request):
    """
    Twilio webhook that returns TwiML instructing Twilio to <Play> an AI-generated MP3.
    The MP3 is generated once and cached.
    """
    audio_path = generate_ai_audio(
        "Hello, this is an AI calling you for a test. Thank you."
    )

    # Build absolute URL for the audio file
    base_url = str(request.base_url).rstrip("/")
    audio_url = f"{base_url}/audio/ai_greeting.mp3"

    vr = VoiceResponse()
    vr.play(audio_url)
    action_url = f"{base_url}/process_speech"
    vr.gather(
        input="speech",
        action=action_url,
        method="POST",
        timeout=5,
        speech_timeout="auto",
    )

    xml = str(vr)
    return Response(content=xml, media_type="application/xml")

@app.post("/process_speech")
async def process_speech(
    request: Request,
    SpeechResult: str | None = Form(default=None),
):
    """
    Handle Twilio's speech result (single turn):
    - Read SpeechResult text
    - If empty: play fallback and end
    - Else: get LLM reply, TTS to MP3, play response, then end
    """
    speech_text = (SpeechResult or "").strip()

    base_url = str(request.base_url).rstrip("/")

    if not speech_text:
        fallback_text = "Sorry, I didn't catch that. Goodbye."
        generate_ai_response_audio(fallback_text)
        reply_url = f"{base_url}/audio/ai_response.mp3"
        vr = VoiceResponse()
        vr.play(reply_url)
        return Response(content=str(vr), media_type="application/xml")

    ai_text = generate_ai_reply(speech_text)
    generate_ai_response_audio(ai_text)
    reply_url = f"{base_url}/audio/ai_response.mp3"

    vr = VoiceResponse()
    vr.play(reply_url)
    return Response(content=str(vr), media_type="application/xml")


