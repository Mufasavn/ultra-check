"""Windows user-bound credential encryption; never stores plaintext keys."""
import ctypes
from ctypes import wintypes
import json
import os
import threading
from ultra_client import UltraError

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def crypt(data, decrypt=False):
    if os.name!='nt':raise UltraError('Encrypted credential storage is supported on Windows only.')
    buf=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if decrypt:
        fn=dll.CryptUnprotectData;fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        args=(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:
        fn=dll.CryptProtectData;fn.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        args=(ctypes.byref(source),'Ultra Check Apify',None,None,None,1,ctypes.byref(target))
    fn.restype=wintypes.BOOL
    if not fn(*args):raise UltraError('Could not read or write the Windows key vault. Only the Windows account that saved it can decrypt it.')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data,ctypes.c_void_p))

class KeyVault:
    def __init__(self,path):self.path=path;self.lock=threading.Lock()
    def load(self):
        if not self.path.exists():return None
        try:
            data=json.loads(crypt(self.path.read_bytes(),True))
            if data.get('version')!=1 or len(data.get('slots',[])) not in (5,10):raise ValueError()
            return data
        except UltraError:raise
        except (OSError,ValueError,TypeError):raise UltraError('The Apify key vault is invalid. Existing data was not overwritten.') from None
    def save(self,data):
        raw=crypt(json.dumps(data,ensure_ascii=False).encode())
        with self.lock:
            temporary=self.path.with_suffix('.tmp');temporary.write_bytes(raw);os.replace(temporary,self.path)
