# -*- coding: utf-8 -*-
"""Windows 子进程工具：统一处理 GBK/UTF-8 输出编码 + 不闪黑框。
软件用 pythonw（无控制台）启动，子进程若不设 CREATE_NO_WINDOW 会各自弹黑框。
"""
import subprocess

CREATE_NO_WINDOW = 0x08000000


def decode_bytes(b) -> str:
    if b is None:
        return ""
    if isinstance(b, str):
        return b
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def run_cmd(args, timeout=20, cwd=None, env=None):
    """运行命令并安全解码输出（Windows 控制台程序多为 GBK）。不弹窗口。"""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, cwd=cwd,
                           env=env, creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "命令超时（{0}s）".format(timeout))
    except OSError as exc:
        return subprocess.CompletedProcess(args, 1, "", "命令不可用: {0}".format(exc))
    r.stdout = decode_bytes(r.stdout)
    r.stderr = decode_bytes(r.stderr)
    return r
