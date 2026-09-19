"""Unit test to verify faster-whisper WhisperModel is loaded once and reused."""

import unittest
from unittest.mock import MagicMock, patch
import core.voice as voice


class TestWhisperModelReuse(unittest.TestCase):
    def test_module_level_model_exists(self):
        """Verify _whisper_model variable is defined at module level."""
        self.assertTrue(hasattr(voice, "_whisper_model"))

    def test_transcribe_local_reuses_module_model(self):
        """Verify _transcribe_local uses the existing _whisper_model and does not instantiate a new one."""
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "test transcription"
        mock_model.transcribe.return_value = ([mock_segment], None)

        with patch.object(voice, "_whisper_model", mock_model):
            with patch("core.voice.WhisperModel") as mock_whisper_class:
                # Call 1
                res1 = voice._transcribe_local("dummy1.wav")
                self.assertEqual(res1, "test transcription")

                # Call 2
                res2 = voice._transcribe_local("dummy2.wav")
                self.assertEqual(res2, "test transcription")

                # Verify WhisperModel constructor was never called during transcription calls
                mock_whisper_class.assert_not_called()

                # Verify transcribe was called on the reused model
                self.assertEqual(mock_model.transcribe.call_count, 2)

    def test_transcribe_local_lazy_init_if_none(self):
        """Verify that if _whisper_model was None, it initializes once and retains it."""
        mock_new_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "lazy transcription"
        mock_new_model.transcribe.return_value = ([mock_segment], None)

        with patch.object(voice, "_whisper_model", None):
            with patch("core.voice.WhisperModel", return_value=mock_new_model) as mock_whisper_class:
                # First call should initialize model once
                res1 = voice._transcribe_local("dummy.wav")
                self.assertEqual(res1, "lazy transcription")
                self.assertEqual(mock_whisper_class.call_count, 1)

                # Second call should reuse the initialized model
                res2 = voice._transcribe_local("dummy.wav")
                self.assertEqual(res2, "lazy transcription")
                # Still only called once!
                self.assertEqual(mock_whisper_class.call_count, 1)


if __name__ == "__main__":
    unittest.main()
