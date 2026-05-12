#!/bin/bash
PID=$(pgrep -u pawel -f /usr/libexec/gnome-session-binary | head -1)
if [ -n "$PID" ]; then
    export XAUTHORITY=$(tr '\0' '\n' < /proc/$PID/environ | grep ^XAUTHORITY= | cut -d= -f2-)
fi
exec /home/pawel/PycharmProjects/speech-to-text-for-ubuntu/venv/bin/python /home/pawel/PycharmProjects/speech-to-text-for-ubuntu/speech_to_text.py
