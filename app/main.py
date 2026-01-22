import os
from fastapi import FastAPI, Request, Query, HTTPException, Form
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from twilio.twiml.voice_response import VoiceResponse
from twilio.base.exceptions import TwilioRestException

from .tts import generate_tts_mp3, generate_ai_audio, generate_ai_response_audio
from .llm import generate_ai_reply
from .twilio_call import place_outbound_call
from .api import dashboard_router, websocket_router, settings_router

app = FastAPI(title="AI Outbound Voice Orchestrator", version="0.2.0")

# CORS middleware for frontend
# - Configure CORS_ORIGINS env var (comma-separated) to specify explicit origins
# - Optionally configure CORS_ORIGIN_REGEX to allow a regex (e.g., local LAN IPs)
_default_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_cors_origins = os.getenv("CORS_ORIGINS")
_origin_regex_env = os.getenv("CORS_ORIGIN_REGEX")
if _cors_origins:
    _allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
else:
    _allowed_origins = _default_origins
_default_origin_regex = r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$"
_allow_origin_regex = _origin_regex_env.strip() if _origin_regex_env else _default_origin_regex

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fallback OPTIONS handler to ensure permissive preflight responses
@app.options("/{rest_of_path:path}")
def options_fallback(rest_of_path: str, request: Request):
    origin = request.headers.get("origin")
    acr_headers = request.headers.get("access-control-request-headers")
    response = Response(status_code=204)
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = acr_headers or "*"
    response.headers["Access-Control-Max-Age"] = "600"
    return response

# Include API routers
app.include_router(dashboard_router)
app.include_router(websocket_router)
app.include_router(settings_router)

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

if __name__ == "__main__":
    # Simulation entrypoint
    import os
    from .call_provider.factory import get_call_provider
    provider = get_call_provider()
    if os.getenv("CALL_PROVIDER", "twilio").lower() == "simulator":
        provider.start_call()
    else:
        print("This module defines the FastAPI app. Run with uvicorn for HTTP server.")

