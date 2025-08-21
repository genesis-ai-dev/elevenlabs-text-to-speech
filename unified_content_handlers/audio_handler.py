#!/usr/bin/env python3
"""
Audio Handler Module
Supports ElevenLabs, OpenAI, and Google Cloud TTS generation with concurrency
"""

import os
import base64
import io
import asyncio
import time
from typing import Optional, Union, List, Tuple, Dict
from pydub import AudioSegment
from elevenlabs import ElevenLabs
from openai import AsyncOpenAI, OpenAI
from google.cloud import texttospeech as gtts
import aiohttp
import backoff
from asyncio import Semaphore
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioHandler:
    def __init__(self, config: dict):
        """Initialize audio handler with configuration"""
        self.config = config.get('audio_generation', {})
        self.provider = self.config.get('provider', 'elevenlabs').lower()
        
        # Store provider-specific config
        self.elevenlabs_config = self.config.get('elevenlabs', {})
        self.openai_config = self.config.get('openai', {})
        self.google_config = self.config.get('google', {})
        
        # Concurrency settings
        self.max_concurrent = self.config.get('max_concurrent_requests', 5)
        # Do not bind a semaphore to a loop at init; create per running loop
        self._loop_semaphores: Dict[int, Semaphore] = {}
        
        # Rate limiting settings
        self.requests_per_minute = self.config.get('requests_per_minute', 60)
        self.request_times = []
        
        # Initialize the appropriate client
        if self.provider == 'elevenlabs':
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY not found in environment")
            self.elevenlabs_client = ElevenLabs(api_key=api_key)
            # For async ElevenLabs, we'll use aiohttp
            self.elevenlabs_api_key = api_key
        elif self.provider == 'openai':
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not found in environment")
            self.openai_client = OpenAI(api_key=api_key)
            self.async_openai_client = AsyncOpenAI(api_key=api_key)
        elif self.provider == 'google':
            # Google Cloud TTS uses application default credentials or explicit service account file
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path:
                self.google_client = gtts.TextToSpeechClient.from_service_account_file(credentials_path)
            else:
                self.google_client = gtts.TextToSpeechClient()
        elif self.provider == 'huggingface':
            # Uses custom Inference Endpoint exposed via HF_TTS_ENDPOINT
            self.hf_endpoint = os.getenv("HF_TTS_ENDPOINT")
            self.hf_token = os.getenv("HF_TOKEN_READ")
            if not self.hf_endpoint:
                raise RuntimeError("HF_TTS_ENDPOINT not found in environment for Hugging Face provider")
            if not self.hf_token:
                raise RuntimeError("HF_TOKEN_READ not found in environment for Hugging Face provider")
        else:
            raise ValueError(f"Unsupported audio provider: {self.provider}")
        
        # Shared HTTP session for providers that use aiohttp (improves concurrency performance)
        self._aiohttp_session: Optional[aiohttp.ClientSession] = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create a shared aiohttp session"""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            connector = aiohttp.TCPConnector(limit=self.max_concurrent)
            self._aiohttp_session = aiohttp.ClientSession(connector=connector)
        return self._aiohttp_session
    
    async def _check_rate_limit(self):
        """Check and enforce rate limiting (adaptive)"""
        now = time.time()
        # Remove requests older than 1 minute
        self.request_times = [t for t in self.request_times if now - t < 60]
        
        if len(self.request_times) >= self.requests_per_minute:
            # Calculate wait time
            oldest_request = self.request_times[0]
            wait_time = 60 - (now - oldest_request) + 0.1  # Add small buffer
            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
        
        self.request_times.append(now)
    
    def generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio using the configured provider (sync wrapper)"""
        return asyncio.run(self.generate_audio_async(text, output_path))
    
    def _get_semaphore_for_current_loop(self) -> Semaphore:
        """Return a semaphore bound to the current event loop, creating if needed"""
        loop = asyncio.get_running_loop()
        key = id(loop)
        sem = self._loop_semaphores.get(key)
        if sem is None:
            sem = Semaphore(self.max_concurrent)
            self._loop_semaphores[key] = sem
        return sem

    async def generate_audio_async(self, text: str, output_path: str) -> bool:
        """Generate audio using the configured provider (async)"""
        sem = self._get_semaphore_for_current_loop()
        async with sem:
            await self._check_rate_limit()
            
            if self.provider == 'elevenlabs':
                return await self._generate_elevenlabs_async(text, output_path)
            elif self.provider == 'openai':
                return await self._generate_openai_async(text, output_path)
            elif self.provider == 'google':
                return await self._generate_google_async(text, output_path)
            elif self.provider == 'huggingface':
                return await self._generate_huggingface_async(text, output_path)
            else:
                raise ValueError(f"Unsupported audio provider: {self.provider}")
    
    async def generate_multiple_audio(self, items: List[Tuple[str, str]]) -> List[Tuple[str, bool]]:
        """Generate multiple audio files concurrently with proper task scheduling
        
        Args:
            items: List of tuples (text, output_path)
            
        Returns:
            List of tuples (output_path, success)
        """
        async def run_one(text: str, output_path: str) -> Tuple[str, bool]:
            try:
                success = await self.generate_audio_async(text, output_path)
                return output_path, success
            except Exception as e:
                logger.error(f"Error generating audio for {output_path}: {e}")
                return output_path, False

        tasks: List[asyncio.Task] = [
            asyncio.create_task(run_one(text, output_path)) for text, output_path in items
        ]

        results: List[Tuple[str, bool]] = []
        for fut in asyncio.as_completed(tasks):
            output_path, success = await fut
            results.append((output_path, success))

        return results
    
    def _generate_elevenlabs(self, text: str, output_path: str) -> bool:
        """Generate audio using ElevenLabs (sync version for compatibility)"""
        return asyncio.run(self._generate_elevenlabs_async(text, output_path))
    
    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, Exception),
        max_tries=3,
        max_time=60
    )
    async def _generate_elevenlabs_async(self, text: str, output_path: str) -> bool:
        """Generate audio using ElevenLabs (async)"""
        try:
            voice_id = self.elevenlabs_config.get('voice_id')
            if not voice_id:
                raise ValueError("voice_id is required for ElevenLabs")
            
            # Use aiohttp for async requests to ElevenLabs
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.elevenlabs_api_key
            }
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            }
            
            session = await self._get_http_session()
            async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 429:
                        # Rate limit hit, wait and retry
                        retry_after = response.headers.get('retry-after', '60')
                        wait_time = int(retry_after)
                        logger.warning(f"ElevenLabs rate limit hit, waiting {wait_time} seconds")
                        await asyncio.sleep(wait_time)
                        raise aiohttp.ClientError("Rate limit hit, retrying...")
                    
                    response.raise_for_status()
                    audio_bytes = await response.read()
            
            # Convert MP3 to M4A
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # Ensure output path has .m4a extension
            if not output_path.endswith('.m4a'):
                output_path = os.path.splitext(output_path)[0] + '.m4a'
            
            # Export as M4A
            audio_segment.export(output_path, format="mp4", codec="aac")
            logger.info(f"Audio saved successfully to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating audio with ElevenLabs: {str(e)}")
            return False
    
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=60
    )
    async def _generate_openai_async(self, text: str, output_path: str) -> bool:
        """Generate audio using OpenAI (async)"""
        try:
            voice = self.openai_config.get('voice', 'echo')
            model = self.openai_config.get('model', 'gpt-4o-mini-tts')
            
            # Collect audio bytes
            audio_bytes = b""
            
            try:
                async with self.async_openai_client.audio.speech.with_streaming_response.create(
                    model=model,
                    voice=voice,
                    input=text,
                    response_format="mp3"
                ) as response:
                    # Check rate limit headers
                    if hasattr(response, 'headers'):
                        remaining = response.headers.get('x-ratelimit-remaining-requests')
                        if remaining and int(remaining) < 5:
                            logger.warning(f"Low rate limit remaining: {remaining}")
                    
                    async for chunk in response.iter_bytes():
                        audio_bytes += chunk
            except Exception as e:
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    # Extract retry-after if available
                    wait_time = 60  # Default wait time
                    logger.warning(f"OpenAI rate limit hit, waiting {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                    raise
                else:
                    raise
            
            # Convert MP3 to M4A
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # Ensure output path has .m4a extension
            if not output_path.endswith('.m4a'):
                output_path = os.path.splitext(output_path)[0] + '.m4a'
            
            # Export as M4A
            audio_segment.export(output_path, format="mp4", codec="aac")
            logger.info(f"Audio saved successfully to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating audio with OpenAI: {str(e)}")
            return False

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=60
    )
    async def _generate_google_async(self, text: str, output_path: str) -> bool:
        """Generate audio using Google Cloud Text-to-Speech (async wrapper using thread)"""
        try:
            # Prepare request parts from config with sensible defaults
            language_code = self.google_config.get('language_code', 'en-US')
            voice_name = self.google_config.get('voice_name')  # e.g., "en-US-Neural2-C"
            ssml_gender_str = self.google_config.get('ssml_gender', 'NEUTRAL').upper()
            speaking_rate = float(self.google_config.get('speaking_rate', 1.0))
            pitch = float(self.google_config.get('pitch', 0.0))
            volume_gain_db = float(self.google_config.get('volume_gain_db', 0.0))
            audio_encoding_str = self.google_config.get('audio_encoding', 'MP3').upper()
            final_format = (self.google_config.get('final_format') or 'm4a').lower()

            # Map gender and encoding
            gender_map = {
                'MALE': gtts.SsmlVoiceGender.MALE,
                'FEMALE': gtts.SsmlVoiceGender.FEMALE,
                'NEUTRAL': gtts.SsmlVoiceGender.NEUTRAL,
                'SSML_VOICE_GENDER_UNSPECIFIED': gtts.SsmlVoiceGender.SSML_VOICE_GENDER_UNSPECIFIED,
            }
            ssml_gender = gender_map.get(ssml_gender_str, gtts.SsmlVoiceGender.NEUTRAL)

            encoding_map = {
                'MP3': gtts.AudioEncoding.MP3,
                'OGG_OPUS': gtts.AudioEncoding.OGG_OPUS,
                'LINEAR16': gtts.AudioEncoding.LINEAR16,
                'MULAW': gtts.AudioEncoding.MULAW,
                'ALAW': gtts.AudioEncoding.ALAW,
            }
            # Allow users to specify M4A as a convenience: treat as final container, synthesize MP3
            if audio_encoding_str in ('M4A', 'MP4', 'AAC') and not self.google_config.get('final_format'):
                final_format = 'm4a'
                audio_encoding_str = 'MP3'
            audio_encoding = encoding_map.get(audio_encoding_str, gtts.AudioEncoding.MP3)

            synthesis_input = gtts.SynthesisInput(text=text)

            voice_params = gtts.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name if voice_name else None,
                ssml_gender=ssml_gender
            )

            audio_config = gtts.AudioConfig(
                audio_encoding=audio_encoding,
                speaking_rate=speaking_rate,
                pitch=pitch,
                volume_gain_db=volume_gain_db
            )

            def _synthesize_sync() -> bytes:
                response = self.google_client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice_params,
                    audio_config=audio_config
                )
                return response.audio_content

            audio_bytes: bytes = await asyncio.to_thread(_synthesize_sync)

            # Decode according to encoding, then export in requested final format
            if audio_encoding == gtts.AudioEncoding.MP3:
                audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            elif audio_encoding == gtts.AudioEncoding.OGG_OPUS:
                audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="ogg")
            elif audio_encoding == gtts.AudioEncoding.LINEAR16:
                audio_segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
            else:
                # Fallback: try generic decode
                audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))

            # Select final export format and extension
            if final_format == 'm4a':
                if not output_path.endswith('.m4a'):
                    output_path = os.path.splitext(output_path)[0] + '.m4a'
                audio_segment.export(output_path, format="mp4", codec="aac")
            elif final_format == 'mp3':
                if not output_path.endswith('.mp3'):
                    output_path = os.path.splitext(output_path)[0] + '.mp3'
                audio_segment.export(output_path, format="mp3")
            elif final_format == 'wav':
                if not output_path.endswith('.wav'):
                    output_path = os.path.splitext(output_path)[0] + '.wav'
                audio_segment.export(output_path, format="wav")
            else:
                # Default to m4a
                if not output_path.endswith('.m4a'):
                    output_path = os.path.splitext(output_path)[0] + '.m4a'
                audio_segment.export(output_path, format="mp4", codec="aac")
            logger.info(f"Audio saved successfully to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error generating audio with Google TTS: {str(e)}")
            return False

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, Exception),
        max_tries=3,
        max_time=60
    )
    async def _generate_huggingface_async(self, text: str, output_path: str) -> bool:
        """Generate audio using a custom Hugging Face Inference Endpoint.

        The endpoint is expected to accept JSON {"inputs": str} and return
        {"audio_base64": str, "sampling_rate": int}.
        """
        try:
            session = await self._get_http_session()
            headers = {
                "Authorization": f"Bearer {self.hf_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            payload = {"inputs": text}
            async with session.post(self.hf_endpoint, json=payload, headers=headers) as response:
                if response.status == 429:
                    retry_after = response.headers.get('retry-after', '60')
                    wait_time = int(retry_after)
                    logger.warning(f"Hugging Face rate limit hit, waiting {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                    raise aiohttp.ClientError("Rate limit hit, retrying...")
                response.raise_for_status()
                data = await response.json()

            audio_b64 = data.get("audio_base64") if isinstance(data, dict) else None
            if not audio_b64:
                raise ValueError("Hugging Face endpoint returned no 'audio_base64'")

            wav_bytes = base64.b64decode(audio_b64)
            audio_segment = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")

            # Ensure output path has .m4a extension
            if not output_path.endswith('.m4a'):
                output_path = os.path.splitext(output_path)[0] + '.m4a'

            audio_segment.export(output_path, format="mp4", codec="aac")
            logger.info(f"Audio saved successfully to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error generating audio with Hugging Face endpoint: {str(e)}")
            return False
    
    def get_provider_name(self) -> str:
        """Get the name of the current provider"""
        return self.provider 