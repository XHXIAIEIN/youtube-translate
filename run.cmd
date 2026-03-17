@echo off
chcp 65001 >nul

REM ╔══════════════════════════════════════════════╗
REM ║  YouTube Live Translator — Configuration     ║
REM ╚══════════════════════════════════════════════╝

REM YouTube video or live URL
set URL=https://www.youtube.com/watch?v=gCNeDWCI0vo

REM Whisper model: tiny / small / medium / large-v3
set WHISPER=small

REM Audio chunk size (seconds)
set CHUNK=5

REM Translation provider (choose one):
REM   google-free (default, no API key needed) / microsoft-free
REM   ollama / deepseek / openai / anthropic / gemini / groq
REM   together / openrouter / siliconflow
REM   zhipu / doubao / qwen / kimi
REM   deepl / google / microsoft / baidu / volcano
REM   caiyun / youdao / niutrans / tencent
set PROVIDER=google-free

REM Override default model (optional, leave empty to use provider default)
set MODEL=

REM System prompt for LLM translation (leave empty for default)
set TRANSLATE_PROMPT=Simultaneous interpreter. Translate every word from English to Chinese. Keep person/place/organization names in English. Partial sentences: translate as-is, include every word. Output translation only.

REM ══════════════════════════════════════════════
REM  Do not edit below this line
REM ══════════════════════════════════════════════

REM Load API keys from .keys/api_keys.env
if exist "%~dp0.keys\api_keys.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.keys\api_keys.env") do (
        set "line=%%a"
        if not "%%a"=="" if not "!line:~0,1!"=="#" (
            set "%%a=%%b"
        )
    )
)

REM Auto-select API key based on provider
setlocal enabledelayedexpansion
set TRANSLATE_API_KEY=
if /i "%PROVIDER%"=="deepseek"   set "TRANSLATE_API_KEY=!DEEPSEEK_API_KEY!"
if /i "%PROVIDER%"=="openai"     set "TRANSLATE_API_KEY=!OPENAI_API_KEY!"
if /i "%PROVIDER%"=="anthropic"  set "TRANSLATE_API_KEY=!ANTHROPIC_API_KEY!"
if /i "%PROVIDER%"=="gemini"     set "TRANSLATE_API_KEY=!GEMINI_API_KEY!"
if /i "%PROVIDER%"=="groq"       set "TRANSLATE_API_KEY=!GROQ_API_KEY!"
if /i "%PROVIDER%"=="deepl"      set "TRANSLATE_API_KEY=!DEEPL_API_KEY!"
if /i "%PROVIDER%"=="microsoft"  set "TRANSLATE_API_KEY=!MICROSOFT_API_KEY!"
if /i "%PROVIDER%"=="baidu"      set "TRANSLATE_API_KEY=!BAIDU_API_KEY!"
if /i "%PROVIDER%"=="volcano"    set "TRANSLATE_API_KEY=!VOLCANO_API_KEY!"
if /i "%PROVIDER%"=="openrouter" set "TRANSLATE_API_KEY=!OPENROUTER_API_KEY!"
if /i "%PROVIDER%"=="together"   set "TRANSLATE_API_KEY=!TOGETHER_API_KEY!"
if /i "%PROVIDER%"=="zhipu"      set "TRANSLATE_API_KEY=!ZHIPU_API_KEY!"
if /i "%PROVIDER%"=="kimi"       set "TRANSLATE_API_KEY=!KIMI_API_KEY!"
if /i "%PROVIDER%"=="qwen"       set "TRANSLATE_API_KEY=!QWEN_API_KEY!"
if /i "%PROVIDER%"=="doubao"     set "TRANSLATE_API_KEY=!DOUBAO_API_KEY!"
if /i "%PROVIDER%"=="siliconflow" set "TRANSLATE_API_KEY=!SILICONFLOW_API_KEY!"
if /i "%PROVIDER%"=="caiyun"    set "TRANSLATE_API_KEY=!CAIYUN_API_KEY!"
if /i "%PROVIDER%"=="youdao"    set "TRANSLATE_API_KEY=!YOUDAO_API_KEY!"
if /i "%PROVIDER%"=="niutrans"  set "TRANSLATE_API_KEY=!NIUTRANS_API_KEY!"
if /i "%PROVIDER%"=="tencent"   set "TRANSLATE_API_KEY=!TENCENT_API_KEY!"
endlocal & set "TRANSLATE_API_KEY=%TRANSLATE_API_KEY%"

set PYTHONUNBUFFERED=1
set HF_ENDPOINT=https://hf-mirror.com
cls

set CMD=python "%~dp0live_translate.py" "%URL%" --whisper %WHISPER% --chunk %CHUNK% --provider %PROVIDER%
if not "%MODEL%"=="" set CMD=%CMD% --model %MODEL%
if not "%TRANSLATE_API_KEY%"=="" set CMD=%CMD% --api-key %TRANSLATE_API_KEY%
if not "%TRANSLATE_PROMPT%"=="" set CMD=%CMD% --prompt "%TRANSLATE_PROMPT%"

%CMD%
pause
