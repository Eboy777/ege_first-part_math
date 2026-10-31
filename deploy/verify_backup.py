import sqlite3,tarfile,tempfile
from pathlib import Path
latest=sorted(Path('/var/backups/pyaterka').glob('pyaterka-*.tar.gz'))[-1]
with tempfile.TemporaryDirectory(dir='/var/backups/pyaterka') as folder:
    database=Path(folder)/'trainer.sqlite3'
    with tarfile.open(latest) as archive:
        with archive.extractfile('state/trainer.sqlite3') as source:database.write_bytes(source.read())
    with sqlite3.connect(database) as connection:
        result=connection.execute('PRAGMA integrity_check').fetchone()[0]
        print('Backup SQLite integrity:',result)
        print('Backup accounts:',connection.execute('select count(*) from auth_user').fetchone()[0])
    if result!='ok':raise SystemExit(1)
