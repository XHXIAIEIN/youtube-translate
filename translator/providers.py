"""
Translation providers — unified interface.
fn(text, api_key, model, api_base, prompt) -> generator[str]
"""

import json, hashlib, random
import requests

DEFAULT_PROMPT = (
    "Simultaneous interpreter. Translate every word from English to Chinese. "
    "Keep person/place/organization names in English. "
    "Partial sentences: translate as-is, include every word. "
    "Output translation only."
)


# ── Base helpers ─────────────────────────────────

def _parse_sse(response, extract_token):
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload.strip() == "[DONE]":
            break
        try:
            token = extract_token(json.loads(payload))
            if token:
                yield token
        except (json.JSONDecodeError, KeyError, IndexError):
            continue


def _post(url, headers, body, **kw):
    return requests.post(url, headers=headers, json=body, timeout=30, stream=True, **kw)


# ── LLM providers ────────────────────────────────

def _ollama(text, api_key, model, api_base, prompt):
    url = api_base or "http://localhost:11434/api/generate"
    r = requests.post(url, json={
        "model": model, "system": prompt, "prompt": text,
        "stream": True, "options": {"temperature": 0.3, "num_predict": 300}
    }, timeout=30, stream=True)
    for line in r.iter_lines():
        if line:
            data = json.loads(line)
            if data.get("response"):
                yield data["response"]
            if data.get("done"):
                break


