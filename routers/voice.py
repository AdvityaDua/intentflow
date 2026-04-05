"""
IntentFlow — Voice Router (Whisper STT).
Accepts audio uploads, transcribes via faster-whisper, and optionally auto-submits as tickets.
"""

import io
import logging
import tempfile
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth import get_current_user
from config import get_settings
from database import User, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice"])

settings = get_settings()

_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            model_size = settings.WHISPER_MODEL
            logger.info(f"Loading Whisper model: {model_size}")
            _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.warning("faster-whisper not installed, voice transcription unavailable")
            raise HTTPException(
                status_code=503,
                detail="Voice transcription not available — faster-whisper not installed",
            )
    return _whisper_model


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Transcribe an audio file (WAV, MP3, WebM, OGG) to text using Whisper.
    """
    allowed = {"audio/wav", "audio/mpeg", "audio/mp3", "audio/webm", "audio/ogg",
               "audio/x-wav", "audio/wave", "video/webm", "application/octet-stream"}

    content_type = file.content_type or "application/octet-stream"
    if content_type not in allowed and not file.filename.endswith((".wav", ".mp3", ".webm", ".ogg", ".m4a")):
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {content_type}")

    # Save to temp file (Whisper needs file path)
    audio_bytes = await file.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")
    if len(audio_bytes) > 25 * 1024 * 1024:  # 25MB
        raise HTTPException(status_code=400, detail="Audio file too large (max 25MB)")

    ext = os.path.splitext(file.filename or ".wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_whisper()
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments).strip()

        if not text:
            text = "[No speech detected]"

        return {
            "transcription": text,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration_seconds": round(info.duration, 2),
        }
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("/submit")
async def voice_submit(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Transcribe audio AND auto-submit as a ticket in one step.
    Returns both the transcription and the ticket result.
    """
    # Transcribe first
    audio_bytes = await file.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")

    ext = os.path.splitext(file.filename or ".wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_whisper()
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not text or text == "[No speech detected]":
        raise HTTPException(status_code=400, detail="Could not detect speech in the audio")

    # Now create ticket through the normal pipeline
    import uuid
    from orchestration.pipeline import run_pipeline
    from memory.session_memory import get_session_history, store_turn
    from database import Ticket

    sess_id = session_id or f"sess-{uuid.uuid4().hex[:10]}"

    ticket = Ticket(
        user_id=current_user.id,
        session_id=sess_id,
        original_query=text,
        transcribed_from_voice=True,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    session_history = get_session_history(sess_id)
    ticket = await run_pipeline(ticket, session_history, db)

    store_turn(sess_id, "user", f"[VOICE] {text}")

    return {
        "transcription": text,
        "language": info.language,
        "ticket_id": ticket.id,
        "status": ticket.status,
        "mode": ticket.mode,
        "intent": ticket.intent,
        "priority": ticket.priority,
        "confidence": ticket.confidence,
        "empathy_response": ticket.empathy_response,
        "session_id": sess_id,
    }
