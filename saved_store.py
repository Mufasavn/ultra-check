"""Durable, atomic bookmarks with a last-known-good backup."""
import json,os,threading,shutil
from ultra_client import domain
class SavedStore:
    def __init__(self,path):self.path=path;self.lock=threading.RLock();self.backup=path.with_suffix(path.suffix+'.bak')
    def decode(self,path):
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value,dict) or any(not isinstance(value.get(k),list) or any(not isinstance(x,str) for x in value[k]) for k in ('advertisers','domains')):raise ValueError('Invalid saved list. Restore saved.json or its backup.')
        return {k:value[k] for k in ('advertisers','domains')}
    def read(self):
        with self.lock:
            if not self.path.exists():return self.decode(self.backup) if self.backup.exists() else {'advertisers':[],'domains':[]}
            try:return self.decode(self.path)
            except (ValueError,UnicodeError):
                if self.backup.exists():return self.decode(self.backup)
                raise
    def write(self,saved):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            try:self.decode(self.path);shutil.copy2(self.path,self.backup)
            except (ValueError,UnicodeError):pass
        temporary=self.path.with_suffix('.tmp')
        with temporary.open('w',encoding='utf-8') as f:json.dump(saved,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temporary,self.path)
        # Also ensure the first successful save has a usable backup.
        if not self.backup.exists():shutil.copy2(self.path,self.backup)
    def merge(self,incoming):
        with self.lock:
            saved=self.read()
            for kind in ('advertisers','domains'):
                seen={x.casefold() for x in saved[kind]}
                for value in incoming.get(kind,[]):
                    if isinstance(value,str) and value.strip() and value.casefold() not in seen:saved[kind].append(value);seen.add(value.casefold())
            self.write(saved);return saved
    def update(self,body):
        kind,value=body.get('kind'),body.get('value')
        if kind not in ('advertisers','domains') or not isinstance(value,str):raise ValueError('Invalid saved item.')
        value=value.strip()
        if not value or len(value)>300 or any(ord(c)<32 for c in value):raise ValueError('Enter a name or domain, up to 300 characters.')
        if kind=='domains':
            value=domain(value)
            if not value:raise ValueError('Invalid domain.')
        with self.lock:
            saved=self.read();items=saved[kind]
            if body.get('remove') is True:saved[kind]=[x for x in items if x.casefold()!=value.casefold()]
            elif not any(x.casefold()==value.casefold() for x in items):items.append(value)
            self.write(saved);return saved
