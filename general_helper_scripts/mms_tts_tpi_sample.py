import os
from pathlib import Path
from dotenv import load_dotenv
import requests
from huggingface_hub import InferenceClient

def main():
	# Load env so we can read HF token and optional custom endpoint URL
	load_dotenv(Path(__file__).resolve().parent.parent / ".env")

	text = "Dispela em wanpela eksampel long Tok Pisin."

	# Accept common token env var names
	token = (
		os.getenv("HF_TOKEN_READ")
	)
	if not token:
		raise SystemExit("Missing HF token (HF_TOKEN_READ)")

	# Prefer a custom Inference Endpoint if provided; else use public model API
	endpoint = os.getenv("HF_TTS_ENDPOINT")
	if endpoint:
		# Custom endpoint: JSON in, base64 WAV out
		resp = requests.post(endpoint, headers={"Authorization": f"Bearer {token}"}, json={"inputs": text})
		if resp.status_code != 200:
			raise SystemExit(f"Endpoint error {resp.status_code}: {resp.text[:200]}")
		data = resp.json()
		import base64
		b = base64.b64decode(data.get("audio_base64", "")) if isinstance(data, dict) else None
		if not b:
			raise SystemExit("No audio from custom endpoint")
		with open("tok_pisin.wav", "wb") as f:
			f.write(b)
		print("Saved tok_pisin.wav")
		return
	else:
		model_id = os.getenv("HF_TTS_MODEL") or "facebook/mms-tts-tpi"
		client = InferenceClient(model=model_id, token=token)

		# Use high-level helper; falls back to POST internally
		audio_bytes = client.text_to_speech(text)
		if not audio_bytes:
			raise SystemExit("No audio returned from inference API")

		with open("tok_pisin.wav", "wb") as f:
			f.write(audio_bytes)
		print("Saved tok_pisin.wav")

if __name__ == "__main__":
	main()