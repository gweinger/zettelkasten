"""Audio transcription using local Whisper."""

from pathlib import Path
import whisper
from zettelkasten.core.models import Transcript
from zettelkasten.core.config import Config


class TranscriptionService:
    """Transcribe audio files using local Whisper."""

    def __init__(self, config: Config, model_size: str = "base"):
        """
        Initialize transcription service with local Whisper.

        Args:
            config: Application configuration
            model_size: Whisper model size (tiny, base, small, medium, large)
                       - tiny: fastest, least accurate
                       - base: good balance (default)
                       - small: better accuracy
                       - medium/large: best accuracy, slower
        """
        self.config = config
        self.model_size = model_size
        self.model = None  # Lazy load the model
        self.config.ensure_directories()

    def _load_model(self) -> whisper.Whisper:
        """Lazy load the Whisper model."""
        if self.model is None:
            self.model = whisper.load_model(self.model_size)
        return self.model

    def transcribe(self, audio_file: Path, language: str = "en") -> Transcript:
        """
        Transcribe an audio file using local Whisper.

        Args:
            audio_file: Path to audio file
            language: Language code (default: "en")

        Returns:
            Transcript object with text and metadata
        """
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        # Load model
        model = self._load_model()

        # Transcribe audio
        result = model.transcribe(
            str(audio_file),
            language=language,
            verbose=False,
        )

        # Save transcript to file
        transcript_file = self.config.transcripts_path / f"{audio_file.stem}.txt"
        transcript_file.write_text(result["text"])

        return Transcript(
            text=result["text"],
            source_file=audio_file,
            language=result.get("language", language),
            duration=None,  # Whisper doesn't provide duration directly
        )

    def get_transcript_path(self, audio_file: Path) -> Path:
        """Get the expected path for a transcript file."""
        return self.config.transcripts_path / f"{audio_file.stem}.txt"

    def transcript_exists(self, audio_file: Path) -> bool:
        """Check if a transcript already exists for an audio file."""
        return self.get_transcript_path(audio_file).exists()

    def load_transcript(self, audio_file: Path) -> Transcript:
        """Load an existing transcript from disk."""
        transcript_file = self.get_transcript_path(audio_file)
        if not transcript_file.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript_file}")

        text = transcript_file.read_text()
        return Transcript(
            text=text,
            source_file=audio_file,
        )
