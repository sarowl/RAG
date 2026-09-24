import threading
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tts import PiperTTS


class PiperTTSTests(unittest.TestCase):
    def setUp(self):
        self.tts = PiperTTS()
        self.addCleanup(self.tts.close)

    def test_disabled_does_not_load_or_synthesize(self):
        with patch.object(self.tts._executor, 'submit') as submit:
            self.tts.speak('Answer')
            submit.assert_not_called()
        self.assertIsNone(self.tts._voice)

    def test_missing_voice_leaves_speech_disabled(self):
        self.tts.model_path = Path('/missing/voice.onnx')
        with self.assertRaisesRegex(RuntimeError, 'voice missing'):
            self.tts.set_enabled(True)
        self.assertFalse(self.tts.enabled)

    def test_disable_during_synthesis_prevents_playback(self):
        started, release = threading.Event(), threading.Event()

        def synthesize(answer, wav):
            started.set()
            release.wait(5)
            wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0')

        self.tts.enabled = True
        self.tts._voice = Mock(synthesize_wav=synthesize)
        with patch('tts.subprocess.Popen') as player:
            self.tts.speak('Final answer')
            try:
                self.assertTrue(started.wait(5))
                self.tts.set_enabled(False)
            finally:
                release.set()
                self.tts.close()
            player.assert_not_called()

    def test_disable_stops_active_playback(self):
        process = Mock()
        process.poll.return_value = None
        self.tts._process = process
        self.tts.set_enabled(False)
        process.terminate.assert_called_once()
        self.tts._process = None

    def test_only_answer_is_passed_to_synthesis(self):
        def synthesize(answer, wav):
            wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0')

        self.tts._voice = Mock()
        self.tts._voice.synthesize_wav.side_effect = synthesize
        self.tts._player = 'aplay'
        process = Mock(returncode=0)
        process.communicate.return_value = (None, b'')
        with patch('tts.subprocess.Popen', return_value=process):
            self.tts._synthesize_and_play('Final answer', threading.Event())
        self.assertEqual(self.tts._voice.synthesize_wav.call_args.args[0], 'Final answer')


if __name__ == '__main__':
    unittest.main()
