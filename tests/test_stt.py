import ast
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from stt import VoskSTT, voice_question


class SpeechInputTests(unittest.TestCase):
    def test_missing_model_has_setup_hint(self):
        with patch('stt.Path.is_dir', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'README.md'):
                VoskSTT().listen()

    def capture(self, accepted=True, final='question', interrupt=False):
        recognizer = Mock()
        recognizer.AcceptWaveform.return_value = accepted
        recognizer.Result.return_value = json.dumps({'text': final})
        recognizer.FinalResult.return_value = json.dumps({'text': final})
        stream = Mock()
        stream.__exit__ = Mock(return_value=False)
        sd = Mock()
        sd.query_devices.return_value = {'default_samplerate': 48000}

        def open_stream(**kwargs):
            def enter():
                if interrupt:
                    raise KeyboardInterrupt
                kwargs['callback'](b'\0\0', 1, None, False)
            stream.__enter__ = Mock(side_effect=enter)
            return stream

        sd.RawInputStream.side_effect = open_stream
        vosk = SimpleNamespace(Model=Mock(), KaldiRecognizer=Mock(return_value=recognizer))
        with patch('stt.Path.is_dir', return_value=True), patch.dict(
            'sys.modules', {'sounddevice': sd, 'vosk': vosk}
        ):
            result = VoskSTT().listen(timeout=0.02)
        stream.__exit__.assert_called_once()
        self.assertEqual(sd.RawInputStream.call_args.kwargs['samplerate'], 48000)
        return result

    def test_utterance_transcribed_and_microphone_closed(self):
        self.assertEqual(self.capture(), 'question')

    def test_timeout_returns_final_transcript(self):
        self.assertEqual(self.capture(accepted=False), 'question')

    def test_silence_returns_empty(self):
        self.assertEqual(self.capture(accepted=False, final=''), '')

    def test_review_accept_edit_and_cancel(self):
        for reply, expected in [('', 'question'), ('edited question', 'edited question'), ('/cancel', None)]:
            stt, tts = Mock(), Mock()
            stt.listen.return_value = 'question'
            with patch('builtins.input', return_value=reply), patch('builtins.print'):
                self.assertEqual(voice_question(stt, tts), expected)
            tts.stop.assert_called_once()

    def test_failure_or_interrupt_returns_to_text_chat(self):
        for error in (KeyboardInterrupt(), RuntimeError('No microphone')):
            stt = Mock()
            stt.listen.side_effect = error
            with patch('builtins.input') as prompt, patch('builtins.print'):
                self.assertIsNone(voice_question(stt, Mock()))
            prompt.assert_not_called()

    def test_empty_transcript_is_not_submitted(self):
        stt = Mock()
        stt.listen.return_value = ''
        with patch('builtins.input') as prompt, patch('builtins.print'):
            self.assertIsNone(voice_question(stt, Mock()))
        prompt.assert_not_called()

    def test_terminal_sends_reviewed_voice_to_chain_and_storage(self):
        # Exercise the actual loop without importing the model/retrieval stack.
        tree = ast.parse(Path('aichatbot.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        chain, storage, tts, stt = Mock(), Mock(), Mock(), Mock()
        stt.listen.return_value = 'recognized question'
        chain.invoke.return_value = {'answer': 'answer'}
        namespace = {
            'log': Mock(), 'ChatStorage': Mock(return_value=storage),
            'CHAT_DB_PATH': ':memory:', 'init_chatbot': lambda: (chain, None),
            'PiperTTS': lambda: tts, 'VoskSTT': lambda: stt,
            'voice_question': voice_question, 'MAX_HISTORY': 5,
        }
        exec(compile(ast.Module(body=[main], type_ignores=[]), 'aichatbot.py', 'exec'), namespace)
        with patch('builtins.input', side_effect=['voice', 'corrected question', 'exit']), patch('builtins.print'):
            namespace['main']()
        self.assertEqual(chain.invoke.call_args.args[0]['question'], 'corrected question')
        storage.save.assert_called_once_with('corrected question', 'answer', None, None)
        tts.speak.assert_called_once_with('answer')
        tts.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
