import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import nullcontext
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('auth_upgrade',ROOT/'cloud-skill/xuhuohua-cloud/scripts/upgrade-douyin-auth.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class UpgradeTests(unittest.TestCase):
    def install(self,d):
        root=Path(d)/'release';engine=root/'douyin-auto-fire'
        (root/'xuhuohua-cloud').mkdir(parents=True)
        (root/'xuhuohua-cloud/VERSION').write_text('0.14.2')
        for name in module.FILES:
            path=engine/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# old\n')
        for name in ['storage-state.json','config.json','artifacts/history.json']:
            path=engine/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('PRIVATE')
        package=Path(d)/'xuhuohua-cloud.zip'
        with zipfile.ZipFile(package,'w') as z:
            z.writestr('xuhuohua-cloud/VERSION','0.14.2')
            for name in module.FILES:z.writestr('douyin-auto-fire/'+name,'# new public code\n')
        package.with_name(package.name+'.sha256').write_text(hashlib.sha256(package.read_bytes()).hexdigest()+'  '+package.name)
        return root,package

    def test_only_public_code_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root,package=self.install(d)
            with patch.object(module,'idle_engine',return_value=nullcontext()):report=module.upgrade(root,package)
            self.assertEqual(report['version'],'0.14.2')
            for name in module.FILES:self.assertEqual((root/'douyin-auto-fire'/name).read_text(),'# new public code\n')
            for name in ['storage-state.json','config.json','artifacts/history.json']:
                self.assertEqual((root/'douyin-auto-fire'/name).read_text(),'PRIVATE')

    def test_checksum_failure_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root,package=self.install(d);package.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):module.upgrade(root,package)
            self.assertEqual((root/'douyin-auto-fire/app/main.py').read_text(),'# old\n')

    def test_busy_engine_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root,package=self.install(d)
            with patch.object(module,'idle_engine',side_effect=RuntimeError('busy')):
                with self.assertRaises(RuntimeError):module.upgrade(root,package)
            self.assertEqual((root/'douyin-auto-fire/app/main.py').read_text(),'# old\n')

    def test_partial_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            root,package=self.install(d);real=module.replace;count=0
            def fail_second(*args,**kwargs):
                nonlocal count
                count+=1
                if count==2:raise OSError('disk full')
                return real(*args,**kwargs)
            with patch.object(module,'idle_engine',return_value=nullcontext()),patch.object(module,'replace',side_effect=fail_second):
                with self.assertRaises(OSError):module.upgrade(root,package)
            for name in module.FILES:self.assertEqual((root/'douyin-auto-fire'/name).read_text(),'# old\n')
