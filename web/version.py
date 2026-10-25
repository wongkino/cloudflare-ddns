import os
from pathlib import Path


def app_version():
    # 建置時寫入的版本優先。本機沒有這個值時讀 VERSION，再不然顯示 dev。
    override = os.environ.get("APP_VERSION", "").strip()
    if override:
        return override
    source = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        baked = source.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        baked = ""
    return baked or "dev"
