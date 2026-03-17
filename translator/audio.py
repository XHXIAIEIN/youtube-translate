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
