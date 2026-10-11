"""Generate a YouTube OAuth token for GTA Oculto AI.

Run locally on your Windows PC:
  1) Put your Google OAuth Desktop client file beside this script as client_secret.json.
  2) Run: python oauth_youtube.py
  3) Sign in with the YouTube channel account and approve access.
  4) Copy the printed YOUTUBE_TOKEN_JSON value into Render Environment.

The token includes both upload and YouTube Analytics read-only scopes so the
same credential can publish Shorts and feed the learning engine.
"""
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
BASE = Path(__file__).resolve().parent
CLIENT = BASE / "client_secret.json"
TOKEN = BASE / "youtube_token.json"

if not CLIENT.exists():
    raise SystemExit(
        "ERRO: client_secret.json não encontrado. Baixe o OAuth Client "
        "do Google Cloud (tipo Desktop app) e coloque o arquivo nesta pasta."
    )

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

data = json.loads(creds.to_json())
TOKEN.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

print("\nOK — OAuth do YouTube concluído.")
print(f"Arquivo salvo: {TOKEN}")
print("\nNo Render, configure:")
print("YOUTUBE_AUTO_PUBLISH=1")
print("YOUTUBE_ANALYTICS_ENABLED=1")
print("YOUTUBE_PRIVACY=private   # primeiro teste")
print("\nYOUTUBE_TOKEN_JSON (uma linha):")
print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
