import re, os

SAMPLE_RATE = 16000
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(_ROOT, ".tmp")
os.makedirs(WORK_DIR, exist_ok=True)

GRAY  = "\033[38;5;242m"
DIM   = "\033[38;5;237m"
WHITE = "\033[97m"
RESET = "\033[0m"

WHISPER_HALLUCINATIONS = {
    "thank you", "thanks for watching", "subscribe",
    "you", "the end", "bye", "music", "applause",
}
HALLUCINATION_RE = re.compile(r'(\b\w+\b)(?:\s*\.\s*\1){3,}')

SPEAKER_GAP = 0.5

# Display layer — short, per-clause
DISPLAY_MAX = 120       # force display line break

# Translation layer — per-sentence, longer
TR_SENTENCE_MIN = 60    # min chars before sentence-end triggers translation
TR_SENTENCE_MAX = 180   # force translation send

SILENCE_WAIT_MAX = 2
PITCH_CHANGE = 0.25
RECORDS_MAX = 50
