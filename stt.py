"""Optional offline microphone transcription for the terminal chatbot."""

import json
import io
import os
import queue
import threading
import wave
from pathlib import Path
from time import monotonic


class VoskSTT:
    """Load Vosk on first use and capture one utterance, up to 15 seconds."""

    def __init__(self):
        self._model = None

    def transcribe_wav(self, data):
        """Transcribe bounded mono PCM from the browser without a server microphone."""
        try:
            with wave.open(io.BytesIO(data), 'rb') as audio:
                rate = audio.getframerate()
                frames = audio.getnframes()
                if (audio.getnchannels() != 1 or audio.getsampwidth() != 2
                        or not 8000 <= rate <= 96000 or not 0 < frames <= rate * 30):
                    raise ValueError('Send mono 16-bit WAV audio, up to 30 seconds.')
                pcm = audio.readframes(frames)
                if len(pcm) != frames * 2:
                    raise ValueError('Incomplete WAV audio.')
        except (wave.Error, EOFError) as exc:
            raise ValueError('Invalid WAV audio.') from exc
        from vosk import Model, KaldiRecognizer
        if self._model is None:
            model_path = Path(os.getenv('VOSK_MODEL', 'models/vosk-model-small-en-us-0.15')).expanduser()
            if not model_path.is_dir():
                raise RuntimeError('Speech model missing. See README.md for voice input setup.')
            self._model = Model(str(model_path))
        recognizer = KaldiRecognizer(self._model, rate)
        parts = []
        for offset in range(0, len(pcm), 8000):
            if recognizer.AcceptWaveform(pcm[offset:offset + 8000]):
                parts.append(json.loads(recognizer.Result()).get('text', ''))
        parts.append(json.loads(recognizer.FinalResult()).get('text', ''))
        return ' '.join(part.strip() for part in parts if part.strip())

    def listen(self, timeout=15):
        model_path = Path(os.getenv(
            "VOSK_MODEL", "models/vosk-model-small-en-us-0.15"
        )).expanduser()
        if not model_path.is_dir():
            raise RuntimeError(
                f"Speech model missing: {model_path}. See README.md for voice input setup."
            )
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                "Install requirements_stt.txt and PortAudio (libportaudio2 on Linux)."
            ) from exc

        if self._model is None:
            print("Loading speech recognition model …")
            self._model = Model(str(model_path))
        device = os.getenv("STT_DEVICE") or None
        if device is not None and device.isdecimal():
            device = int(device)
        sample_rate = int(sd.query_devices(device, "input")["default_samplerate"])
        recognizer = KaldiRecognizer(self._model, sample_rate)
        audio = queue.Queue(maxsize=100)
        overflow = threading.Event()

        def capture(data, frames, time_info, status):
            if status:
                overflow.set()
            try:
                audio.put_nowait(bytes(data))
            except queue.Full:
                overflow.set()

        with sd.RawInputStream(
            samplerate=sample_rate, blocksize=max(1, sample_rate // 10),
            device=device, dtype="int16", channels=1, callback=capture,
        ):
            print(f"Listening (up to {timeout} seconds). Pause to finish; Ctrl+C cancels.")
            deadline = monotonic() + timeout
            while monotonic() < deadline:
                if overflow.is_set():
                    raise RuntimeError("Microphone audio was dropped. Please try again.")
                try:
                    data = audio.get(timeout=min(0.1, max(0.001, deadline - monotonic())))
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(data):
                    text = json.loads(recognizer.Result()).get("text", "").strip()
                    if text:
                        return text
            return json.loads(recognizer.FinalResult()).get("text", "").strip()


def voice_question(stt, tts):
    """Review speech before submitting it; cancellation keeps text chat available."""
    tts.stop()
    try:
        text = stt.listen()
        if not text:
            print("No speech recognized. Type 'voice' to retry or type your question.\n")
            return None
        print(f"Heard: {text}")
        edited = input("Enter to send, type a correction, or /cancel: ").strip()
        return None if edited.lower() == "/cancel" else (edited or text)
    except KeyboardInterrupt:
        print("\nVoice input cancelled.\n")
    except Exception as exc:
        print(f"Voice input unavailable: {exc}\nYou can still type your question.\n")
    return None
