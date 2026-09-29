"""Enable a private OneBot HTTP endpoint for the cloud QQ cron runner."""

import json
import os
import secrets
from pathlib import Path


def configure(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    network = data.setdefault("network", {})
    servers = network.setdefault("httpServers", [])
    if not isinstance(servers, list):
        raise ValueError("OneBot httpServers 配置无效")
    for server in servers:
        if server.get("name") == "xuhuohua-local":
            if not server.get("token"):
                server["token"] = secrets.token_urlsafe(32)
                break
            return False
    else:
        servers.append({"name": "xuhuohua-local", "enable": True,
                        "host": "0.0.0.0", "port": 3000,
                        "enableCors": False, "enableWebsocket": False,
                        "messagePostFormat": "array",
                        "token": secrets.token_urlsafe(32), "debug": False})
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    configs = list((root / "qq-data/config").glob("onebot11_*.json"))
    if len(configs) != 1:
        raise SystemExit("请先扫码登录 QQ，再配置 OneBot 本机接口")
    changed = configure(configs[0])
    print("OneBot 本机接口已配置；需重启 NapCat 后生效" if changed else "OneBot 本机接口已配置")


if __name__ == "__main__":
    main()
