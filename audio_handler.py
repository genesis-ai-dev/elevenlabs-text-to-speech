#!/usr/bin/env python3
"""
Audio Handler Module
Supports both ElevenLabs and OpenAI text-to-speech generation with concurrency
"""

import os
import io
import asyncio
import time
from typing import Optional, Union, List, Tuple, Dict
from pydub import AudioSegment
from elevenlabs import ElevenLabs
from openai import AsyncOpenAI, OpenAI
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
        
        # Concurrency settings
        self.max_concurrent = self.config.get('max_concurrent_requests', 5)
        self.semaphore = Semaphore(self.max_concurrent)
        
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
        else:
            raise ValueError(f"Unsupported audio provider: {self.provider}")
    
    async def _check_rate_limit(self):
        """Check and enforce rate limiting"""
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
    
    async def generate_audio_async(self, text: str, output_path: str) -> bool:
        """Generate audio using the configured provider (async)"""
        async with self.semaphore:
            await self._check_rate_limit()
            
            if self.provider == 'elevenlabs':
                return await self._generate_elevenlabs_async(text, output_path)
            elif self.provider == 'openai':
                return await self._generate_openai_async(text, output_path)
            else:
                raise ValueError(f"Unsupported audio provider: {self.provider}")
    
    async def generate_multiple_audio(self, items: List[Tuple[str, str]]) -> List[Tuple[str, bool]]:
        """Generate multiple audio files concurrently
        
        Args:
            items: List of tuples (text, output_path)
            
        Returns:
            List of tuples (output_path, success)
        """
        tasks = []
        for text, output_path in items:
            task = self.generate_audio_async(text, output_path)
            tasks.append((output_path, task))
        
        results = []
        for output_path, task in tasks:
            try:
                success = await task
                results.append((output_path, success))
            except Exception as e:
                logger.error(f"Error generating audio for {output_path}: {e}")
                results.append((output_path, False))
        
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
            
            async with aiohttp.ClientSession() as session:
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
    
    def get_provider_name(self) -> str:
        """Get the name of the current provider"""
        return self.provider 