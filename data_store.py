"""Stable per-Windows-user storage with non-destructive portable-data migration."""
import json,os,shutil,sqlite3
from pathlib import Path
from saved_store import SavedStore

def data_directory(executable,override=None):
    if override:
        path=Path(override);path.mkdir(parents=True,exist_ok=True);return path
    base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
    target=base/'UltraCheck';target.mkdir(parents=True,exist_ok=True)
    marker=target/'portable-migrations.json'
    try:done=json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else []
    except (ValueError,OSError):done=[]
    candidates=[Path(executable)/'UltraCheck-data',Path.cwd()/'UltraCheck-data',Path(executable).parent/'UltraCheck-data']
    for source in candidates:
        identity=str(source.resolve()).casefold()
        if not source.is_dir() or source.resolve()==target.resolve() or identity in done:continue
        # Merge bookmark lists rather than replacing the user's stable copy.
        if (source/'saved.json').exists() or (source/'saved.json.bak').exists():
            SavedStore(target/'saved.json').merge(SavedStore(source/'saved.json').read())
        for name in ('apify-keys.dat','proxy-settings.dat','proxy-usage.json'):
            if (source/name).is_file() and not (target/name).exists():shutil.copy2(source/name,target/name)
        for name in ('cache.sqlite','proxy-cache/cache.sqlite'):
            old=source/name;new=target/name
            if old.exists() and not new.exists():
                new.parent.mkdir(parents=True,exist_ok=True)
                with sqlite3.connect(old) as src,sqlite3.connect(new) as dst:src.backup(dst)
        done.append(identity)
        temporary=marker.with_suffix('.tmp');temporary.write_text(json.dumps(done),encoding='utf-8');os.replace(temporary,marker)
    return target
