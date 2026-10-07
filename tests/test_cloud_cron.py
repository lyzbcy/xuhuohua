import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dedupe', ROOT / 'cloud-skill/xuhuohua-cloud/scripts/dedupe-douyin-cron.py')
dedupe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dedupe)


class CronTests(unittest.TestCase):
    def test_remove_only_this_install_douyin(self):
        root = Path('/home/test/release')
        keep = [
            'SHELL=/bin/bash',
            '* * * * * python3 /home/test/release/xuhuohua-cloud/scripts/qq-run.py',
            '0 9 * * * /another/release/douyin-auto-fire/run-cron.sh',
            '# 0 9 * * * /home/test/release/douyin-auto-fire/run-cron.sh',
            '0 9 * * * echo /home/test/release/douyin-auto-fire/run-cron.sh-extra',
            '0 9 * * * echo /home/test/release/douyin-auto-fire/run-cron.sh',
        ]
        text = '\n'.join(keep + [
            '0 9 * * * /home/test/release/douyin-auto-fire/run-cron.sh >> log 2>&1',
            "* * * * * /bin/bash '/home/test/release/xuhuohua-cloud/run-if-due.sh' '09:00' # xuhuohua-cloud-daily",
        ]) + '\n'
        self.assertEqual(dedupe.remove_entries(text, root), '\n'.join(keep) + '\n')

    def test_canonical_login_precedes_inherited_state(self):
        script = (ROOT / 'cloud-skill/xuhuohua-cloud/scripts/run-douyin.sh').read_text(encoding='utf-8')
        self.assertLess(script.index('$PWD/storage-state.json'), script.index('$here/storage-state.json'))
        self.assertIn('run.py "$@"', script)

    def test_unrelated_crontab_is_byte_for_byte_preserved(self):
        text = 'SHELL=/bin/bash\n\n# unrelated\n0 2 * * * /sbin/reboot\n\n'
        self.assertEqual(dedupe.remove_entries(text, Path('/home/test/release')), text)

    def test_headless_runner_does_not_use_login_browser(self):
        script = (ROOT / 'cloud-skill/xuhuohua-cloud/scripts/run-douyin.sh').read_text(encoding='utf-8')
        self.assertIn('douyin-headless-browser-path', script)
        self.assertNotIn('/douyin-browser-path', script)
        prepare = (ROOT / 'cloud-skill/xuhuohua-cloud/scripts/prepare-douyin.sh').read_text(encoding='utf-8')
        self.assertIn('chromium_headless_shell-$revision', prepare)
        self.assertNotIn('sort -V', prepare)


if __name__ == '__main__':
    unittest.main()
