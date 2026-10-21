"""One-time recovery from the preserved read-only copy to fresh local storage.

Never modifies .mysql-data. Requires the manually prepared read-only copy.
Full logical backup and before/after table fingerprints are saved privately.
"""
import gzip
import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import pymysql
from dotenv import dotenv_values
from local_mysql import ROOT, STATE

OUT = ROOT / 'backups/migration-20261021'
BIN = Path(r'D:\Software\Env\mysql8\bin')


def fingerprints(config, schema):
    result = {}
    with pymysql.connect(**config, database=schema, charset='utf8mb4') as conn:
        with conn.cursor() as c:
            c.execute('SHOW TABLES'); tables = [r[0] for r in c.fetchall()]
        for table in tables:
            digest = hashlib.sha256(); count = 0
            with conn.cursor() as c:
                c.execute('SHOW INDEX FROM `'+table+"` WHERE Key_name='PRIMARY'")
                keys = [r[4] for r in c.fetchall()]
                if not keys: raise RuntimeError('No deterministic primary key in '+table)
                c.execute('SELECT * FROM `'+table+'` ORDER BY '+','.join('`'+k+'`' for k in keys))
                for row in c:
                    digest.update((json.dumps(row,default=str,ensure_ascii=False,separators=(',',':'))+'\n').encode())
                    count += 1
            result[table] = {'rows':count,'sha256':digest.hexdigest()}
    return result


def main():
    cfg = dotenv_values(ROOT/'backend/.env')
    if (cfg['DB_HOST'],cfg['DB_PORT'],cfg['DB_NAME']) != ('127.0.0.1','3307','finance'):
        raise RuntimeError('This recovery only handles the confirmed local development database')
    newdata = ROOT/'.mysql-dev-data'
    if STATE.exists() or newdata.exists(): raise RuntimeError('Fresh recovery destination already exists; refusing overwrite')
    oldroot = dict(host='127.0.0.1',port=3307,user='root',password='')
    with pymysql.connect(**oldroot) as c:
        with c.cursor() as q:
            q.execute('SELECT @@datadir,@@super_read_only'); directory,readonly = q.fetchone()
            if Path(directory).resolve() != (OUT/'dev-cold-copy').resolve() or not readonly:
                raise RuntimeError('Expected read-only recovery copy')
    before = fingerprints(oldroot,'finance')
    flags = ['--no-defaults','--host=127.0.0.1','--port=3307','--user=root','--default-character-set=utf8mb4']
    backup = OUT/'development-before-recovery.sql.gz'
    if backup.exists(): raise RuntimeError('Recovery backup exists; refusing overwrite')
    with (OUT/'development-dump.log').open('wb') as log:
        process = subprocess.Popen([str(BIN/'mysqldump.exe'),*flags,'--single-transaction','--quick',
                                    '--no-tablespaces','--set-gtid-purged=OFF','--routines','--events','--triggers','--hex-blob','finance'],stdout=subprocess.PIPE,stderr=log)
        with gzip.open(backup,'wb') as stream:
            for block in iter(lambda:process.stdout.read(1024*1024),b''): stream.write(block)
        if process.wait(): raise RuntimeError('Development backup failed; recovery copy retained')
    subprocess.run([str(BIN/'mysqladmin.exe'),*flags[:4],'shutdown'],check=True)
    newdata.mkdir()
    with (OUT/'development-initialize.log').open('wb') as log:
        subprocess.run([str(BIN/'mysqld.exe'),'--no-defaults',f'--datadir={newdata}','--initialize-insecure','--console'],stdout=log,stderr=log,check=True)
    command = [str(BIN/'mysqld.exe'),'--no-defaults',f'--datadir={newdata}','--port=3307','--bind-address=127.0.0.1',
               '--mysqlx=OFF','--event-scheduler=OFF','--innodb-undo-log-truncate=OFF','--innodb-buffer-pool-size=128M',
               '--innodb-redo-log-capacity=128M','--max-connections=30','--console']
    with (newdata/'console.log').open('ab') as log:
        proc = subprocess.Popen(command,cwd=newdata,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(100):
        try:
            connection = pymysql.connect(**oldroot,autocommit=True); break
        except pymysql.OperationalError:
            if proc.poll() is not None: raise RuntimeError('Fresh development instance failed; backup retained')
            time.sleep(.25)
    else: raise RuntimeError('Fresh instance readiness timed out')
    password = secrets.token_urlsafe(32)
    with connection.cursor() as c:
        c.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s",[password])
        c.execute('CREATE DATABASE finance CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        for host in ['localhost','127.0.0.1']:
            c.execute('CREATE USER %s@%s IDENTIFIED BY %s',[cfg['DB_USER'],host,cfg['DB_PASSWORD']])
            for schema in ['finance','test_finance']:c.execute('GRANT ALL ON `'+schema+'`.* TO %s@%s',[cfg['DB_USER'],host])
        c.execute('SELECT @@server_uuid'); uuid = c.fetchone()[0]
    connection.close()
    root = dict(oldroot,password=password)
    STATE.write_text(json.dumps(dict(root=root,uuid=uuid,data_dir=str(newdata),command=command,pid=proc.pid),indent=2),encoding='utf8')
    with (OUT/'development-restore.log').open('wb') as log:
        restore = subprocess.Popen([str(BIN/'mysql.exe'),*flags,'--binary-mode=1','finance'],stdin=subprocess.PIPE,stderr=log,env=dict(os.environ,MYSQL_PWD=password))
        with gzip.open(backup,'rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):restore.stdin.write(block)
        restore.stdin.close()
        if restore.wait():raise RuntimeError('Development restore failed; backup and original retained')
    after = fingerprints(root,'finance')
    report = dict(passed=before==after,tables=len(before),rows=sum(v['rows'] for v in before.values()),
                  before=before,after=after,backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
                  original_directory_unchanged=True,recovery_method='Read-only copied datadir with copied undo preserved separately; fresh logical restore. Original corruption history is not proven.')
    (OUT/'development-recovery.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if before!=after:raise RuntimeError('Restored development database differs from recovery copy')
    print(json.dumps({k:report[k] for k in ['passed','tables','rows','original_directory_unchanged']}))


if __name__ == '__main__':main()
