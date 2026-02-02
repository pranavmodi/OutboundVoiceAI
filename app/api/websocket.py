"""WebSocket handlers for real-time voice and dashboard updates."""
import asyncio
import json
import base64
import logging
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.call_orchestrator import get_orchestrator
from app.services.dispatcher import get_dispatcher
from app.providers import get_queue_provider, get_call_log_provider
from app.models import CallOutcome

logger = logging.getLogger(__name__)

router = APIRouter()


# Connected dashboard clients for broadcasting updates
dashboard_clients: Set[WebSocket] = set()


async def broadcast_to_dashboards(message: dict):
    """Broadcast a message to all connected dashboard clients."""
    if not dashboard_clients:
        return

    message_str = json.dumps(message)
    disconnected = set()

    for client in dashboard_clients:
        try:
            await client.send_text(message_str)
        except Exception:
            disconnected.add(client)

    # Remove disconnected clients
    dashboard_clients.difference_update(disconnected)


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket endpoint for dashboard real-time updates."""
    await websocket.accept()
    dashboard_clients.add(websocket)

    try:
        # Send initial state
        queue_provider = get_queue_provider()
        call_log_provider = get_call_log_provider()

        active_call = await call_log_provider.get_active_call()
        statistics = await call_log_provider.get_statistics()

        await websocket.send_json({
            "type": "initial_state",
            "queue_state": queue_provider.get_state().to_dict(),
            "active_call": active_call.to_dict() if active_call else None,
            "statistics": statistics,
        })

        # Keep connection alive and handle any incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                message = json.loads(data)

                # Handle ping/pong for keepalive
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    finally:
        dashboard_clients.discard(websocket)


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """WebSocket endpoint for voice call audio streaming."""
    await websocket.accept()

    orchestrator = get_orchestrator()
    audio_buffer = bytearray()

    # Set up callbacks to forward to WebSocket
    async def on_call_started(call):
        await websocket.send_json({
            "type": "call_started",
            "call": call.to_dict(),
        })
        await broadcast_to_dashboards({
            "type": "call_started",
            "call": call.to_dict(),
        })
        get_dispatcher().notify_call_started(call.patient_id)

    async def on_call_ended(call):
        await websocket.send_json({
            "type": "call_ended",
            "call": call.to_dict(),
        })
        await broadcast_to_dashboards({
            "type": "call_ended",
            "call": call.to_dict(),
        })
        get_dispatcher().notify_call_ended()

    async def on_transcript_update(speaker, text):
        await websocket.send_json({
            "type": "transcript",
            "speaker": speaker,
            "text": text,
        })
        # Only broadcast complete transcripts to dashboard
        if speaker in ("ai", "patient"):
            await broadcast_to_dashboards({
                "type": "transcript",
                "speaker": speaker,
                "text": text,
            })

    async def on_audio_output(audio_data):
        # Send audio as base64
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        await websocket.send_json({
            "type": "audio",
            "data": audio_b64,
        })

    async def on_status_update(status):
        await websocket.send_json({
            "type": "status",
            "status": status,
        })
        await broadcast_to_dashboards({
            "type": "status_update",
            "status": status,
        })

    async def on_error(error):
        await websocket.send_json({
            "type": "error",
            "message": error,
        })

    # Attach callbacks
    orchestrator.on_call_started = on_call_started
    orchestrator.on_call_ended = on_call_ended
    orchestrator.on_transcript_update = on_transcript_update
    orchestrator.on_audio_output = on_audio_output
    orchestrator.on_status_update = on_status_update
    orchestrator.on_error = on_error

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                if msg_type == "start_call":
                    patient_id = data.get("patient_id")
                    call_mode = data.get("call_mode", "web")
                    if patient_id:
                        await orchestrator.start_call(patient_id, call_mode=call_mode)

                elif msg_type == "end_call":
                    outcome_str = data.get("outcome", "completed")
                    try:
                        outcome = CallOutcome(outcome_str)
                    except ValueError:
                        outcome = CallOutcome.COMPLETED
                    await orchestrator.end_call(outcome)

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

            elif "bytes" in message:
                # Binary audio data from browser
                audio_data = message["bytes"]
                if not hasattr(voice_websocket, '_audio_received_logged'):
                    voice_websocket._audio_received_logged = True
                    print(f"[WebSocket] Received audio from browser: {len(audio_data)} bytes")
                await orchestrator.send_audio(audio_data)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Clean up callbacks
        orchestrator.on_call_started = None
        orchestrator.on_call_ended = None
        orchestrator.on_transcript_update = None
        orchestrator.on_audio_output = None
        orchestrator.on_status_update = None
        orchestrator.on_error = None

        # End any active call
        if orchestrator.is_call_active:
            await orchestrator.end_call(CallOutcome.FAILED)


@router.websocket("/ws/twilio-media/{stream_id}")
async def twilio_media_websocket(websocket: WebSocket, stream_id: str):
    """WebSocket endpoint for Twilio media streams.

    Twilio connects here after our TwiML <Connect><Stream> instruction.
    We bridge the audio to/from the OpenAI RealtimeVoiceService.
    """
    from app.services.twilio_voice_service import pop_bridge

    await websocket.accept()
    logger.info(f"Twilio media stream connected: stream_id={stream_id}")

    bridge = pop_bridge(stream_id)
    if not bridge:
        logger.error(f"No pending bridge for stream_id={stream_id}")
        await websocket.close(code=4000, reason="No pending bridge")
        return

    try:
        await bridge.handle_twilio_ws(websocket)
    except WebSocketDisconnect:
        logger.info(f"Twilio media stream disconnected: stream_id={stream_id}")
    except Exception as e:
        logger.error(f"Twilio media stream error: {e}")
