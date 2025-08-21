import os
from dotenv import load_dotenv
import sys
from huggingface_hub import HfApi, create_repo, upload_file
from dotenv import load_dotenv
from pathlib import Path


def main() -> None:
	load_dotenv(Path(__file__).resolve().parent.parent / ".env")
	load_dotenv()
	# Token from env
	token = os.getenv("HF_TOKEN_WRITE")
	if not token:
		raise SystemExit("Set HF_TOKEN_WRITE before running.")

	api = HfApi(token=token)
	namespace = os.environ.get("HF_NAMESPACE") or api.whoami(token=token)["name"]
	repo_name = os.environ.get("HF_REPO_NAME", "mms-tts-tpi-endpoint")
	repo_id = f"{namespace}/{repo_name}"

	# Create (idempotent) as a model repo (required for Inference Endpoints)
	create_repo(repo_id=repo_id, private=True, exist_ok=True, token=token, repo_type="model")

	# Upload required files for the endpoint handler
	files = {
		"hf_endpoint/handler.py": "handler.py",
		"hf_endpoint/requirements.txt": "requirements.txt",
	}
	for local_path, path_in_repo in files.items():
		if not os.path.exists(local_path):
			raise SystemExit(f"Missing file: {local_path}")
		upload_file(
			path_or_fileobj=local_path,
			path_in_repo=path_in_repo,
			repo_id=repo_id,
			token=token,
			repo_type="model",
		)

	print(f"Uploaded to https://huggingface.co/{repo_id}")
	print("In Inference Endpoints: create endpoint -> Container Type: Default, Task: Custom, Repository: this repo.")


if __name__ == "__main__":
	main()


