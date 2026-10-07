"""Create a PostgreSQL custom-format backup without shell redirection."""
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
path = args.output / ('livepulse-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.dump')
with path.open('xb') as output:
    result = subprocess.run(['docker', 'compose', '-f', 'infra/compose.yaml', 'exec', '-T',
                             'db', 'pg_dump', '-U', 'livepulse', '-d', 'livepulse', '-Fc'], stdout=output)
if result.returncode:
    path.unlink(missing_ok=True)
    raise SystemExit(result.returncode)
print(path)
