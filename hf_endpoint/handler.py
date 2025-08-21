import os
os.environ["TRANSFORMERS_NO_TORCHVISION"] = "1"

import base64
import io
from typing import Any, Dict

import numpy as np
import scipy.io.wavfile as wavfile
import torch
from transformers import VitsModel, AutoTokenizer


class EndpointHandler:
	def __init__(self, path: str = "") -> None:
		# Load model/tokenizer once at startup
		self.model = VitsModel.from_pretrained("facebook/mms-tts-tpi")
		self.tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-tpi")
		self.sampling_rate = int(self.model.config.sampling_rate)
		self.model.eval()

	def __call__(self, data: Dict[str, Any]) -> Dict[str, Any]:
		# Accept either {"inputs": "..."} or {"text": "..."}
		text = data.get("inputs") or data.get("text") or ""
		if not isinstance(text, str) or not text.strip():
			return {"error": "Missing 'inputs' text"}

		inputs = self.tokenizer(text, return_tensors="pt")
		with torch.no_grad():
			waveform = self.model(**inputs).waveform  # (1, num_samples)

		audio = waveform.squeeze(0).cpu().numpy().astype(np.float32)
		buf = io.BytesIO()
		wavfile.write(buf, rate=self.sampling_rate, data=audio)
		audio_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
		return {"audio_base64": audio_b64, "sampling_rate": self.sampling_rate}
