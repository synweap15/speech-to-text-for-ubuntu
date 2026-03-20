#!/usr/bin/env python3
"""
Simple speech-to-text processor using Faster Whisper.

For English we use the tiny.en model for speed. For other languages we use the
tiny multilingual model.

The script expects an audio file (e.g. /tmp/recorded_audio.wav) as an argument.

Usage: python3 speech_to_text.py [--language LANG] <audio_file>

Tested on Ubuntu 24.04.2 LTS

The script is intended to be run using your Python virtual environment (see key_listener.py).
"""

import argparse
import logging
import sys
import os
import pwd
import subprocess


# Setup logging
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
except ImportError as e:
    print(f"Error: Required library not found: {e}")
    print("Install in your venv with: pip install numpy soundfile faster-whisper")
    sys.exit(1)

def log_user_info():
    """Log current user information."""
    try:
        uid = os.geteuid()
        user = pwd.getpwuid(uid).pw_name
        logging.info(f"Running as user: {os.getlogin()}")
        logging.info(f"Effective user: {user} (UID: {uid})")
    except Exception as e:
        logging.warning(f"Could not determine user info: {e}")

def load_audio(file_path):
    """Load and preprocess audio file."""
    if not os.path.exists(file_path):
        logging.error(f"Audio file not found: {file_path}")
        sys.exit(1)
    
    try:
        audio, samplerate = sf.read(file_path)
        audio = audio.astype('float32')
        
        # Convert stereo to mono if necessary
        if len(audio.shape) > 1 and audio.shape[1] > 1:
            audio = np.mean(audio, axis=1)
            logging.info("Converted stereo audio to mono")
        
        logging.info(f"Audio loaded: {file_path}, sample rate: {samplerate}")
        return audio
        
    except Exception as e:
        logging.error(f"Failed to read audio file {file_path}: {e}")
        sys.exit(1)

def transcribe_audio(audio, language="en"):
    """Transcribe audio using Whisper."""
    try:
        # Use English-only model for English (faster), multilingual small for others
        model_name = "tiny.en" if language == "en" else "small"
        logging.info(f"Loading Whisper model '{model_name}' for language '{language}'...")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")

        logging.info("Starting transcription...")
        segments, _ = model.transcribe(
            audio,
            language=language,
            beam_size=1,
            vad_filter=True
        )
        
        # Process segments
        results = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                results.append(text)
                logging.info(f"Recognized: {text}")
        
        logging.info(f"Transcription completed: {len(results)} segments")
        return results
        
    except Exception as e:
        logging.error(f"Transcription failed: {e}")
        sys.exit(1)

def type_text(text):
    """Type text using xdotool for better Unicode support."""
    try:
        logging.info(f"Typing: {text}")
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--", text + " "],
            check=True
        )
    except Exception as e:
        logging.error(f"Failed to type text: {e}")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Speech-to-text using Faster Whisper")
    parser.add_argument("audio_file", help="Path to audio file")
    parser.add_argument("--language", default="en", help="Language code (default: en)")
    args = parser.parse_args()

    # Log user info
    log_user_info()

    # Process audio
    logging.info(f"Processing audio file: {args.audio_file} (language: {args.language})")

    # Load audio
    audio = load_audio(args.audio_file)

    # Transcribe
    segments = transcribe_audio(audio, language=args.language)

    # Type results
    for segment in segments:
        type_text(segment)

    logging.info("Processing completed")

if __name__ == "__main__":
    main()

