#!/usr/bin/python3
"""Root-only local backup; SQLite snapshot stays consistent while the app runs."""
import os
import sqlite3
import tarfile
import tempfile
from datetime import datetime,timezone
from pathlib import Path

state=Path('/srv/pyaterka/state');root=Path('/var/backups/pyaterka')
root.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(root,0o700)
name=root/('pyaterka-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.tar.gz')
with tempfile.TemporaryDirectory(dir=root) as folder:
    snapshot=Path(folder)/'trainer.sqlite3'
    with sqlite3.connect('file:'+str(state/'trainer.sqlite3')+'?mode=ro',uri=True) as source,sqlite3.connect(snapshot) as target:source.backup(target)
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as handle,tarfile.open(fileobj=handle,mode='w:gz') as archive:
        archive.add(snapshot,arcname='state/trainer.sqlite3')
        for item in state.iterdir():
            if item.name not in {'trainer.sqlite3','trainer.sqlite3-wal','trainer.sqlite3-shm'} and item.suffix!='.lock':archive.add(item,arcname='state/'+item.name)
        archive.add('/etc/pyaterka.env',arcname='pyaterka.env')
for old in sorted(root.glob('pyaterka-*.tar.gz'))[:-7]:old.unlink()
print('Backup created:',name.name)
