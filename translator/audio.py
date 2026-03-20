import subprocess, sys, json, struct, queue
from .constants import SAMPLE_RATE


def get_video_info(url):
    r = subprocess.run(["yt-dlp", "--dump-json", "--no-download", url],
                       capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}


def get_audio_url(url):
    for fmt in ("bestaudio", "worst", "91", "92", "93"):
        r = subprocess.run(["yt-dlp", "-f", fmt, "-g", url],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    sys.exit("yt-dlp: no audio stream found")


def start_ffmpeg(audio_url):
    return subprocess.Popen([
        "ffmpeg", "-reconnect", "1", "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5", "-i", audio_url,
        "-vn", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE),
        "-ac", "1", "-f", "s16le", "-loglevel", "error", "pipe:1"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def capture_loop(ff, aq, chunk_bytes, silence_thresh=300, check_win=None):
    if check_win is None:
        check_win = SAMPLE_RATE
    while True:
        data = ff.stdout.read(chunk_bytes)
        if not data:
            aq.put((b"", True))
            break
        tail = data[-check_win:] if len(data) >= check_win else data
        samples = struct.unpack(f"<{len(tail)//2}h", tail)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        if aq.full():
            try:
                aq.get_nowait()
            except queue.Empty:
                pass
        aq.put((data, rms < silence_thresh))


def capture_loop_dynamic(ff, aq, silence_thresh=300, stop_fn=None,
                         min_sec=1.5, max_sec=4, window_sec=0.3,
                         silence_flush=0.6):
    """
    Dynamic chunking: read small windows, flush on speech→silence transition.

    - Accumulates audio in small windows (0.3s)
    - During speech: keep buffering up to max_sec
    - Speech→silence detected: flush immediately (low latency)
    - Pure silence: don't flush (wait for speech)
    - Exceeds max_sec: force flush
    """
    bps = SAMPLE_RATE * 2  # bytes per second (16-bit mono)
    win_bytes = int(bps * window_sec)
    min_bytes = int(bps * min_sec)
    max_bytes = int(bps * max_sec)
    silence_wins = int(silence_flush / window_sec)  # consecutive silent windows to trigger flush

    buf = b""
    had_speech = False
    silent_count = 0

    def _rms(data):
        samples = struct.unpack(f"<{len(data)//2}h", data)
        return (sum(s * s for s in samples) / len(samples)) ** 0.5

    def _flush(is_silence):
        nonlocal buf, had_speech, silent_count
        if not buf:
            return
        if aq.full():
            try: aq.get_nowait()
            except queue.Empty: pass
        aq.put((buf, is_silence))
        buf = b""
        had_speech = False
        silent_count = 0

    while True:
        if stop_fn and stop_fn():
            break
        data = ff.stdout.read(win_bytes)
        if not data:
            _flush(True)
            break

        buf += data
        rms = _rms(data)
        is_silent = rms < silence_thresh

        if is_silent:
            silent_count += 1
        else:
            silent_count = 0
            had_speech = True

        # force flush: exceeded max
        if len(buf) >= max_bytes:
            _flush(is_silent)
            continue

        # speech→silence transition: flush if we have enough audio
        if had_speech and silent_count >= silence_wins and len(buf) >= min_bytes:
            _flush(True)
            continue
