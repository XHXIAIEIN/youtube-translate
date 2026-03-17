import sys, os
from datetime import datetime
from .constants import GRAY, DIM, WHITE, RESET
from .srt import save_record
from .names import annotate


def _w(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def render_loop(out_q):
    en_buffer = []
    in_cn = False
    interim_rows = 0
    has_output = False  # track if any EN+CN pair has been printed

    def erase_interim():
        nonlocal interim_rows
        for _ in range(interim_rows):
            _w("\033[A\033[2K")
        interim_rows = 0

    def calc_rows(text, ts):
        cols = os.get_terminal_size().columns
        return max(1, -(-(len(text) + len(ts) + 1) // cols))

    def print_en(text, ts):
        nonlocal has_output
        if has_output:
            _w("\n")  # blank line separator between pairs
        _w(f"{GRAY}{text} {DIM}{ts}{RESET}\n")
        has_output = True

    while True:
        msg = out_q.get()
        if msg is None:
            break

        kind = msg[0]

        if kind == "en_interim":
            if not in_cn:
                _, text, ts = msg
                erase_interim()
                # interim doesn't add pair separator — it's temporary
                _w(f"{GRAY}{text} {DIM}{ts}{RESET}\n")
                interim_rows = calc_rows(text, ts)

        elif kind == "en_final":
            if in_cn:
                en_buffer.append(msg)
            else:
                _, text, ts = msg
                erase_interim()
                print_en(text, ts)

        elif kind == "cn_start":
            erase_interim()
            in_cn = True
            _w("\033[s")  # save cursor — will rewrite with annotations
            _w(WHITE)

        elif kind == "cn_token":
            _w(msg[1])

        elif kind == "cn_end":
            _, en, cn, ts = msg
            display, clean = annotate(cn)
            # erase streamed text, reprint with name annotations
            _w(f"\033[u\033[J")       # restore cursor + clear to end
            _w(f"{WHITE}{display}{RESET}\n")
            save_record(en, clean, ts)
            in_cn = False

            # flush buffered en_finals
            for _, text, ts2 in en_buffer:
                print_en(text, ts2)
            en_buffer.clear()

        elif kind == "log":
            _w(f"{GRAY}{msg[1]}{RESET}\n")


def print_header(title, channel, is_live, url, provider, model, chunk, srt_path):
    _w(f"\n{WHITE}{title}{RESET}\n")
    meta = [channel] if channel else []
    meta.append("LIVE" if is_live else "video")
    _w(f"{GRAY}{' · '.join(meta)}{RESET}\n")
    _w(f"{GRAY}{url}{RESET}\n")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _w(f"{GRAY}whisper small · {provider}/{model} · {chunk}s · {ts}{RESET}\n")
    _w(f"{GRAY}{srt_path}{RESET}\n")
    cols = os.get_terminal_size().columns
    _w(f"{DIM}{'─' * cols}{RESET}\n\n")
