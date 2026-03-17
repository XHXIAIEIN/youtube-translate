"""
Speech-to-text worker with look-ahead buffering.

Uses the HLS buffer delay (3-10s ahead of viewer) to:
1. Look-ahead: use next chunk to fix current chunk's sentence boundaries
2. Pre-translate: send to LLM before display time
3. Better segmentation: 2-chunk window for context-aware splitting
"""

import os, tempfile, wave, re
from datetime import datetime
import numpy as np

from .constants import (
    SAMPLE_RATE, WORK_DIR, WHISPER_HALLUCINATIONS, HALLUCINATION_RE,
    SPEAKER_GAP, TR_SENTENCE_MIN, TR_SENTENCE_MAX,
    SILENCE_WAIT_MAX, PITCH_CHANGE
)

# ── Pitch-based speaker detection ────────────────
_prev_pitch = 0.0


def detect_speaker_change(pcm):
    global _prev_pitch
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if len(samples) < SAMPLE_RATE // 4:
        return False
    mid = len(samples) // 2
    win = SAMPLE_RATE // 2
    c = samples[max(0, mid - win):mid + win]
    c = c - np.mean(c)
    if np.max(np.abs(c)) < 100:
        return False
    c /= np.max(np.abs(c))
    corr = np.correlate(c, c, mode='full')[len(c) - 1:]
    lo, hi = SAMPLE_RATE // 300, SAMPLE_RATE // 50
    if hi >= len(corr):
        return False
    seg = corr[lo:hi]
    if not len(seg):
        return False
    pk = np.argmax(seg) + lo
    if pk == 0 or corr[pk] < 0.2 * corr[0]:
        return False
    pitch = SAMPLE_RATE / pk
    if _prev_pitch == 0:
        _prev_pitch = pitch
        return False
    changed = abs(pitch - _prev_pitch) / _prev_pitch > PITCH_CHANGE
    _prev_pitch = pitch
    return changed


def clean_segment(text):
    text = text.strip()
    while text.endswith('...'):
        text = text[:-3].strip()
    text = text.rstrip('\u2026').strip()
    if not text or len(text) < 2:
        return None
    low = text.lower()
    if low in WHISPER_HALLUCINATIONS or low[0] in "[(" or HALLUCINATION_RE.search(low):
        return None
    if re.search(r'(\b\w+-?\s*){4,}', low) and len(set(low.split())) <= 3:
        return None
    return text


def _ends_sentence(s):
    s = s.rstrip()
    return s and s[-1] in ".!?\"'"


def _find_sentence_break(text):
    """Find a sentence boundary where the first part is long enough to stand alone."""
    for i in range(len(text) - 1):
        if text[i] in '.!?':
            if text[i + 1] == ' ' and i + 2 < len(text) and text[i + 2].isupper():
                first_part = text[:i + 1].strip()
                if len(first_part) >= TR_SENTENCE_MIN:
                    return i + 2
    return -1


# ── Transcribe worker with look-ahead ────────────
def transcribe_loop(aq, tq, whisper_model, device, out_q):
    """
    Look-ahead pipeline:
    1. Transcribe each chunk immediately → show as en_interim (fast)
    2. Hold text in buffer, wait for NEXT chunk's start to confirm sentence boundary
    3. When boundary confirmed → en_final + pre-translate (tq)

    Buffer holds up to 2 chunks of text. When chunk N+1 arrives:
    - If chunk N ended mid-sentence and N+1 continues it → merge
    - If chunk N ended with sentence punctuation → finalize N, start fresh with N+1
    """
    from faster_whisper import WhisperModel

    out_q.put(("log", f"loading whisper {whisper_model}..."))
    ct = "float16" if device == "cuda" else "int8"
    model = WhisperModel(whisper_model, device=device, compute_type=ct)
    out_q.put(("log", "ready\n"))

    buf = ""          # accumulated text
    buf_ts = None     # timestamp of first text in buffer
    prev_chunk_ended_sentence = False  # did the previous chunk end at a sentence boundary?

    def finalize(text=None, ts=None):
        """Send finalized text to display + translation."""
        nonlocal buf, buf_ts
        t = text or buf.strip()
        s = ts or buf_ts or datetime.now().strftime("%H:%M:%S")
        if not t:
            return
        out_q.put(("en_final", t, s))
        tq.put((t, s))
        if text is None:
            buf, buf_ts = "", None

    def try_split_and_finalize():
        """Try to find a sentence boundary in buf and finalize up to it."""
        nonlocal buf, buf_ts
        pos = _find_sentence_break(buf)
        if pos > 0:
            sentence = buf[:pos].strip()
            remainder = buf[pos:].strip()
            ts = buf_ts or datetime.now().strftime("%H:%M:%S")
            if sentence:
                finalize(sentence, ts)
            buf = remainder
            buf_ts = datetime.now().strftime("%H:%M:%S") if remainder else None
            return True
        return False

    while True:
        item = aq.get()
        if item is None or (isinstance(item, tuple) and not item[0]):
            # flush remaining
            if buf.strip():
                finalize()
            break

        audio, is_silence = item
        if not aq.empty():
            continue

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=WORK_DIR)
        try:
            with wave.open(tmp.name, 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio)
            try:
                segs = list(model.transcribe(
                    tmp.name, beam_size=1, best_of=1, language="en",
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 300,
                                     "speech_pad_ms": 150, "threshold": 0.4},
                    condition_on_previous_text=False
                )[0])
            except Exception:
                continue

            if not segs:
                # silence with no speech — finalize only if long enough
                if buf.strip() and len(buf) >= TR_SENTENCE_MIN:
                    finalize()
                continue

            # speaker change → finalize only if sentence looks complete
            if detect_speaker_change(audio) and len(buf) >= TR_SENTENCE_MIN and _ends_sentence(buf):
                finalize()

            # process segments from this chunk
            chunk_text_parts = []
            prev_end = None
            for seg in segs:
                text = clean_segment(seg.text)
                if not text:
                    continue

                # speaker gap within chunk — finalize only if sentence complete
                if prev_end is not None and seg.start - prev_end > SPEAKER_GAP and len(buf) >= TR_SENTENCE_MIN and _ends_sentence(buf):
                    finalize()

                chunk_text_parts.append(text)
                prev_end = seg.end

            if not chunk_text_parts:
                continue

            chunk_text = " ".join(chunk_text_parts)
            ts = datetime.now().strftime("%H:%M:%S")

            # ── Look-ahead logic ──
            # Previous chunk ended at sentence boundary → that was already finalized.
            # Now start fresh with this chunk's text.
            # Previous chunk ended mid-sentence → this chunk's start may complete it.

            if not buf_ts:
                buf_ts = ts
            buf += (" " if buf else "") + chunk_text

            # show interim (full buffer, rewritable)
            out_q.put(("en_interim", buf.strip(), buf_ts))

            # ── Decide what to finalize ──

            # 1. Try to split at sentence boundaries within buf
            while try_split_and_finalize():
                if buf.strip():
                    out_q.put(("en_interim", buf.strip(), buf_ts or ts))

            # 2. Silence detected → only finalize if sentence looks complete
            if is_silence and len(buf) > TR_SENTENCE_MIN and _ends_sentence(buf):
                finalize()
                continue
            # Silence but no sentence end → keep accumulating (look-ahead)
            if is_silence and len(buf) > TR_SENTENCE_MAX:
                finalize()  # too long, force it
                continue

            # 3. Buffer too long → force split at best position or just cut
            if len(buf) > TR_SENTENCE_MAX:
                if not try_split_and_finalize():
                    finalize()  # no good break point, just send it all

        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
