# Speech-to-Text For Ubuntu

A simple Python project to record audio using keyboard hotkeys and automatically transcribe it to text offline using Faster Whisper. Supports multiple languages with different trigger keys. Designed for use on Linux systems (tested on Ubuntu 24.04.2 LTS).

## Features

- **Multi-language support**: English and Polish with separate hotkeys
- **Toggle recording**: Press hotkey to start, press again to stop and transcribe
- **Auto-stop**: Recording automatically stops after 3 minutes
- **Offline**: Uses local Faster Whisper models, no internet required
- **Auto-type**: Transcribed text is typed into the active window via xdotool

## Keyboard Shortcuts

| Shortcut | Language | Whisper Model |
|---|---|---|
| `Ctrl+Shift+Alt+,` | English | `tiny.en` (fast) |
| `Ctrl+Shift+Alt+/` | Polish | `small` (multilingual) |

## Project Overview

- **key_listener.py**: Runs as root, monitors keyboard via evdev for hotkey combos. Discovers Keychron K15 Pro keyboards dynamically. Starts/stops `pw-record` for audio capture and triggers transcription.

- **speech_to_text.py**: Loads recorded audio, transcribes using Faster Whisper, and types the result into the active window using `xdotool`.

- **speech-to-text.service**: systemd unit file to run the key listener on boot.

## Requirements

- Python 3.x
- Linux (tested on Ubuntu 24.04.2 LTS)
- PipeWire (`pw-record` for audio recording)
- `xdotool` (for typing transcribed text)
- `evdev` (for key listening)
- Faster Whisper

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/synweap15/speech-to-text-for-ubuntu
   cd speech-to-text-for-ubuntu
   ```
2. **Create and activate a Python virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Install system dependencies**
   ```bash
   sudo apt install pipewire xdotool
   ```
5. **Pre-download Whisper models**
   ```bash
   python3 -c "from faster_whisper import WhisperModel; WhisperModel('tiny.en', device='cpu', compute_type='int8'); WhisperModel('small', device='cpu', compute_type='int8')"
   ```
6. **Install and enable the systemd service**
   ```bash
   sudo cp speech-to-text.service /etc/systemd/system/
   sudo systemctl enable --now speech-to-text.service
   ```

## Configuration

Edit `key_listener.py` to adjust:

- `DEVICE_NAME_PATTERNS` - keyboard device names to monitor
- `USER` - the desktop user
- `TRIGGER_KEYS` - hotkey-to-language mappings
- `MAX_RECORDING_SECONDS` - max recording duration (default: 180s)
- `PROCESS_FOR_XAUTH_COPY` - process to get XAUTHORITY from
- `DISPLAY` - X display number

## Usage

The service runs automatically on boot. Press a hotkey to start recording, press it again to stop and transcribe. The transcribed text is typed into whatever window is focused.

Logs are written to `/tmp/key_listener.log` and `/tmp/speech_to_text.log`.

## License

MIT License

Copyright (c) 2025 CDNsun

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
