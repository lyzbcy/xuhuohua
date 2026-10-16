"""Apply verified public auth files to an idle existing cloud installation."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

FILES = ('app/auth_state.py', 'app/main.py', 'scripts/login.py')


@contextmanager
def idle_engine(root):
    import fcntl
    lock_path = root/'douyin-auto-fire/artifacts/run.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('任务或登录正在运行，请等待结束后升级') from None
        yield


def replace(path, data, owner=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.auth-upgrade-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            os.chmod(name, 0o644)
            if owner and hasattr(os,'chown'): os.chown(name,owner.st_uid,owner.st_gid)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def upgrade(root, package):
    package = Path(package)
    parts = package.with_name(package.name+'.sha256').read_text().split()
    payload = package.read_bytes()
    if len(parts) != 2 or parts[1] != package.name or hashlib.sha256(payload).hexdigest() != parts[0]:
        raise ValueError('云端包校验失败')
    with zipfile.ZipFile(package) as archive:
        version = archive.read('xuhuohua-cloud/VERSION').decode().strip()
        if version != (root/'xuhuohua-cloud/VERSION').read_text().strip():
            raise ValueError('请先升级 Skill 到同一 Release 版本')
        files = {name:archive.read('douyin-auto-fire/'+name) for name in FILES}
        for name,data in files.items(): compile(data,name,'exec')
    engine = root/'douyin-auto-fire'
    with idle_engine(root):
        # Only these public files may change. All config, history, profiles and
        # credentials remain untouched, including other Douyin applications.
        backup = root/'auth-upgrade-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True,mode=0o700)
        before = {}
        for name in FILES:
            dest = engine/name
            before[name] = (dest.read_bytes(),dest.stat()) if dest.exists() else None
            if dest.exists():
                copy = backup/name; copy.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(dest,copy)
        try:
            owner = (engine/'app/main.py').stat()
            for name,data in files.items(): replace(engine/name,data,owner)
        except Exception:
            for name,old in before.items():
                if old: replace(engine/name,old[0],old[1])
                else: (engine/name).unlink(missing_ok=True)
            raise
        report = {'version':version,'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
        (backup/'manifest.json').write_text(json.dumps(report,indent=2))
    return report


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('package',type=Path,help='已下载的 xuhuohua-cloud.zip（旁边须有 .sha256）')
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[2]
    try:
        print(json.dumps({'ok':True, **upgrade(root,args.package)},ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__},ensure_ascii=False))
        raise SystemExit(1)
