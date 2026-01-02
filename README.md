## AI Outbound Voice POC (FastAPI + Twilio + OpenAI TTS)

Minimal proof-of-concept to:
- Place an outbound call with Twilio
- When answered, play AI-generated speech from OpenAI Text-to-Speech
- Run locally with FastAPI and expose via ngrok

### Environment variables via dotenv
This app loads credentials from:
- `.env` (standard) and/or
- `.en` (alternate filename you mentioned)

If both exist, `.en` overrides duplicate keys from `.env`.

Required keys:
```
TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+15551234567
OPENAI_API_KEY=sk-...
# Optional:
PUBLIC_BASE_URL=https://<your-ngrok>.ngrok-free.app
```

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expose locally with ngrok (install and auth once, then run):
```bash
sudo snap install ngrok
ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
ngrok http 8000
```

Trigger a test call (replace `to` and `base_url` with the HTTPS Forwarding URL ngrok prints):
```bash
export URL="https://<your-ngrok>.ngrok-free.app"
curl -X POST "$URL/call?to=+15551230000&base_url=$URL"
```

### Endpoints
- Health: `GET /health` → `ok`
- Trigger call: `GET|POST /call?to=+1...&base_url=https://...`
- Twilio webhook: `GET|POST /voice` → returns TwiML `<Play>` of AI MP3
- AI MP3: `/audio/ai_greeting.mp3`

### STEP 2 (What this proves)
- On call answer, server generates AI speech via OpenAI TTS (once) and stores `app/audio/ai_greeting.mp3`.
- FastAPI serves the audio at `/audio/ai_greeting.mp3`.
- Twilio `<Play>` fetches that public URL (via ngrok) and plays it to the callee.

### STEP 3 (Single-turn response)
- Call flow:
  1) `/voice` plays greeting via `<Play>`
  2) `<Gather input="speech">` listens once
  3) Twilio posts `SpeechResult` to `/process_speech`
  4) Server generates a short AI reply (OpenAI chat), converts to MP3, and returns TwiML `<Play>` for `/audio/ai_response.mp3`
  5) Call ends after playback

Test:
```bash
export URL="https://<your-ngrok>.ngrok-free.app"
curl -i "$URL/voice"                       # should include <Gather>
curl -i -X POST "$URL/call?to=+15551230000&base_url=$URL"
```


