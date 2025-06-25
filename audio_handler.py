#!/usr/bin/env python3
"""
Audio Handler Module
Supports both ElevenLabs and OpenAI text-to-speech generation
"""

import os
import io
import asyncio
from typing import Optional, Union
from pydub import AudioSegment
from elevenlabs import ElevenLabs
from openai import AsyncOpenAI, OpenAI


class AudioHandler:
    def __init__(self, config: dict):
        """Initialize audio handler with configuration"""
        self.config = config.get('audio_generation', {})
        self.provider = self.config.get('provider', 'elevenlabs').lower()
        
        # Store provider-specific config
        self.elevenlabs_config = self.config.get('elevenlabs', {})
        self.openai_config = self.config.get('openai', {})
        
        # Initialize the appropriate client
        if self.provider == 'elevenlabs':
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY not found in environment")
            self.elevenlabs_client = ElevenLabs(api_key=api_key)
        elif self.provider == 'openai':
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not found in environment")
            self.openai_client = OpenAI(api_key=api_key)
            self.async_openai_client = AsyncOpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unsupported audio provider: {self.provider}")
    
    def generate_audio(self, text: str, output_path: str) -> bool:
        """Generate audio using the configured provider"""
        if self.provider == 'elevenlabs':
            return self._generate_elevenlabs(text, output_path)
        elif self.provider == 'openai':
            # Use sync version for compatibility with existing code
            return asyncio.run(self._generate_openai_async(text, output_path))
        else:
            raise ValueError(f"Unsupported audio provider: {self.provider}")
    
    def _generate_elevenlabs(self, text: str, output_path: str) -> bool:
        """Generate audio using ElevenLabs"""
        try:
            voice_id = self.elevenlabs_config.get('voice_id')
            if not voice_id:
                raise ValueError("voice_id is required for ElevenLabs")
            
            # Use the v3 API endpoint
            audio_generator = self.elevenlabs_client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            
            # Collect audio bytes from generator
            audio_bytes = b"".join(audio_generator)
            
            # Convert MP3 to M4A
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # Ensure output path has .m4a extension
            if not output_path.endswith('.m4a'):
                output_path = os.path.splitext(output_path)[0] + '.m4a'
            
            # Export as M4A
            audio_segment.export(output_path, format="mp4", codec="aac")
            print(f"Audio saved successfully to {output_path}")
            return True
            
        except Exception as e:
            print(f"Error generating audio with ElevenLabs: {str(e)}")
            return False
    
    async def _generate_openai_async(self, text: str, output_path: str) -> bool:
        """Generate audio using OpenAI (async)"""
        try:
            voice = self.openai_config.get('voice', 'echo')
            model = self.openai_config.get('model', 'gpt-4o-mini-tts')
            
            # Collect audio bytes
            audio_bytes = b""
            
            async with self.async_openai_client.audio.speech.with_streaming_response.create(
                model=model,
                voice=voice,
                input=text,
                response_format="mp3"
            ) as response:
                async for chunk in response.iter_bytes():
                    audio_bytes += chunk
            
            # Convert MP3 to M4A
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            
            # Ensure output path has .m4a extension
            if not output_path.endswith('.m4a'):
                output_path = os.path.splitext(output_path)[0] + '.m4a'
            
            # Export as M4A
            audio_segment.export(output_path, format="mp4", codec="aac")
            print(f"Audio saved successfully to {output_path}")
            return True
            
        except Exception as e:
            print(f"Error generating audio with OpenAI: {str(e)}")
            return False
    
    def get_provider_name(self) -> str:
        """Get the name of the current provider"""
        return self.provider 