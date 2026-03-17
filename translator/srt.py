from .constants import RECORDS_MAX

_records = []
_srt_index = 0
_log_file = None


def init_srt(path):
    global _log_file
    _log_file = path
    open(path, "w", encoding="utf-8").close()


def get_log_file():
    return _log_file


def save_record(en, cn, ts):
    global _srt_index
    _records.append((en, cn, ts))
    if len(_records) > RECORDS_MAX:
        _records.pop(0)
    if not _log_file:
        return
    try:
        _srt_index += 1
        h, m, s = (int(x) for x in ts.split(":"))
        s2 = s + 5
        m2, s2 = m + s2 // 60, s2 % 60
        h2, m2 = h + m2 // 60, m2 % 60
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(f"{_srt_index}\n{ts},000 --> {h2:02d}:{m2:02d}:{s2:02d},000\n{en}\n{cn}\n\n")
    except Exception:
        pass
