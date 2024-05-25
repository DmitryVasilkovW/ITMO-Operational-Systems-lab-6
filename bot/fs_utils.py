import os
import llfuse
from memory_fs import MemoryFS
from config import MOUNT_POINT, STORAGE_PATH, logger

memory_fs = None


def check_mount():
    return os.path.ismount(MOUNT_POINT)


def mount_fs():
    global memory_fs
    memory_fs = MemoryFS(STORAGE_PATH)
    llfuse.init(memory_fs, MOUNT_POINT, ['fsname=memoryfs', 'nonempty'])
    logger.info(f"File system successfully mounted at {MOUNT_POINT}")
    try:
        llfuse.main()
    except:
        llfuse.close(unmount=True)


def unmount_fs():
    global memory_fs
    if check_mount():
        os.system(f"fusermount -u {MOUNT_POINT}")
        logger.info(f"File system successfully unmounted from {MOUNT_POINT}")


def start_fuse():
    if not os.path.exists(MOUNT_POINT):
        try:
            os.makedirs(MOUNT_POINT)
        except FileExistsError:
            pass
    elif not os.path.isdir(MOUNT_POINT):
        raise Exception(f"{MOUNT_POINT} exists but is not a directory.")

    if check_mount():
        logger.info(f"File system already mounted at {MOUNT_POINT}")
        return
    else:
        mount_fs()