def _openai_compat(text, api_key, model, api_base, prompt):
    r = _post(f"{api_base}/chat/completions",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        {"model": model, "stream": True, "temperature": 0.3, "max_tokens": 300,
         "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]})

    in_think = False
    for token in _parse_sse(r, lambda d: d["choices"][0]["delta"].get("content")):
        if "<think>" in token:
            in_think = True
            token = token.split("<think>")[0]
            if token:
                yield token
            continue
        if "</think>" in token:
            in_think = False
            token = token.split("</think>")[-1]
            if token:
                yield token
            continue
        if not in_think:
            yield token


def _anthropic(text, api_key, model, api_base, prompt):
    r = _post("https://api.anthropic.com/v1/messages",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        {"model": model, "max_tokens": 300, "system": prompt, "stream": True,
         "messages": [{"role": "user", "content": text}]})
    yield from _parse_sse(r, lambda d: d.get("delta", {}).get("text") if d.get("type") == "content_block_delta" else None)


def _gemini(text, api_key, model, api_base, prompt):
    import time
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
    for attempt in range(3):
        r = requests.post(url, json={
            "system_instruction": {"parts": [{"text": prompt}]},
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300}
        }, timeout=30, stream=True)
        if r.status_code == 429:
            time.sleep(2 * (attempt + 1))
            continue
        yield from _parse_sse(r, lambda d: d["candidates"][0]["content"]["parts"][0].get("text"))
        return
    yield "[限流，稍后重试]"


# ── Traditional translation (prompt ignored) ─────

def _deepl(text, api_key, model, api_base, prompt):
    url = "https://api-free.deepl.com/v2/translate" if api_key.endswith(":fx") else "https://api.deepl.com/v2/translate"
    r = requests.post(url, data={"auth_key": api_key, "text": text, "target_lang": "ZH", "source_lang": "EN"}, timeout=15)
    yield r.json()["translations"][0]["text"]


def _google(text, api_key, model, api_base, prompt):
    r = requests.post(f"https://translation.googleapis.com/language/translate/v2?key={api_key}",
        json={"q": text, "source": "en", "target": "zh-CN", "format": "text"}, timeout=15)
    yield r.json()["data"]["translations"][0]["translatedText"]


def _google_free(text, api_key, model, api_base, prompt):
    r = requests.get("https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text}, timeout=15)
    yield "".join(part[0] for part in r.json()[0] if part[0])


def _microsoft(text, api_key, model, api_base, prompt):
    r = requests.post("https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=en&to=zh-Hans",
        headers={"Ocp-Apim-Subscription-Key": api_key, "Content-Type": "application/json"},
        json=[{"text": text}], timeout=15)
    yield r.json()[0]["translations"][0]["text"]


_edge_token = {"jwt": "", "exp": 0}

def _microsoft_free(text, api_key, model, api_base, prompt):
    import time
    # Refresh token from Edge Translate (valid ~10 min)
    if time.time() > _edge_token["exp"]:
        r = requests.get("https://edge.microsoft.com/translate/auth",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        _edge_token["jwt"] = r.text
        _edge_token["exp"] = time.time() + 500  # refresh before 10min expiry
    r = requests.post("https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=en&to=zh-Hans",
        headers={"Authorization": f"Bearer {_edge_token['jwt']}", "Content-Type": "application/json"},
        json=[{"text": text}], timeout=15)
    yield r.json()[0]["translations"][0]["text"]


def _baidu(text, api_key, model, api_base, prompt):
    appid, secret = api_key.split(":")
    salt = str(random.randint(10000, 99999))
    sign = hashlib.md5(f"{appid}{text}{salt}{secret}".encode()).hexdigest()
    r = requests.get("https://fanyi-api.baidu.com/api/trans/vip/translate",
        params={"q": text, "from": "en", "to": "zh", "appid": appid, "salt": salt, "sign": sign}, timeout=15)
    yield "".join(item["dst"] for item in r.json()["trans_result"])


def _volcano(text, api_key, model, api_base, prompt):
    r = requests.post("https://translate.volcengineapi.com/api/v1/translate",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"source_language": "en", "target_language": "zh", "text": text}, timeout=15)
    yield r.json()["translation"]


def _caiyun(text, api_key, model, api_base, prompt):
    r = requests.post("http://api.interpreter.caiyunai.com/v1/translator",
        headers={"Content-Type": "application/json", "X-Authorization": f"token {api_key}"},
        json={"source": [text], "trans_type": "en2zh", "detect": True}, timeout=15)
    yield r.json()["target"][0]


def _youdao(text, api_key, model, api_base, prompt):
    import time, uuid
    appid, secret = api_key.split(":")
    salt = str(uuid.uuid4())
    curtime = str(int(time.time()))
    sign_input = text if len(text) <= 20 else text[:10] + str(len(text)) + text[-10:]
    raw = f"{appid}{sign_input}{salt}{curtime}{secret}"
    sign = hashlib.sha256(raw.encode()).hexdigest()
    r = requests.post("https://openapi.youdao.com/api",
        data={"q": text, "from": "en", "to": "zh-CHS", "appKey": appid,
              "salt": salt, "sign": sign, "signType": "v3", "curtime": curtime}, timeout=15)
    yield r.json()["translation"][0]


def _niutrans(text, api_key, model, api_base, prompt):
    r = requests.post("https://api.niutrans.com/NiuTransServer/translation",
        json={"from": "en", "to": "zh", "apikey": api_key, "src_text": text}, timeout=15)
    yield r.json()["tgt_text"]


def _tencent(text, api_key, model, api_base, prompt):
    import time, hmac
    secret_id, secret_key = api_key.split(":")
    host = "tmt.tencentcloudapi.com"
    timestamp = int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    payload = json.dumps({"SourceText": text, "Source": "en", "Target": "zh", "ProjectId": 0})
    # TC3-HMAC-SHA256 signing
    hashed_payload = hashlib.sha256(payload.encode()).hexdigest()
    canonical = f"POST\n/\n\ncontent-type:application/json\nhost:{host}\n\ncontent-type;host\n{hashed_payload}"
    string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{date}/tmt/tc3_request\n{hashlib.sha256(canonical.encode()).hexdigest()}"
    def _hmac(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()
    secret_date = _hmac(f"TC3{secret_key}".encode(), date)
    secret_service = _hmac(secret_date, "tmt")
    signing_key = _hmac(secret_service, "tc3_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"TC3-HMAC-SHA256 Credential={secret_id}/{date}/tmt/tc3_request, SignedHeaders=content-type;host, Signature={signature}"
    r = requests.post(f"https://{host}",
        headers={"Authorization": auth, "Content-Type": "application/json",
                 "Host": host, "X-TC-Action": "TextTranslate", "X-TC-Version": "2018-03-21",
                 "X-TC-Timestamp": str(timestamp)},
        data=payload, timeout=15)
    yield r.json()["Response"]["TargetText"]


# ── Registry ─────────────────────────────────────

PROVIDERS = {
    "deepseek":   {"api_base": "https://api.deepseek.com/v1",                          "model": "deepseek-chat",                              "fn": _openai_compat},
    "openai":     {"api_base": "https://api.openai.com/v1",                             "model": "gpt-4o-mini",                                "fn": _openai_compat},
    "anthropic":  {"api_base": "anthropic",                                              "model": "claude-haiku-4-5-20251001",                  "fn": _anthropic},
    "gemini":     {"api_base": "gemini",                                                 "model": "gemini-2.0-flash",                           "fn": _gemini},
    "groq":       {"api_base": "https://api.groq.com/openai/v1",                        "model": "llama-3.3-70b-versatile",                    "fn": _openai_compat},
    "together":   {"api_base": "https://api.together.xyz/v1",                           "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",   "fn": _openai_compat},
    "openrouter": {"api_base": "https://openrouter.ai/api/v1",                          "model": "google/gemini-2.0-flash-001",                "fn": _openai_compat},
    "zhipu":      {"api_base": "https://open.bigmodel.cn/api/paas/v4",                  "model": "glm-4-flash",                                "fn": _openai_compat},
    "doubao":     {"api_base": "https://ark.cn-beijing.volces.com/api/v3",              "model": "doubao-1.5-lite-32k",                        "fn": _openai_compat},
    "qwen":       {"api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",     "model": "qwen-turbo",                                 "fn": _openai_compat},
    "kimi":       {"api_base": "https://api.moonshot.cn/v1",                             "model": "moonshot-v1-8k",                             "fn": _openai_compat},
    "siliconflow":{"api_base": "https://api.siliconflow.cn/v1",                          "model": "Qwen/Qwen2.5-7B-Instruct",                   "fn": _openai_compat},
    "ollama":     {"api_base": None,                                                     "model": "qwen2.5:7b",                                 "fn": _ollama},
    "deepl":      {"api_base": None, "model": None, "fn": _deepl},
    "google":     {"api_base": None, "model": None, "fn": _google},
    "google-free":{"api_base": None, "model": None, "fn": _google_free},
    "microsoft":  {"api_base": None, "model": None, "fn": _microsoft},
    "microsoft-free": {"api_base": None, "model": None, "fn": _microsoft_free},
    "baidu":      {"api_base": None, "model": None, "fn": _baidu},
    "volcano":    {"api_base": None, "model": None, "fn": _volcano},
    "caiyun":     {"api_base": None, "model": None, "fn": _caiyun},
    "youdao":     {"api_base": None, "model": None, "fn": _youdao},
    "niutrans":   {"api_base": None, "model": None, "fn": _niutrans},
    "tencent":    {"api_base": None, "model": None, "fn": _tencent},
}


_last_request_time = 0
_MIN_INTERVAL = 1.5  # seconds between API calls


def resolve_config(provider=None, model=None, api_base=None, api_key="", prompt=None):
    base = {"api_key": api_key, "prompt": prompt or DEFAULT_PROMPT}
    if provider and provider in PROVIDERS:
        preset = PROVIDERS[provider]
        return {**base, "model": model or preset["model"], "api_base": api_base or preset["api_base"], "fn": preset["fn"]}
    if api_base:
        return {**base, "model": model or "gpt-4o-mini", "api_base": api_base, "fn": _openai_compat}
    return {**base, "model": model or "qwen2.5:7b", "api_base": None, "fn": _ollama}


def translate_stream(text, config):
    import time
    global _last_request_time
    # rate limit: wait if too fast (skip for local ollama only)
    fn = config.get("fn")
    if fn is not _ollama:
        elapsed = time.time() - _last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_time = time.time()
    try:
        yield from config["fn"](text, config.get("api_key", ""), config.get("model", ""), config.get("api_base", ""), config.get("prompt", DEFAULT_PROMPT))
    except Exception:
        yield "[翻译失败]"
