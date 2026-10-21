"""Start/stop the recorded local development MySQL without deleting storage files."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.mysql-local-state.json'


def connect(state):
    connection = pymysql.connect(**state['root'], connect_timeout=3)
    with connection.cursor() as c:
        c.execute('SELECT @@server_uuid,@@datadir')
        uuid, directory = c.fetchone()
    if uuid != state['uuid'] or Path(directory).resolve() != Path(state['data_dir']).resolve():
        connection.close()
        raise RuntimeError('Development MySQL identity mismatch')
    return connection


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['start', 'stop', 'status'])
    a = p.parse_args()
    if not STATE.exists():
        raise RuntimeError('No recorded local instance. Initialize or recover it first; existing files will not be deleted.')
    state = json.loads(STATE.read_text(encoding='utf8'))
    try:
        conn = connect(state)
    except pymysql.OperationalError:
        if a.action != 'start':
            print('Local development MySQL is stopped'); return
        command = state['command']
        data = Path(state['data_dir']).resolve()
        if not data.is_relative_to(ROOT) or '--bind-address=127.0.0.1' not in command or '--event-scheduler=OFF' not in command:
            raise RuntimeError('Invalid recorded development launch command')
        with (data/'console.log').open('ab') as log:
            process = subprocess.Popen(command, cwd=data, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for _ in range(120):
            try:
                conn = connect(state); break
            except pymysql.OperationalError:
                if process.poll() is not None: raise RuntimeError('MySQL startup failed; storage preserved; inspect console.log')
                time.sleep(.25)
        else: raise RuntimeError('MySQL startup timed out; storage preserved')
        state['pid'] = process.pid
        STATE.write_text(json.dumps(state, indent=2), encoding='utf8')
    if a.action == 'stop':
        conn.close()
        binary = Path(state['command'][0]).with_name('mysqladmin.exe')
        subprocess.run([str(binary),'--no-defaults','--host=127.0.0.1',f'--port={state["root"]["port"]}',
                        '--user=root','shutdown'], env=dict(os.environ,MYSQL_PWD=state['root']['password']),check=True)
        print('Local development MySQL stopped; all storage retained')
    else:
        conn.close(); print(f'Local development MySQL ready on 127.0.0.1:{state["root"]["port"]}')


if __name__ == '__main__': main()
