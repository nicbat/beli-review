"""Start the local app; install/build the frontend on first launch."""
import argparse
import os
import subprocess
from pathlib import Path
from app.backend.server import serve

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description='Run Beli Review locally.')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--db',type=Path,default=ROOT/'data'/'workshop.sqlite3')
    parser.add_argument('--no-build',action='store_true',help='Use an already built frontend.')
    args=parser.parse_args()
    os.umask(0o077)
    if not args.no_build:
        if not (ROOT/'node_modules').exists():
            subprocess.run(['npm','ci'],cwd=ROOT,check=True)
        sources=list((ROOT/'app'/'frontend').rglob('*.tsx'))+list((ROOT/'app'/'frontend').rglob('*.css'))
        sources += [ROOT/'package-lock.json',ROOT/'vite.config.mjs',ROOT/'app'/'frontend'/'index.html']
        index=ROOT/'dist'/'index.html'
        if not index.exists() or any(p.stat().st_mtime > index.stat().st_mtime for p in sources):
            subprocess.run(['npm','run','build'],cwd=ROOT,check=True)
    serve(args.db.resolve(),args.port)

if __name__=='__main__':
    main()
