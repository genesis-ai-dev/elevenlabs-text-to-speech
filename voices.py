from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
import os

load_dotenv()

api_key=os.getenv('ELEVENLABS_API_KEY')

client = ElevenLabs(
  api_key=api_key,
)

response = client.voices.get_all()
voice_names = [voice.name for voice in response.voices]
print(voice_names)