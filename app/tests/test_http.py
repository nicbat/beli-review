"""Exercise the actual HTTP boundary and backup replacement on a disposable DB."""
import base64
import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from test_workshop import fixture


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        cls.base=f'http://127.0.0.1:{port}'
        root=Path(__file__).resolve().parents[2]
        cls.process=subprocess.Popen([sys.executable,'run.py','--no-build','--port',str(port),'--db',str(Path(cls.temp.name)/'workspace.sqlite3')],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urllib.request.urlopen(cls.base+'/api/state',timeout=.2):break
            except (OSError,urllib.error.URLError):time.sleep(.05)
        else:raise RuntimeError('Test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=5);cls.temp.cleanup()

    def request(self,path,body=None,headers=None):
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(self.base+path,data=data,headers={'Content-Type':'application/json',**(headers or {})})
        with urllib.request.urlopen(req) as response:return response.read()

    def state(self):return json.loads(self.request('/api/state'))

    def act(self,action,**fields):
        return json.loads(self.request('/api/action',dict(action=action,category='RES',revision=self.state()['revision'],operation_id=str(uuid.uuid4()),**fields)))

    def test_backup_restore_and_revision_guard(self):
        self.act('import',payload=fixture())
        self.act('start')
        before=self.state()
        backup=self.request('/api/backup')
        self.act('place',key='RES:1',attention=True)
        response=json.loads(self.request('/api/restore-backup',dict(data=base64.b64encode(backup).decode(),revision=self.state()['revision'])))
        self.assertEqual(response['view']['state'],before['state'])
        self.assertGreater(response['view']['revision'],before['revision'])
        self.assertEqual(len(list((Path(self.temp.name)/'workshop-backups').glob('*.sqlite3'))),1)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/action',dict(action='place',key='RES:1',attention=True,category='RES',revision=0,operation_id='stale'))
        self.assertEqual(error.exception.code,409)
        error.exception.close()

    def test_reject_remote_origin_and_host(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/action',{}, {'Origin':'https://unrelated.example'})
        self.assertEqual(error.exception.code,403);error.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/state',headers={'Host':'unrelated.example'})
        self.assertEqual(error.exception.code,403);error.exception.close()

    def test_reject_invalid_backup(self):
        before=self.state()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/restore-backup',dict(data=base64.b64encode(b'not a database').decode(),revision=before['revision']))
        self.assertEqual(error.exception.code,400);error.exception.close()
        self.assertEqual(self.state(),before)
