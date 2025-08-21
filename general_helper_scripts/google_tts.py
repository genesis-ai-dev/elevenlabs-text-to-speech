from pathlib import Path
import os
from google.cloud import texttospeech as tts

def main():
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        client = tts.TextToSpeechClient.from_service_account_file(credentials_path)
    else:
        client = tts.TextToSpeechClient()

    # Text you want to synthesize
    text = """
        Pada permulaan segala sesuatu,
        Dia yang disebut Firman sudah bersama dengan Allah,
        dan Firman itu sendiri adalah Allah.
    """

    # Choose a voice (leave empty for default Indonesian)
    voice = tts.VoiceSelectionParams(
        language_code="id-ID",
        name="id-ID-Standard-C",  # Change to another if needed
        ssml_gender=tts.SsmlVoiceGender.MALE
    )

    # Audio configuration
    audio_config = tts.AudioConfig(
        audio_encoding=tts.AudioEncoding.MP3,
        speaking_rate=0.9,  # 1.0 = normal speed
        pitch=-3.0          # 0.0 = normal pitch
    )

    # Input
    input_text = tts.SynthesisInput(text=text)

    # Synthesize
    response = client.synthesize_speech(
        input=input_text,
        voice=voice,
        audio_config=audio_config
    )

    # Save to file
    output_path = Path("output_id.mp3")
    output_path.write_bytes(response.audio_content)
    print(f"Audio saved to {output_path}")

if __name__ == "__main__":
    main()
