#!/usr/bin/env python3
"""
Audio Recording Key Listener

This script listens for a specific key press to start audio recording and stops on key release.
In other words, it listens and records when the key is pressed and stops when the key is released.

It is recommended to use a key (I use F16) that is not otherwise used by your system or 
applications, otherwise you may experience interference.

For example, suppose you want to use the side mouse button (BTN_SIDE) to trigger speech-to-text.
However, some programs (such as Chrome) already use this button for navigation (e.g., "back").
To avoid conflicts, you can use input-remapper-gtk to remap BTN_SIDE to F16 (which is typically 
not used by any program).

This script must be run as root in order to access input devices (e.g., /dev/input/event*).
Running as a regular user will result in permission errors.

To automatically start this key listener on boot, you can use the following crontab entry for root:

* * * * * ps -ef | grep "/home/david/Cursor/speech-to-text/key_listener.py" | grep -v grep > /dev/null || /usr/bin/python3 /home/david/Cursor/speech-to-text/key_listener.py >> /tmp/key_listener.log 2>&1 &

This cron job checks every minute if the key_listener.py script is running. If it is not, it starts the script.
The output and errors are appended to /tmp/key_listener.log.

Usage (as root): python3 key_listener.py

Tested on Ubuntu 24.04.2 LTS

The script assumes that the user has a python virtual environment in /home/david/venv/bin/python3
with the necessary packages installed including evdev, numpy pyautogui soundfile faster-whisper
"""

import logging
import os
import socket
import sys
import subprocess
import pwd
import time


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/key_listener.log')
    ]
)

import select

try:
    from evdev import InputDevice, categorize, ecodes, list_devices
except ImportError:
    print("Error: evdev library not found. Install in your venv with: pip install evdev")
    sys.exit(1)


def discover_devices_by_name(name_patterns):
    """
    Discover input devices matching any of the given name patterns.
    Returns a list of device paths that match.
    """
    matching_paths = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            if dev.name in name_patterns:
                matching_paths.append(path)
                logging.info(f"Discovered device: {path} ({dev.name})")
            dev.close()
        except Exception as e:
            logging.debug(f"Could not check device {path}: {e}")
    return matching_paths

# Configuration
# Device discovery: find Keychron keyboards dynamically by name
# This supports both USB and Bluetooth connections without hardcoding paths
DEVICE_NAME_PATTERNS = [
    "Keychron Keychron K15 Pro",           # USB main keyboard
    "Keychron Keychron K15 Pro Keyboard",  # USB secondary
    "Keychron K15 Pro Keyboard",           # Bluetooth keyboard
]

# Just a temporary file to store the audio.
AUDIO_FILE = "/tmp/recorded_audio.wav"

# The user who runs the X server accessing the microphone.
USER = "pawel"

# We will get XAUTHORITY variable from a running process (e.g., /usr/bin/ksmserver) owned by USER.
# Find a process that is always running in single instance and owned by USER and has
# XAUTHORITY variable defined in its environment (see /proc/{pid}/environ)
PROCESS_FOR_XAUTH_COPY = "/usr/libexec/gnome-session-binary"

# The script that will process the stored audio and generate text from it.
SPEECHTOTEXT_SCRIPT = "/home/pawel/PycharmProjects/speech-to-text-for-ubuntu/speech_to_text.py"

# Your python virtual environment
PYTHON_VENV = "/home/pawel/PycharmProjects/speech-to-text-for-ubuntu/venv/bin/python3"

def setup_environment():
    pw_record = pwd.getpwnam(USER)
    env = os.environ.copy()
    env.update({
        "HOME": f"/home/{USER}",
        "XDG_CACHE_HOME": f"/home/{USER}/.cache",
        "XDG_RUNTIME_DIR": f"/run/user/{pw_record.pw_uid}",
        "DISPLAY": ":1"
    })

    # Get XAUTHORITY from the environment of the running process 
    # PROCESS_FOR_XAUTH_COPY owned by USER.
    # If your XAUTHORITY is simply ~/.Xauthority, then you can skip this step
    # and set env["XAUTHORITY"] = "~/.Xauthority"
    # Check your confiuration using: echo $XAUTHORITY (as USER)
    try:
        # Use pgrep to get the PID of the process
        pid = subprocess.check_output(
            ["pgrep", "-u", USER, "-f", PROCESS_FOR_XAUTH_COPY],
            universal_newlines=True
        ).strip().split('\n')[0]
        environ_path = f"/proc/{pid}/environ"
        with open(environ_path, "rb") as f:
            env_vars = f.read().split(b'\0')
            xauth = None
            for var in env_vars:
                if var.startswith(b"XAUTHORITY="):
                    xauth = var[len(b"XAUTHORITY="):].decode()
                    break
        if not xauth:
            raise RuntimeError(f"XAUTHORITY not found in environment of process {PROCESS_FOR_XAUTH_COPY} (PID {pid})")
        env["XAUTHORITY"] = xauth
        logging.info(f"Set XAUTHORITY to {xauth} (from process {PROCESS_FOR_XAUTH_COPY}, PID {pid})")
    except Exception as e:
        logging.error(f"Could not get XAUTHORITY from process {PROCESS_FOR_XAUTH_COPY} for {USER}: {e}")
        sys.exit(1)

    return env

