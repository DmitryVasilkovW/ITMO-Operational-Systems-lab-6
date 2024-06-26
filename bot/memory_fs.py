import errno
import time
import stat
import os
import llfuse
from llfuse import FUSEError, Operations


class MemoryFS(Operations):
    def __init__(self, storage_path):
        super(MemoryFS, self).__init__()
        self.files = {}
        self.data = {}
        self.storage_path = storage_path
        now = time.time()
        self.files['/'] = dict(st_mode=(stat.S_IFDIR | 0o755), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2)

    def getattr(self, inode, ctx=None):
        path = llfuse.fuse_decode_inode(inode)
        if path not in self.files:
            raise FUSEError(errno.ENOENT)
        return self.files[path]

    def lookup(self, parent_inode, name, ctx=None):
        path = llfuse.fuse_decode_inode(parent_inode)
        name = name.decode()
        full_path = os.path.join(path, name)
        if full_path not in self.files:
            raise FUSEError(errno.ENOENT)
        return self.files[full_path]

    def readdir(self, inode, off, token):
        path = llfuse.fuse_decode_inode(inode)
        entries = ['.', '..'] + [x[1:] for x in self.files if x != '/' and x.startswith(path)]
        for i, entry in enumerate(entries):
            if i >= off:
                llfuse.readdir_add(token, entry.encode('utf-8'), llfuse.ROOT_INODE + i + 1, off + 1)

    def mknod(self, parent_inode, name, mode, rdev, ctx=None):
        path = llfuse.fuse_decode_inode(parent_inode)
        name = name.decode()
        full_path = os.path.join(path, name)
        self.files[full_path] = dict(st_mode=(stat.S_IFREG | mode), st_nlink=1, st_size=0,
                                     st_ctime=time.time(), st_mtime=time.time(), st_atime=time.time())
        self.data[full_path] = b''

    def mkdir(self, parent_inode, name, mode, ctx=None):
        path = llfuse.fuse_decode_inode(parent_inode)
        name = name.decode()
        full_path = os.path.join(path, name)
        self.files[full_path] = dict(st_mode=(stat.S_IFDIR | mode), st_nlink=2,
                                     st_ctime=time.time(), st_mtime=time.time(), st_atime=time.time())
        self.files['/']['st_nlink'] += 1

    def unlink(self, parent_inode, name, ctx=None):
        path = llfuse.fuse_decode_inode(parent_inode)
        name = name.decode()
        full_path = os.path.join(path, name)
        self.files.pop(full_path)
        self.data.pop(full_path, None)

    def rmdir(self, parent_inode, name, ctx=None):
        path = llfuse.fuse_decode_inode(parent_inode)
        name = name.decode()
        full_path = os.path.join(path, name)
        self.files.pop(full_path)
        self.files['/']['st_nlink'] -= 1

    def read(self, fh, off, size):
        path = llfuse.fuse_decode_inode(fh)
        return self.data[path][off:off + size]

    def write(self, fh, off, buf):
        path = llfuse.fuse_decode_inode(fh)
        if path not in self.data:
            self.data[path] = b''
        self.data[path] = self.data[path][:off] + buf
        self.files[path]['st_size'] = len(self.data[path])
        return len(buf)

    def setattr(self, inode, attr, fields, ctx):
        path = llfuse.fuse_decode_inode(inode)
        if path not in self.files:
            raise FUSEError(errno.ENOENT)
        entry = self.files[path]
        if 'st_size' in fields:
            entry['st_size'] = attr.st_size
        if 'st_mode' in fields:
            entry['st_mode'] = attr.st_mode
        if 'st_mtime' in fields:
            entry['st_mtime'] = attr.st_mtime
        if 'st_atime' in fields:
            entry['st_atime'] = attr.st_atime
        if 'st_ctime' in fields:
            entry['st_ctime'] = attr.st_ctime
        return entry