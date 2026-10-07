"""Loopback-only HTTP server. No Beli account mutations are exposed."""
import base64
from contextlib import closing
import json
import mimetypes
import os
import sqlite3
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .store import Store, Conflict

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / 'dist'


def serve(db_path, port=8765):
    store = Store(db_path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # URLs only; never log personal request bodies.
            if args and str(args[1] if len(args)>1 else '').startswith('5'):
                super().log_message(format, *args)

        def send(self, value, status=200, content_type='application/json'):
            content = json.dumps(value).encode() if content_type == 'application/json' else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https://photos2.beliapp.cloud data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(content)

        def permitted(self):
            host = self.headers.get('Host', '').split(':')[0]
            origin = self.headers.get('Origin')
            if host not in ('127.0.0.1', 'localhost'):
                return False
            if origin:
                parsed = urlparse(origin)
                if parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.scheme != 'http':
                    return False
                if parsed.port not in (port, 5173):
                    return False
            return True

        def do_GET(self):
            if not self.permitted():
                return self.send({'error':'Local access only.'}, 403)
            path = urlparse(self.path).path
            try:
                if path == '/api/state':
                    return self.send(store.view())
                if path == '/api/exports':
                    # Only discover files in this project's export folders.
                    rows=[]
                    for f in sorted((ROOT / 'data').glob('export-*/export.json')):
                        rows.append(dict(name=f.parent.name, size=f.stat().st_size))
                    return self.send(rows)
                if path == '/api/backup':
                    with tempfile.TemporaryDirectory() as folder:
                        target=Path(folder)/'backup.sqlite3'
                        store.backup(target)
                        return self.send(target.read_bytes(), content_type='application/octet-stream')
                if path.startswith('/api/'):
                    return self.send({'error':'Not found.'}, 404)
                target = (DIST / path.lstrip('/')).resolve()
                if not target.is_relative_to(DIST.resolve()):
                    return self.send({'error':'Not found.'}, 404)
                if path == '/':
                    target = DIST / 'index.html'
                if not target.is_file():
                    return self.send({'error':'Build the frontend with npm run build first.'}, 404)
                return self.send(target.read_bytes(), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')
            except Exception:
                return self.send({'error':'Could not read local workspace.'}, 500)

        def do_POST(self):
            if not self.permitted() or self.headers.get('Content-Type') != 'application/json':
                return self.send({'error':'Only local JSON requests are accepted.'}, 403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 100*1024*1024:
                    raise ValueError('Request must be between 1 byte and 100 MB.')
                body = json.loads(self.rfile.read(size))
                path=urlparse(self.path).path
                if path == '/api/local-export':
                    name = body['name']
                    if not isinstance(name,str) or '/' in name or '\\' in name or not name.startswith('export-'):
                        raise ValueError('Choose an available export folder.')
                    folder = ROOT/'data'/name
                    if not folder.resolve().is_relative_to((ROOT/'data').resolve()):
                        raise ValueError('Invalid export folder.')
                    report = json.loads((folder/'report.json').read_text()) if (folder/'report.json').exists() else {}
                    return self.send(dict(payload=json.loads((folder/'export.json').read_text()), report=report))
                if path == '/api/preview':
                    return self.send(store.preview(body['payload'], body.get('report')))
                if path == '/api/action':
                    result=store.mutate(body)
                    return self.send({**result, 'view':store.view()})
                if path == '/api/restore-backup':
                    with tempfile.TemporaryDirectory() as folder:
                        target=Path(folder)/'restore.sqlite3'
                        target.write_bytes(base64.b64decode(body['data'], validate=True))
                        Store.validate_backup(target)
                        with store.connect() as db:
                            revision,_=store.read(db)
                            if body.get('revision') != revision:
                                raise Conflict('Workspace changed. Refresh before restoring this backup.')
                        backups=store.path.parent/'workshop-backups'
                        backups.mkdir(exist_ok=True,mode=0o700)
                        import uuid
                        store.backup(backups/f'before-restore-{uuid.uuid4()}.sqlite3')
                        # Serial server ensures no concurrent writer while replacing DB contents.
                        with closing(sqlite3.connect(target)) as source, store.connect() as destination:
                            source.backup(destination)
                            restored_revision = destination.execute('SELECT revision FROM workspace WHERE id=1').fetchone()[0]
                            destination.execute('UPDATE workspace SET revision=? WHERE id=1',(max(revision,restored_revision)+1,))
                    return self.send({'view':store.view()})
                return self.send({'error':'Not found.'},404)
            except Conflict as exc:
                return self.send({'error':str(exc)},409)
            except (ValueError, KeyError, TypeError, OSError, sqlite3.DatabaseError) as exc:
                return self.send({'error':str(exc)},400)
            except Exception:
                return self.send({'error':'Could not save the change. Your previous saved state is intact.'},500)

    server=HTTPServer(('127.0.0.1',port),Handler)
    print(f'Beli Review is ready at http://127.0.0.1:{port}', flush=True)
    print(f'Workspace: {store.path}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
