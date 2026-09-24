"""Optional, cancellable Piper speech for final chatbot answers."""

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger("kiosk_chatbot.tts")


class PiperTTS:
    """Synthesize locally and play WAV audio through ALSA on Linux/Pi.

    Imports and voice loading are deferred until explicitly enabled. Only one
    answer plays at a time; disabling cancels pending audio and stops playback.
    """

    def __init__(self, model_path=None):
        self.model_path = Path(model_path or os.getenv(
            "PIPER_MODEL", "voices/en_US-lessac-medium.onnx"
        )).expanduser()
        self.enabled = False
        self._voice = None
        self._player = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="piper")
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._process = None

    def set_enabled(self, enabled: bool):
        if not enabled:
            self.enabled = False
            self.stop()
            return
        if self._voice is None:
            if not self.model_path.is_file() or not Path(str(self.model_path) + ".json").is_file():
                raise RuntimeError(
                    f"Piper voice missing: {self.model_path} and its .json file are required. "
                    "See README.md for voice setup."
                )
            self._player = shutil.which("aplay")
            if not self._player:
                raise RuntimeError("Audio playback requires aplay. Install alsa-utils.")
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise RuntimeError("Install piper-tts to enable speech.") from exc
            self._voice = PiperVoice.load(str(self.model_path))
        self.enabled = True

    def speak(self, answer: str):
        if not self.enabled or not answer.strip():
            return
        self.stop()
        self._cancel = threading.Event()
        self._executor.submit(self._synthesize_and_play, answer, self._cancel)

    def stop(self):
        with self._lock:
            self._cancel.set()
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()

    def _synthesize_and_play(self, answer, cancelled):
        try:
            if cancelled.is_set():
                return
            with tempfile.TemporaryDirectory(prefix="kiosk-tts-") as directory:
                audio_path = Path(directory) / "answer.wav"
                with wave.open(str(audio_path), "wb") as wav_file:
                    self._voice.synthesize_wav(answer, wav_file)
                with self._lock:
                    if cancelled.is_set():
                        return
                    process = subprocess.Popen(
                        [self._player, "-q", str(audio_path)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    self._process = process
                try:
                    _, error = process.communicate()
                    if process.returncode and not cancelled.is_set():
                        raise RuntimeError(error.decode(errors="replace").strip())
                finally:
                    with self._lock:
                        self._process = None
        except Exception as exc:
            if not cancelled.is_set():
                log.warning("Speech unavailable; the answer is still shown in chat: %s", exc)

    def close(self):
        self.set_enabled(False)
        self._executor.shutdown(wait=True, cancel_futures=True)
