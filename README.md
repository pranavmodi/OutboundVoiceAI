# AI Outbound Voice Orchestrator

AI-powered outbound calling system for scheduling, with mock external systems and a real-time voice dashboard.

## Features

- **Mock External Systems**: Simulated FreePBX queue status, patient database, and call logs
- **OpenAI Realtime API**: Real-time voice conversations with AI
- **Web Dashboard**: View queue status, patient queue, active calls, and call history
- **Browser Voice Interface**: Speak as the patient using your microphone

## Architecture

```
┌─────────────────────┐     WebSocket      ┌─────────────────────┐
│   Next.js Frontend  │◄──────────────────►│   FastAPI Backend   │
│   (Dashboard + UI)  │                    │   (Orchestrator)    │
└─────────────────────┘                    └──────────┬──────────┘
                                                      │
                                                      │ WebSocket
                                                      ▼
                                           ┌─────────────────────┐
                                           │  OpenAI Realtime    │
                                           │  API (Voice AI)     │
                                           └─────────────────────┘
```

## Quick Start

### 1. Backend Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file with your OpenAI API key
echo "OPENAI_API_KEY=sk-your-key-here" > .env

# Start the backend server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

### 3. Open the Dashboard

Open http://localhost:3000 in your browser.

## Using the Dashboard

### Queue Status Panel
- Shows simulated FreePBX queue status (agents available, calls waiting, etc.)
- **Outbound Allowed** indicator shows if conditions are met for outbound calls
- Use simulation buttons to test different scenarios:
  - **Quiet Queue**: Low traffic, outbound allowed
  - **Busy Queue**: High traffic, outbound blocked
  - **AMI Failure**: Simulate connection loss

### Patient Queue Panel
- Lists patients eligible for outbound calling
- Sorted by priority bucket (1-4)
- Click **Call** to start an AI call to that patient

### Active Call Panel
- Shows when a call is in progress
- **Live Transcript**: Real-time conversation display
- **Mic Controls**: Toggle your microphone to speak as the patient
- **End Call**: Terminate the current call

### Call History Panel
- View past calls with outcomes
- Click a call to see full transcript and details

## How Voice Calls Work

1. Click **Connect Voice** in the header to establish WebSocket connection
2. Select a patient and click **Call**
3. The AI will greet the patient (audio plays through your speakers)
4. Click the mic button and speak as the patient
5. The AI responds in real-time
6. The conversation continues until the AI determines the outcome (transfer, callback, etc.)

## Environment Variables

### Backend (.env)
```
OPENAI_API_KEY=sk-...          # Required for voice AI
TWILIO_ACCOUNT_SID=AC...       # Optional, for real calls
TWILIO_AUTH_TOKEN=...          # Optional, for real calls
TWILIO_FROM_NUMBER=+1...       # Optional, for real calls
```

### Frontend (frontend/.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## API Endpoints

### Dashboard API
- `GET /api/status` - System status overview
- `GET /api/queue` - Current queue state
- `GET /api/patients` - All patients
- `GET /api/patients/queue` - Outbound-eligible patients (sorted)
- `GET /api/calls` - Call history
- `GET /api/calls/{call_id}` - Specific call details

### Queue Simulation
- `POST /api/queue/simulate/busy` - Simulate busy queue
- `POST /api/queue/simulate/quiet` - Simulate quiet queue
- `POST /api/queue/simulate/ami-failure` - Simulate AMI disconnection
- `POST /api/queue/simulate/ami-recovery` - Restore AMI connection

### WebSocket Endpoints
- `WS /ws/dashboard` - Real-time dashboard updates
- `WS /ws/voice` - Voice call audio streaming

## Project Structure

```
OutboundVoiceAI/
├── app/
│   ├── api/
│   │   ├── dashboard.py      # REST API endpoints
│   │   └── websocket.py      # WebSocket handlers
│   ├── models/
│   │   ├── queue_state.py    # Queue state model
│   │   ├── patient.py        # Patient model
│   │   └── call_log.py       # Call log model
│   ├── providers/
│   │   ├── queue_provider.py    # Mock FreePBX
│   │   ├── patient_provider.py  # Mock patient DB
│   │   └── call_log_provider.py # Call log storage
│   ├── services/
│   │   ├── realtime_voice.py    # OpenAI Realtime API
│   │   └── call_orchestrator.py # Call flow management
│   └── main.py               # FastAPI application
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Main dashboard
│   │   └── layout.tsx        # App layout
│   ├── components/
│   │   ├── dashboard/        # Dashboard components
│   │   └── ui/               # shadcn/ui components
│   ├── hooks/
│   │   ├── useApi.ts         # API client
│   │   ├── useWebSocket.ts   # WebSocket clients
│   │   └── useAudio.ts       # Audio capture/playback
│   └── types/
│       └── index.ts          # TypeScript types
├── docs/
│   ├── requirements.md       # Business requirements
│   ├── implementation-plan.md
│   └── external-systems.md
└── requirements.txt
```

## Mock Data

The system initializes with sample patient data across all priority buckets:

| Priority | Description | Example Patients |
|----------|-------------|------------------|
| 1 | Abandoned + No AI Call | John Smith, Maria Garcia |
| 2 | Abandoned + AI Called | Robert Johnson |
| 3 | No AI Call + Called In | Emily Davis, Wei Zhang |
| 4 | No AI Call + Never Called | Michael Wilson, Sarah Brown |

## Legacy Features

### Twilio Integration (Original POC)
The original Twilio integration is still available for real phone calls:

```bash
# Expose locally with ngrok
ngrok http 8000

# Trigger a test call
export URL="https://<your-ngrok>.ngrok-free.app"
curl -X POST "$URL/call?to=+15551230000&base_url=$URL"
```

### Streamlit Simulator
The original Streamlit-based simulator is still available:

```bash
streamlit run app/ui/voice_call_simulator.py
```

## Known Limitations

- OpenAI Realtime API is in beta and may have availability issues
- Browser microphone requires HTTPS in production (localhost is exempt)
- Mock patient data resets on server restart
- Single concurrent call limit (by design)

## Troubleshooting

### "Voice Disconnected" in dashboard
- Click **Connect Voice** button
- Check browser console for WebSocket errors
- Ensure backend is running on port 8000

### No audio from AI
- Check browser volume and permissions
- Verify OPENAI_API_KEY is set correctly
- Check backend logs for API errors

### Microphone not working
- Allow microphone permission when prompted
- Check browser console for getUserMedia errors
- Try a different browser (Chrome recommended)
