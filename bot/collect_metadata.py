import os
import json
import time
import stat

from config import logger


def collect_metadata(directory):
    files = {}
    data = {}
    now = time.time()

    def collect(dir_path):
        nonlocal files, data, now
        for entry in os.scandir(dir_path):
            path = os.path.relpath(entry.path, directory)
            if entry.is_dir():
                files[path] = dict(st_mode=(stat.S_IFDIR | 0o755), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2)
                collect(entry.path)
            elif entry.is_file():
                with open(entry.path, 'rb') as f:
                    content = f.read()
                files[path] = dict(st_mode=(stat.S_IFREG | 0o644), st_ctime=os.path.getctime(entry.path),
                                   st_mtime=os.path.getmtime(entry.path), st_atime=os.path.getatime(entry.path),
                                   st_size=len(content))
                data[path] = content

    collect(directory)

    return {'files': files, 'data': data}


def save_metadata_to_storage(directory, metadata_path, data_path):
    state = collect_metadata(directory)

    metadata = {'files': state['files']}
    try:
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)
        logger.info(f"Metadata saved to {metadata_path}")
    except Exception as e:
        logger.error(f"Error saving metadata to {metadata_path}: {e}")

    data = {k: v.decode('latin1') for k, v in state['data'].items()}
    try:
        with open(data_path, 'w') as f:
            json.dump(data, f)
        logger.info(f"File data saved to {data_path}")
    except Exception as e:
        logger.error(f"Error saving file data to {data_path}: {e}")

