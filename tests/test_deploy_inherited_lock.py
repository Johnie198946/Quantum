"""Real Linux flock behavior; deployment lock tests run on the target OS."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == 'linux', 'production uses Linux flock and /proc')
class DeploymentLockTest(unittest.TestCase):
    def test_inherited_lock_cannot_bypass_exclusion(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts/update.sh').read_text()
        block = source[source.index('# An offline image preparer'):source.index('# Re-read the active release')]
        with tempfile.TemporaryDirectory() as directory:
            lock = str(Path(directory) / 'deploy.lock')
            block = block.replace('/run/lock/ai-lab-platform-update.lock', lock)
            cases = {
                'inherited': ('exec 8>' + shlex.quote(lock) + '; flock -n 8; export AI_LAB_DEPLOY_LOCK_FD=8;', True),
                'foreign': ('exec 8>' + shlex.quote(lock + '.other') + '; export AI_LAB_DEPLOY_LOCK_FD=8;', False),
                'missing': ('export AI_LAB_DEPLOY_LOCK_FD=8;', False),
                'invalid': ('export AI_LAB_DEPLOY_LOCK_FD=7;', False),
                'busy': ('exec 8>' + shlex.quote(lock) + '; flock -n 8; unset AI_LAB_DEPLOY_LOCK_FD;', False),
                'free': ('unset AI_LAB_DEPLOY_LOCK_FD;', True),
            }
            for name, (prefix, expected) in cases.items():
                with self.subTest(name=name):
                    result = subprocess.run(['bash', '-c', prefix + ' bash -c ' + shlex.quote('set -e\n' + block)],
                                            env=os.environ.copy(), capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode == 0, expected, result.stderr)


if __name__ == '__main__':
    unittest.main()
