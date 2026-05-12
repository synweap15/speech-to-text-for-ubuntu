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
    import pyautogui
    import soundfile as sf
    from faster_whisper import WhisperModel
except ImportError as e:
    print(f"Error: Required library not found: {e}")
    print("Install in your venv with: pip install numpy pyautogui soundfile faster-whisper")
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

def type_text(text):
    try:
        logging.info(f"Typing: {text}")
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "80", "--", text + " "],
            check=True
        )
    except Exception as e:
        logging.error(f"Failed to type text: {e}")

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
