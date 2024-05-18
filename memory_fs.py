import errno
import time
import stat
from fuse import FUSE, FuseOSError, Operations


class MemoryFS(Operations):
    def __init__(self):
        self.files = {}
        self.data = {}
        now = time.time()
        self.files['/'] = dict(st_mode=(stat.S_IFDIR | 0o755), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2)

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
