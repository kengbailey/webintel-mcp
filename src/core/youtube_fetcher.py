"""
YouTube content fetching functionality using yt-dlp and STT
"""

import logging
import tempfile
from pathlib import Path
from typing import Tuple
import uuid
import yt_dlp
from openai import OpenAI

from .config import SearchConfig, SearchException


class YouTubeContentFetcher:
    """Handles fetching and transcribing YouTube video content."""
    
    def __init__(self):
        self.stt_endpoint = SearchConfig.STT_ENDPOINT
        self.stt_model = SearchConfig.STT_MODEL
        self.stt_api_key = SearchConfig.STT_API_KEY
        self.logger = logging.getLogger(__name__)
    
    def _extract_video_id(self, video_input: str) -> str:
        """
        Extract video ID from YouTube URL or validate existing ID.
        
        Args:
            video_input: YouTube URL or video ID
            
        Returns:
            Validated video ID
            
        Raises:
            SearchException: If video ID extraction fails
        """
        # If it looks like a video ID (11 chars, alphanumeric), return as-is
        if len(video_input) == 11 and video_input.replace('-', '').replace('_', '').isalnum():
            return video_input
        
        # Otherwise, extract from URL using yt-dlp
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(video_input, download=False)
                return info['id']
        except Exception as e:
            raise SearchException(f"Failed to extract video ID from {video_input}: {str(e)}")
    
    def fetch_and_transcribe(self, video_input: str) -> Tuple[str, str]:
        """
        Download YouTube audio and transcribe it using STT.
        
        Args:
            video_input: YouTube URL or video ID
            
        Returns:
            Tuple of (video_id, transcript_text)
            
        Raises:
            SearchException: If download or transcription fails
        """
        # Extract video ID from input
        video_id = self._extract_video_id(video_input)

        # Create portable temp directory that works everywhere
        temp_dir = Path(tempfile.mkdtemp(prefix='youtube_audio_'))
        unique_id = uuid.uuid4().hex
        audio_path = temp_dir / f"audio_{unique_id}.opus"

        try:
            ydl_opts = {
                'format': 'worstaudio/worst',  # Fallback if worstaudio fails
                'outtmpl': str(audio_path.with_suffix('')),
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'opus'}],
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                },
                'nocheckcertificate': True,
                # Remote components for YouTube JS extraction (fixes 403 errors)
                'extractor_args': {'youtube': {'player_client': ['web', 'mweb']}},
                'verbose': True,  # Show detailed output for debugging
            }

            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_input])
            
            if not audio_path.exists():
                raise SearchException("Audio file was not created by yt-dlp")
            
            if audio_path.stat().st_size == 0:
                raise SearchException("Downloaded audio file is empty")

            # Transcribe
            client = OpenAI(base_url=self.stt_endpoint, api_key=self.stt_api_key)
            with open(audio_path, 'rb') as f:
                transcription = client.audio.transcriptions.create(
                    model=self.stt_model,
                    file=f,
                    response_format="text"
                )

            return video_id, transcription
        
        except Exception as e:
            raise SearchException(f"Failed to fetch/transcribe YouTube content: {str(e)}")
        
        finally:
            # Cleanup file
            if audio_path.exists():
                self.logger.debug(f"Cleaning up temporary file: {audio_path}")
                audio_path.unlink(missing_ok=True)
            
            # Cleanup directory
            if temp_dir.exists():
                self.logger.debug(f"Cleaning up temporary directory: {temp_dir}")
                try:
                    temp_dir.rmdir()
                except OSError:
                    # Directory not empty, use shutil for safety
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
