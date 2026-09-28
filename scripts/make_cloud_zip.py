"""Build the public, credential-free cloud release asset and its checksum."""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))
from backend.cloud import EXPORT_NAME, export_bundle, prompt  # noqa: E402


def main() -> None:
    result = export_bundle()
    if not result.get("ok"):
        raise SystemExit(result.get("msg", "云端包构建失败"))
    package = ROOT / EXPORT_NAME
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    checksum = ROOT / (EXPORT_NAME + ".sha256")
    checksum.write_bytes(f"{digest}  {EXPORT_NAME}\n".encode("ascii"))
    (ROOT / "xuhuohua-cloud-prompt.txt").write_bytes((prompt() + "\n").encode("utf-8"))
    print(f"CLOUD_RELEASE_OK {package.name} files={result['files']} sha256={digest}")


if __name__ == "__main__":
    main()
