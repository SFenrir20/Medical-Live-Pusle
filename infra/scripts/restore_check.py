"""Restore a dump only into a NEW isolated database; never overwrite the application DB."""
import argparse
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('backup', type=Path)
parser.add_argument('--database', required=True)
args = parser.parse_args()
if not re.fullmatch(r'livepulse_restore_[a-z0-9_]{1,32}', args.database):
    parser.error('Use a NEW database named livepulse_restore_<test_name>')
base = ['docker', 'compose', '-f', 'infra/compose.yaml', 'exec', '-T', 'db']
subprocess.run(base + ['createdb', '-U', 'livepulse', args.database], check=True)
with args.backup.open('rb') as source:
    subprocess.run(base + ['pg_restore', '-U', 'livepulse', '-d', args.database,
                           '--no-owner', '--exit-on-error', '--single-transaction'], stdin=source, check=True)
subprocess.run(base + ['psql', '-U', 'livepulse', '-d', args.database, '-v', 'ON_ERROR_STOP=1',
                       '-c', 'SELECT version_num FROM alembic_version; SELECT count(*) FROM shifts;'], check=True)
print('Verified isolated restore:', args.database)
