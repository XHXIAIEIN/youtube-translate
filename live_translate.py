#!/usr/bin/env python
"""YouTube Live Simultaneous Translator — Entry point."""

import sys, os, re, glob, queue, threading, argparse
from datetime import datetime

from translator import (
    PROVIDERS, resolve_config, translate_stream,
    get_video_info, get_audio_url, start_ffmpeg, capture_loop, capture_loop_dynamic,
    transcribe_loop,
    render_loop, print_header,
    web_render_loop, start_web_server, set_header, check_restart, get_switch_url,
    init_srt,
)
from translator.constants import SAMPLE_RATE, WORK_DIR, GRAY, RESET


def main():
    p = argparse.ArgumentParser(description="YouTube Live Translator")
    p.add_argument("url", help="YouTube video/live URL")
    p.add_argument("--whisper", default="small", help="Whisper model (tiny/small/medium/large-v3)")
    p.add_argument("--provider", default=None, help=f"Preset: {', '.join(PROVIDERS.keys())}")
    p.add_argument("--model", default=None, help="Override provider default model")
    p.add_argument("--api-base", default=None, help="Custom API base URL")
    p.add_argument("--api-key", default=None, help="API key (or env TRANSLATE_API_KEY)")
    p.add_argument("--prompt", default=None, help="Custom system prompt (use \\n for newlines)")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    p.add_argument("--chunk", type=int, default=5, help="Audio chunk seconds")
    p.add_argument("--web", action="store_true", help="Open browser subtitle overlay")
    a = p.parse_args()

    api_key = a.api_key or os.environ.get("TRANSLATE_API_KEY", "")
    raw = a.prompt or os.environ.get("TRANSLATE_PROMPT", None)
    prompt = raw.replace("\\n", "\n") if raw else None
    config = resolve_config(a.provider, a.model, a.api_base, api_key, prompt)
    provider_name = a.provider or "ollama"

    # clear screen
    sys.stdout.write("\033[2J\033[1;1H")
    sys.stdout.write(f"{GRAY}connecting...{RESET}\n")
    sys.stdout.flush()

    # video info
    info = get_video_info(a.url)
    title = info.get("title", "Unknown")
    channel = info.get("channel", info.get("uploader", ""))
    is_live = info.get("is_live", False)
    video_id = info.get("id", "unknown")

    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()

    # cleanup old temp WAVs
    for f in glob.glob(os.path.join(WORK_DIR, "*.wav")):
        try: os.unlink(f)
        except OSError: pass

    # SRT file
    safe = re.sub(r'[^\w\s\-.]', '', re.sub(r'[<>:"/\\|?*]', '', title)).strip()[:50]
    project_root = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(project_root, "log", f"{video_id}_{safe}")
    os.makedirs(log_dir, exist_ok=True)
    srt_path = os.path.join(log_dir, f"{datetime.now():%Y%m%d_%H%M%S}.srt")
    init_srt(srt_path)

    # header
    print_header(title, channel, is_live, a.url, provider_name, config.get("model", ""), a.chunk, srt_path)

    # web mode — start server once (persists across restarts)
    if a.web:
        start_web_server()
        set_header(title, channel, is_live, a.url, provider_name, config.get("model", ""), a.chunk, srt_path)

    # ── Pipeline loop: soft-restart reconnects stream, keeps Whisper ──
    out_q = queue.Queue()
    aq = queue.Queue(maxsize=3)
    tq = queue.Queue(maxsize=5)

    # start persistent workers (Whisper + translate + render — survive restarts)
    def _translate_loop():
        last = ""
        while True:
            item = tq.get()
            if item is None:
                continue  # sentinel from restart, keep running
            txt, ts = item
            if txt == last:
                continue
            last = txt
            out_q.put(("cn_start",))
            parts = []
            for token in translate_stream(txt, config):
                t = token.replace("\n", " ")
                parts.append(t)
                out_q.put(("cn_token", t))
            out_q.put(("cn_end", txt, "".join(parts).strip(), ts))

    renderer = web_render_loop if a.web else render_loop
    for fn, args in [
        (renderer, (out_q,)),
        (transcribe_loop, (aq, tq, a.whisper, a.device, out_q)),
        (_translate_loop, ()),
    ]:
        threading.Thread(target=fn, args=args, daemon=True).start()

    # capture loop — restartable, supports URL switching
    current_url = a.url
    while True:
        # check if URL was switched
        new_url = get_switch_url()
        if new_url:
            current_url = new_url
            out_q.put(("log", "switching stream..."))
            info = get_video_info(current_url)
            title = info.get("title", "Unknown")
            channel = info.get("channel", info.get("uploader", ""))
            is_live = info.get("is_live", False)
            if a.web:
                set_header(title, channel, is_live, current_url, provider_name, config.get("model", ""), a.chunk, srt_path)

        audio_url = get_audio_url(current_url)
        ff = start_ffmpeg(audio_url)
        out_q.put(("log", "stream connected"))

        try:
            capture_loop_dynamic(ff, aq, stop_fn=check_restart)
        except KeyboardInterrupt:
            ff.terminate()
            break
        except Exception:
            pass

        ff.terminate()
        out_q.put(("log", "reconnecting..."))

    from translator.srt import get_log_file
    lf = get_log_file()
    if lf:
        sys.stdout.write(f"\n{GRAY}saved to {lf}{RESET}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
