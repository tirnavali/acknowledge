"""
One-time model download script for corporate networks with MITM SSL proxies.
Downloads Qwen2.5-VL-3B-Instruct to ./models/Qwen2.5-VL-3B-Instruct

Usage:
    python download_model.py

After this completes, app.py will load the model from disk automatically.
"""
import ssl
import sys

# Patch SSL BEFORE importing anything that touches the network
ssl._create_default_https_context = ssl._create_unverified_context

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Patch Session.__init__ so EVERY session created by ANY library starts with verify=False.
# This covers huggingface_hub regardless of version (no configure_http_backend needed).
_orig_session_init = requests.Session.__init__
def _patched_session_init(self, *args, **kwargs):
    _orig_session_init(self, *args, **kwargs)
    self.verify = False
requests.Session.__init__ = _patched_session_init

# huggingface_hub must be imported AFTER the patch
from huggingface_hub import snapshot_download

LOCAL_DIR = "./models/Qwen2.5-VL-3B-Instruct"
MODEL_ID  = "Qwen/Qwen2.5-VL-3B-Instruct"

print(f"Downloading {MODEL_ID} → {LOCAL_DIR}")
print("Bu işlem internet bağlantı hızınıza göre birkaç dakika sürebilir (~3 GB)...")

try:
    path = snapshot_download(MODEL_ID, local_dir=LOCAL_DIR)
    print(f"\n✅ Model indirildi: {path}")
    print("Artık app.py'yi başlatabilirsiniz — model diskten yüklenecek.")
except Exception as e:
    print(f"\n❌ İndirme başarısız: {e}", file=sys.stderr)
    sys.exit(1)
