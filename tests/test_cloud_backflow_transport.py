"""Isolated transport failures must never let rsync overwrite unchecked files."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def test_backflow_stops_before_copy_when_remote_inventory_fails(tmp_path):
    root = tmp_path / 'project'
    (root / 'scripts').mkdir(parents=True)
    script = root / 'scripts/sync_cloud_back_to_local.sh'
    shutil.copyfile(Path(__file__).parents[1] / 'scripts/sync_cloud_back_to_local.sh', script)
    vault = tmp_path / 'vault'
    (vault / 'wiki').mkdir(parents=True)
    original = vault / 'wiki/private.md'
    original.write_text('local original')
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    log = tmp_path / 'calls.jsonl'
    fake = '''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as f: f.write(json.dumps([os.path.basename(sys.argv[0]), *sys.argv[1:]])+'\\n')
if '-O' in sys.argv: sys.exit(0)
sys.exit(255 if os.path.basename(sys.argv[0]) == 'ssh' else 0)
'''
    for name in ('ssh', 'scp', 'rsync'):
        path = binaries / name
        path.write_text(fake)
        path.chmod(0o755)
    env = {**os.environ, 'PATH': str(binaries) + ':' + os.environ['PATH'],
           'SERVER_HOST': 'isolated.invalid', 'LOCAL_VAULT_PATH': str(vault),
           'CALL_LOG': str(log), 'SYNC_SSH_KEY': str(tmp_path / 'test key')}
    result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert original.read_text() == 'local original'
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(call[0] == 'ssh' for call in calls)
    assert 'BatchMode=yes' in calls[0] and 'ConnectionAttempts=3' in calls[0]
    control = next(arg.split('=', 1)[1] for arg in calls[0] if arg.startswith('ControlPath='))
    assert not Path(control).parent.exists()
    receipts = list((vault / 'raw/sync_receipts').glob('*.json'))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())['status'] == 'failed'


def test_backflow_quarantines_conflict_and_imports_new_file(tmp_path):
    root = tmp_path / 'project'
    (root / 'scripts').mkdir(parents=True)
    (root / 'data').mkdir()
    (root / 'data/knowledge_matrix.json').write_text('{}')
    script = root / 'scripts/sync_cloud_back_to_local.sh'
    shutil.copyfile(Path(__file__).parents[1] / 'scripts/sync_cloud_back_to_local.sh', script)
    local, remote = tmp_path / 'local', tmp_path / 'remote'
    for vault in (local, remote):
        for directory in ('raw', 'wiki', '访客画像'):
            (vault / directory).mkdir(parents=True)
    (local / 'wiki/shared.md').write_text('keep local')
    (remote / 'wiki/shared.md').write_text('server changed')
    (remote / 'wiki/new.md').write_text('new server result')
    (remote / 'knowledge_matrix.json').write_text('{}')
    # Remote is newer: --update alone would destroy the local version.
    os.utime(local / 'wiki/shared.md', (100, 100))
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    fake = '''#!/usr/bin/env python3
import os, shutil, subprocess, sys
args = sys.argv[1:]
if '-O' in args: sys.exit(0)
while args and args[0].startswith('-'):
    args = args[2:] if args[0] in ('-o', '-i') else args[1:]
if os.path.basename(sys.argv[0]) == 'scp':
    shutil.copyfile(args[0].split(':', 1)[1], args[1]); sys.exit(0)
args = args[1:]
if len(args) == 1: sys.exit(subprocess.call(['bash', '-c', args[0]]))
os.execvp(args[0], args)
'''
    for name in ('ssh', 'scp'):
        path = binaries / name
        path.write_text(fake)
        path.chmod(0o755)
    env = {**os.environ, 'PATH': str(binaries) + ':' + os.environ['PATH'],
           'SERVER_HOST': 'isolated.invalid', 'SERVER_VAULT_PATH': str(remote),
           'LOCAL_VAULT_PATH': str(local), 'SYNC_SSH_KEY': ''}
    result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert (local / 'wiki/shared.md').read_text() == 'keep local'
    assert (local / 'wiki/new.md').read_text() == 'new server result'
    assert next((local / 'raw/待合并').glob('*/shared.server.md')).read_text() == 'server changed'
    receipts = list((local / 'raw/sync_receipts').glob('*.json'))
    assert json.loads(receipts[0].read_text())['status'] == 'quarantined_conflict'