def main():
    """Main function."""
    # Check if running as root
    if os.geteuid() != 0:
        logging.error("This script must be run as root")
        sys.exit(1)

    # Setup
    env = setup_environment()
    recording_process = None

    # Discover and open all matching devices dynamically
    device_paths = discover_devices_by_name(DEVICE_NAME_PATTERNS)
    if not device_paths:
        logging.error(f"No devices found matching patterns: {DEVICE_NAME_PATTERNS}")
        sys.exit(1)

    devices = []
    for path in device_paths:
        try:
            dev = InputDevice(path)
            devices.append(dev)
            logging.info(f"Opened device: {path} ({dev.name})")
        except (FileNotFoundError, PermissionError) as e:
            logging.warning(f"Could not open {path}: {e}")

    if not devices:
        logging.error("No input devices could be opened")
        sys.exit(1)

    # Track modifier states
    modifiers = {
        'ctrl': False,
        'shift': False,
        'alt': False,
    }

    # Modifier key codes
    CTRL_KEYS = {'KEY_LEFTCTRL', 'KEY_RIGHTCTRL'}
    SHIFT_KEYS = {'KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'}
    ALT_KEYS = {'KEY_LEFTALT', 'KEY_RIGHTALT'}
    # Trigger keys mapped to language codes
    TRIGGER_KEYS = {
        'KEY_COMMA': 'en',   # Ctrl+Shift+Alt+, for English
        'KEY_SLASH': 'pl',   # Ctrl+Shift+Alt+/ for Polish
    }

    # Track recording state (toggle mode)
    is_recording = False
    recording_language = None
    recording_start_time = None
    MAX_RECORDING_SECONDS = 180  # 3 minutes

    logging.info(f"Listening for Ctrl+Shift+Alt+,/. (toggle mode) on {len(devices)} device(s)")

    def all_modifiers_held():
        return modifiers['ctrl'] and modifiers['shift'] and modifiers['alt']

    try:
        while True:
            # Use 1s timeout to check recording duration
            try:
                r, _, _ = select.select(devices, [], [], 1.0)
            except OSError as e:
                logging.warning(f"Device lost ({e}), reconnecting...")
                for dev in devices:
                    try:
                        dev.close()
                    except Exception:
                        pass
                time.sleep(2)
                device_paths = discover_devices_by_name(DEVICE_NAME_PATTERNS)
                devices = []
                for path in device_paths:
                    try:
                        dev = InputDevice(path)
                        devices.append(dev)
                        logging.info(f"Reconnected device: {path} ({dev.name})")
                    except Exception:
                        pass
                if not devices:
                    logging.warning("No devices found, retrying in 5s...")
                    time.sleep(5)
                # Reset modifier states after reconnect
                modifiers['ctrl'] = modifiers['shift'] = modifiers['alt'] = False
                continue

            # Auto-stop recording after max duration
            if is_recording and (time.time() - recording_start_time) >= MAX_RECORDING_SECONDS:
                logging.info(f"Recording reached {MAX_RECORDING_SECONDS}s limit, auto-stopping")
                recording_process.terminate()
                recording_process.wait()
                is_recording = False
                logging.info(f"Recording saved to {AUDIO_FILE}")

                logging.info(f"Sending to STT daemon (language: {recording_language})")
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.connect("/tmp/speech_to_text.sock")
                    sock.sendall(f"{recording_language} {AUDIO_FILE}".encode())
                    resp = sock.recv(4096).decode().strip()
                    sock.close()
                    logging.info(f"STT daemon response: {resp}")
                except Exception as e:
                    logging.error(f"STT daemon error: {e}")
                recording_process = None
                recording_language = None

            for dev in r:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        key = categorize(event)
                        keycode = key.keycode

                        # Handle list of keycodes (some keys return a list)
                        if isinstance(keycode, list):
                            keycode = keycode[0]

                        # Ignore key repeats
                        if key.keystate == 2:
                            continue

                        is_down = key.keystate == key.key_down

                        if is_down and (modifiers['ctrl'] or modifiers['shift'] or modifiers['alt']):
                            logging.debug(f"Key pressed with modifiers: {keycode} (ctrl={modifiers['ctrl']}, shift={modifiers['shift']}, alt={modifiers['alt']})")

                        # Update modifier states
                        if keycode in CTRL_KEYS:
                            modifiers['ctrl'] = is_down
                        elif keycode in SHIFT_KEYS:
                            modifiers['shift'] = is_down
                        elif keycode in ALT_KEYS:
                            modifiers['alt'] = is_down

                        # Check for trigger key with all modifiers (toggle on key DOWN)
                        if keycode in TRIGGER_KEYS and is_down and all_modifiers_held():
                            language = TRIGGER_KEYS[keycode]

                            if not is_recording:
                                # Start recording
                                recording_language = language
                                logging.info(f"Starting audio recording (toggle ON, language: {language})")
                                recording_process = subprocess.Popen([
                                    "sudo", "-u", USER, "-E",
                                    "pw-record",
                                    "--rate", "16000",
                                    "--channels", "1",
                                    "--format", "s16",
                                    AUDIO_FILE
                                ], env=env)
                                is_recording = True
                                recording_start_time = time.time()
                                logging.info(f"Recording started with PID {recording_process.pid}")

                            else:
                                # Stop recording and process
                                logging.info("Stopping audio recording (toggle OFF)")
                                recording_process.terminate()
                                recording_process.wait()
                                is_recording = False
                                logging.info(f"Recording saved to {AUDIO_FILE}")

                                logging.info(f"Sending to STT daemon (language: {recording_language})")
                                try:
                                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                                    sock.connect("/tmp/speech_to_text.sock")
                                    sock.sendall(f"{recording_language} {AUDIO_FILE}".encode())
                                    resp = sock.recv(4096).decode().strip()
                                    sock.close()
                                    logging.info(f"STT daemon response: {resp}")
                                except Exception as e:
                                    logging.error(f"STT daemon error: {e}")

                                recording_process = None
                                recording_language = None

    except KeyboardInterrupt:
        logging.info("Shutting down due to keyboard interrupt")
        if recording_process:
            recording_process.terminate()
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)  # Exit with error code so systemd can restart

if __name__ == "__main__":
    main()

