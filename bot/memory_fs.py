import errno
import time
import stat
import os
import json
from fuse import FUSE, FuseOSError, Operations


class MemoryFS(Operations):
    def __init__(self, storage_path):
        self.files = {}
        self.data = {}
        self.storage_path = storage_path
        now = time.time()
        self.files['/'] = dict(st_mode=(stat.S_IFDIR | 0o777), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2)
        self.load_from_storage()

    def load_from_storage(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r') as f:
                state = json.load(f)
                self.files = state['files']
                self.data = {k: bytes(v, 'latin1') for k, v in state['data'].items()}

    def save_to_storage(self):
        state = {
            'files': self.files,
            'data': {k: v.decode('latin1') for k, v in self.data.items()}
        }
        with open(self.storage_path, 'w') as f:
            json.dump(state, f)

    def getattr(self, path, fh=None):
        if path not in self.files:
            raise FuseOSError(errno.ENOENT)
        return self.files[path]

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files if x != '/' and x.startswith(path)]

    def create(self, path, mode):
        self.files[path] = dict(st_mode=(stat.S_IFREG | mode), st_nlink=1, st_size=0,
                                st_ctime=time.time(), st_mtime=time.time(), st_atime=time.time())
        self.data[path] = b''
        return 0

    def write(self, path, data, offset, fh):
        if path not in self.data:
            self.data[path] = b''
        self.data[path] = self.data[path][:offset] + data
        self.files[path]['st_size'] = len(self.data[path])
        return len(data)

    def read(self, path, size, offset, fh):
        return self.data[path][offset:offset + size]

    def mkdir(self, path, mode):
        self.files[path] = dict(st_mode=(stat.S_IFDIR | mode), st_nlink=2,
                                st_ctime=time.time(), st_mtime=time.time(), st_atime=time.time())
        self.files['/']['st_nlink'] += 1

    def unlink(self, path):
        self.files.pop(path)
        self.data.pop(path, None)

    def rmdir(self, path):
        self.files.pop(path)
        self.files['/']['st_nlink'] -= 1
