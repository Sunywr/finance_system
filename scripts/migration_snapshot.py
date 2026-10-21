"""Export a fresh consistent production backup over an existing authorized SSH route.

The database is never modified. Shared metadata locks prevent table DDL.
Private output belongs under backups/; credentials stay in the server config.
"""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

REMOTE = r"""
import datetime as dt, gzip, hashlib, json, os, subprocess, sys, tomllib
from pathlib import Path
from urllib.parse import urlsplit, unquote
run=sys.argv[1]
if not run.replace('-', '').isalnum(): raise RuntimeError('Invalid run')
directory=Path('/projects/ffs/backups')/('finance-migration-'+run)
directory.mkdir(mode=0o700, exist_ok=True)
u=urlsplit(tomllib.loads(Path('/projects/ffs/ffs.toml').read_text())['database']['url'])
if u.query not in ('','charset=utf8mb4'): raise RuntimeError('Unsupported connection options')
database=unquote(u.path.lstrip('/'))
flags=['--no-defaults','--host='+str(u.hostname),'--port='+str(u.port or 3306),'--user='+unquote(u.username or ''),'--default-character-set=utf8mb4']
env=dict(os.environ,MYSQL_PWD=unquote(u.password or ''))
def query(sql):
 p=subprocess.run(['mysql',*flags,'--batch','--raw','--skip-column-names',database,'--execute',sql],env=env,capture_output=True,timeout=30)
 if p.returncode: raise RuntimeError('MySQL metadata/lock operation failed')
 return p.stdout.decode().strip()
dest=directory/'database.sql.gz'
manifest=directory/'manifest.json'
if dest.exists():
 if not manifest.exists(): raise RuntimeError('Backup lacks completion manifest')
 print(manifest.read_text());sys.exit(0)
identity=query('SELECT @@server_uuid,@@version,DATABASE(),@@hostname,@@global.time_zone')
schema_sql="SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COALESCE(COLUMN_DEFAULT,''),EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION"
schema=query(schema_sql)
tables=query("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME").splitlines()
if any(not t.replace('_','').isalnum() for t in tables):raise RuntimeError('Unsupported table identifier')
lock_command=['mysql',*flags,'--batch','--unbuffered','--skip-column-names',database]
lock=subprocess.Popen(lock_command,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
try:
 lock_sql='SET SESSION lock_wait_timeout=10; SET TRANSACTION READ ONLY; START TRANSACTION; '+''.join('SELECT * FROM `'+t+'` LIMIT 0;' for t in tables)+"SELECT 'backup-lock-ready';\n"
 lock.stdin.write(lock_sql.encode());lock.stdin.flush()
 if lock.stdout.readline().strip()!=b'backup-lock-ready': raise RuntimeError('BACKUP_ADMIN lock unavailable; no export performed')
 options=['--single-transaction','--quick','--hex-blob','--no-tablespaces','--set-gtid-purged=OFF','--column-statistics=0','--routines','--events','--triggers']
 started=dt.datetime.now(dt.timezone.utc).isoformat()
 raw_hash=hashlib.sha256();raw_bytes=0
 with (directory/'dump.log').open('wb') as log:
  p=subprocess.Popen(['mysqldump',*flags,*options,database],env=env,stdout=subprocess.PIPE,stderr=log)
  try:
   with (directory/'database.partial').open('xb') as h,gzip.GzipFile(filename='',fileobj=h,mode='wb',compresslevel=1,mtime=0) as z:
    while True:
     block=p.stdout.read(1024*1024)
     if not block: break
     raw_hash.update(block);raw_bytes+=len(block);z.write(block)
   if p.wait(): raise RuntimeError('mysqldump failed; private dump log retained')
  finally:
   if p.poll() is None: p.kill();p.wait()
 if query(schema_sql)!=schema: raise RuntimeError('Schema changed during export')
 (directory/'database.partial').rename(dest)
 sha=hashlib.sha256()
 with dest.open('rb') as h:
  for b in iter(lambda:h.read(1024*1024),b''):sha.update(b)
 result=dict(run=run,identity=identity,database=database,started_at=started,finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),options=options,backup_lock='shared table metadata locks; concurrent DML allowed',sha256=sha.hexdigest(),raw_sha256=raw_hash.hexdigest(),raw_bytes=raw_bytes,bytes=dest.stat().st_size,remote_path=str(dest),schema_sha256=hashlib.sha256(schema.encode()).hexdigest())
 manifest.write_text(json.dumps(result,indent=2));os.chmod(manifest,0o600);os.chmod(dest,0o600)
 print(json.dumps(result))
finally:
 if lock.poll() is None:
  try:lock.stdin.write(b'ROLLBACK;\nquit\n');lock.stdin.flush();lock.communicate(timeout=10)
  except Exception:lock.kill();lock.wait()
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ssh-config", required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    ssh = ["ssh", "-F", args.ssh_config, "-o", "StrictHostKeyChecking=yes", args.host]
    print("Exporting a new production snapshot under a backup lock...", flush=True)
    response = subprocess.run(
        ssh + ["python3", "-", args.run],
        input=REMOTE.encode(),
        capture_output=True,
        timeout=1800,
    )
    if response.returncode:
        raise RuntimeError(
            "Production export failed: "
            + response.stderr.decode(errors="replace")[-1000:]
        )
    manifest = json.loads(response.stdout)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf8"
    )
    # Bounded resumable chunks avoid restarting a large transfer after a reset.
    chunk = 8 * 1024 * 1024
    partial = args.output / "database.sql.gz.partial"
    complete = args.output / "database.sql.gz"
    if not complete.exists():
        offset = partial.stat().st_size if partial.exists() else 0
        if offset % chunk:
            with partial.open("r+b") as h:
                h.truncate(offset - offset % chunk)
            offset -= offset % chunk
        with partial.open("ab") as h:
            for start in range(offset, manifest["bytes"], chunk):
                expected = min(chunk, manifest["bytes"] - start)
                for attempt in range(4):
                    p = subprocess.run(
                        ssh
                        + [
                            f"dd if='{manifest['remote_path']}' bs={chunk} skip={start//chunk} count=1 status=none"
                        ],
                        capture_output=True,
                        timeout=120,
                    )
                    if p.returncode == 0 and len(p.stdout) == expected:
                        h.write(p.stdout)
                        h.flush()
                        break
                    if attempt == 3:
                        raise RuntimeError(
                            "Backup transfer incomplete; rerun to resume"
                        )
                    time.sleep(2)
                print(
                    f'Downloaded {start+expected}/{manifest["bytes"]} bytes', flush=True
                )
        partial.rename(complete)
    sha = hashlib.sha256()
    with complete.open("rb") as h:
        for b in iter(lambda: h.read(1024 * 1024), b""):
            sha.update(b)
    if sha.hexdigest() != manifest["sha256"]:
        raise RuntimeError("Backup checksum mismatch")
    print("Verified local backup SHA-256: " + sha.hexdigest(), flush=True)


if __name__ == "__main__":
    main()
