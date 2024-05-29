import os
import llfuse
from memory_fs import MemoryFS
from config import CUSTOM_STORAGE_PATH, logger

custom_memory_fs = None


def custom_check_mount(custom_mount: str):
    return os.path.ismount(custom_mount)


def custom_mount_fs(custom_mount: str):
    global custom_memory_fs
    custom_memory_fs = MemoryFS(CUSTOM_STORAGE_PATH)
    llfuse.init(custom_memory_fs, custom_mount)
    logger.info(f"File system successfully mounted at {custom_mount}")
    try:
        llfuse.main()
    except:
        llfuse.close(unmount=True)


def custom_unmount_fs(custom_mount: str):
    global custom_memory_fs
    if custom_check_mount(custom_mount):
        os.system(f"fusermount -u {custom_mount}")
        logger.info(f"File system successfully unmounted from {custom_mount}")


def custom_start_fuse(custom_mount: str):
    if not os.path.exists(custom_mount):
        try:
            os.makedirs(custom_mount)
        except FileExistsError:
            pass
    elif not os.path.isdir(custom_mount):
        raise Exception(f"{custom_mount} exists but is not a directory.")

    if custom_check_mount(custom_mount):
        logger.info(f"File system already mounted at {custom_mount}")
        return
    else:
        custom_mount_fs(custom_mount)
