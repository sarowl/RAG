import io
import json
import threading
import unittest
import wave
from http.client import HTTPConnection
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api import create_server, MAX_AUDIO_BODY
from stt import VoskSTT


def wav(channels=1, frames=160):
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0\0' * frames * channels)
    return output.getvalue()


class WebSTTTests(unittest.TestCase):
    def test_wav_validation_and_transcription(self):
        stt = VoskSTT()
        recognizer = Mock()
        recognizer.AcceptWaveform.return_value = True
        recognizer.Result.return_value = '{"text":"hello"}'
        recognizer.FinalResult.return_value = '{"text":"world"}'
        vosk = SimpleNamespace(Model=Mock(), KaldiRecognizer=Mock(return_value=recognizer))
        with patch.dict('sys.modules', {'vosk': vosk}), patch('stt.Path.is_dir', return_value=True):
            self.assertEqual(stt.transcribe_wav(wav()), 'hello world')
            self.assertEqual(stt.transcribe_wav(wav()), 'hello world')
            vosk.Model.assert_called_once()
            self.assertEqual(vosk.KaldiRecognizer.call_args.args[1], 16000)
        for invalid in [b'not wav', wav(channels=2), wav(frames=0), wav(frames=16000 * 31), wav()[:-2]]:
            with self.assertRaises(ValueError):
                stt.transcribe_wav(invalid)

    def test_endpoint_and_error_recovery(self):
        transcriber, chain, storage = Mock(), Mock(), Mock()
        transcriber.transcribe_wav.return_value = 'question'
        with create_server(('127.0.0.1', 0), chain, storage, stt=transcriber) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()

            def request(data, content_type='audio/wav', length=None):
                connection = HTTPConnection(*server.server_address, timeout=3)
                headers = {'Content-Type': content_type}
                if length is not None:
                    headers['Content-Length'] = str(length)
                connection.request('POST', '/api/stt', data, headers)
                response = connection.getresponse()
                result = response.status, json.loads(response.read())
                connection.close()
                return result

            try:
                self.assertEqual(request(wav()), (200, {'text': 'question'}))
                transcriber.transcribe_wav.assert_called_once_with(wav())
                self.assertEqual(request(wav(), 'application/json')[0], 415)
                self.assertEqual(request(b'')[0], 413)
                self.assertEqual(request(b'', length=MAX_AUDIO_BODY + 1)[0], 413)
                transcriber.transcribe_wav.side_effect = ValueError('Invalid WAV audio.')
                self.assertEqual(request(wav())[0], 400)
                transcriber.transcribe_wav.side_effect = RuntimeError('private error')
                status, result = request(wav())
                self.assertEqual(status, 503)
                self.assertNotIn('private', result['error'])
                transcriber.transcribe_wav.side_effect = None
                self.assertEqual(request(wav())[0], 200)
                chain.invoke.assert_not_called()
                storage.save.assert_not_called()
            finally:
                server.shutdown()
                thread.join()
