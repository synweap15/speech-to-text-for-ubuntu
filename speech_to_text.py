#!/usr/bin/env python3
"""
Speech-to-text daemon using Faster Whisper.

Runs as a persistent process with models preloaded in memory.
Listens on a Unix socket for transcription requests from key_listener.py.

Request format (one line): <language> <audio_file_path>
Response: types text into active window via xdotool, then sends "OK\n" or "ERR ...\n"

Usage: python3 speech_to_text.py
"""

import json
import logging
import os
import pwd
import signal
import socket
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/speech_to_text.log')
    ]
)

try:
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    from Xlib import X, XK, display
    from Xlib.ext import xtest
except ImportError as e:
    print(f"Error: Required library not found: {e}")
    print("Install in your venv with: pip install numpy soundfile faster-whisper python-xlib")
    sys.exit(1)

SOCKET_PATH = "/tmp/speech_to_text.sock"

models = {}

def load_models():
    logging.info("Preloading models...")
    models['en'] = WhisperModel("base.en", device="cpu", compute_type="int8")
    logging.info("Loaded base.en model")
    models['other'] = WhisperModel("base", device="cpu", compute_type="int8")
    logging.info("Loaded base multilingual model")

def load_audio(file_path):
    audio, samplerate = sf.read(file_path)
    audio = audio.astype('float32')
    if len(audio.shape) > 1 and audio.shape[1] > 1:
        audio = np.mean(audio, axis=1)
    logging.info(f"Audio loaded: {file_path}, sample rate: {samplerate}")
    return audio

def transcribe(audio, language):
    model = models['en'] if language == 'en' else models['other']
    segments, _ = model.transcribe(
        audio,
        language=language,
        beam_size=1,
        vad_filter=True,
        word_timestamps=True
    )
    results = []
    for seg in segments:
        if seg.words:
            text = " ".join(w.word.strip() for w in seg.words if w.word.strip())
        else:
            text = seg.text.strip()
        if text:
            results.append(text)
            logging.info(f"Recognized: {text}")
    return results

_xdisplay = None
_keysym_cache = {}
_keymap_built = False

def _get_display():
    global _xdisplay
    if _xdisplay is None:
        _xdisplay = display.Display()
    return _xdisplay

def _build_keymap(d):
    global _keymap_built
    if _keymap_built:
        return
    mapping = d.get_keyboard_mapping(8, 248)
    for i, syms in enumerate(mapping):
        for level, ks in enumerate(syms):
            if ks != 0 and ks not in _keysym_cache:
                _keysym_cache[ks] = (i + 8, level)
    _keymap_built = True

def _find_keycode_and_modifier(d, keysym):
    _build_keymap(d)
    return _keysym_cache.get(keysym, (0, 0))

_shift_kc = None
_altgr_kc = None

def _init_modifier_keycodes(d):
    global _shift_kc, _altgr_kc
    if _shift_kc is None:
        _shift_kc = d.keysym_to_keycode(XK.XK_Shift_L)
        _altgr_kc = d.keysym_to_keycode(0xfe03)

def _type_char(d, char):
    keysym = XK.string_to_keysym(char)
    if keysym == 0:
        keysym = ord(char)
    keycode = d.keysym_to_keycode(keysym)
    if keycode != 0:
        shift = _needs_shift(d, keycode, keysym)
        if shift:
            xtest.fake_input(d, X.KeyPress, _shift_kc)
        xtest.fake_input(d, X.KeyPress, keycode)
        xtest.fake_input(d, X.KeyRelease, keycode)
        if shift:
            xtest.fake_input(d, X.KeyRelease, _shift_kc)
        d.sync()
    else:
        keycode, level = _find_keycode_and_modifier(d, keysym)
        if keycode != 0:
            need_altgr = level >= 4
            need_shift = level in (1, 5)
            if need_altgr and _altgr_kc:
                xtest.fake_input(d, X.KeyPress, _altgr_kc)
            if need_shift:
                xtest.fake_input(d, X.KeyPress, _shift_kc)
            xtest.fake_input(d, X.KeyPress, keycode)
            xtest.fake_input(d, X.KeyRelease, keycode)
            if need_shift:
                xtest.fake_input(d, X.KeyRelease, _shift_kc)
            if need_altgr and _altgr_kc:
                xtest.fake_input(d, X.KeyRelease, _altgr_kc)
            d.sync()
        else:
            code = format(ord(char), 'x')
            subprocess.run(["xdotool", "key", f"U{code}"], check=True)

def type_text(text):
    try:
        logging.info(f"Typing: {text}")
        d = _get_display()
        _init_modifier_keycodes(d)
        for char in text + " ":
            _type_char(d, char)
    except Exception as e:
        logging.error(f"Failed to type text: {e}")

def _needs_shift(d, keycode, keysym):
    keysym_noshift = d.keycode_to_keysym(keycode, 0)
    keysym_shift = d.keycode_to_keysym(keycode, 1)
    return keysym != keysym_noshift and keysym == keysym_shift

def handle_request(data):
    parts = data.strip().split(" ", 1)
    if len(parts) != 2:
        return "ERR invalid request format"

    language, audio_file = parts
    logging.info(f"Processing: {audio_file} (language: {language})")

    if not os.path.exists(audio_file):
        return f"ERR file not found: {audio_file}"

    audio = load_audio(audio_file)
    results = transcribe(audio, language)
    for segment in results:
        type_text(segment)

    logging.info("Processing completed")
    return "OK"

def cleanup(*_):
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    sys.exit(0)

def main():
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    load_models()

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o777)
    sock.listen(1)

    logging.info(f"Daemon listening on {SOCKET_PATH}")

    while True:
        conn, _ = sock.accept()
        try:
            data = conn.recv(4096).decode('utf-8')
            if data:
                result = handle_request(data)
                conn.sendall((result + "\n").encode('utf-8'))
        except Exception as e:
            logging.error(f"Request failed: {e}")
            try:
                conn.sendall(f"ERR {e}\n".encode('utf-8'))
            except Exception:
                pass
        finally:
            conn.close()

if __name__ == "__main__":
    main()
