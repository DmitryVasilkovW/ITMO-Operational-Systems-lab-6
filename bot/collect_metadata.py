import os
import json
import time
import stat
from datetime import datetime

from config import logger, STORAGE_PATH


def collect_metadata(directory, existing_files=None):
    files = existing_files if existing_files is not None else {}
    data = {}
    now = time.time()

    def collect(dir_path):
        nonlocal files, data, now
        for entry in os.scandir(dir_path):
            path = os.path.relpath(entry.path, directory)
            if entry.is_dir():
                if path not in files:
                    files[path] = dict(st_mode=(stat.S_IFDIR | 0o755), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2)
                else:
                    files[path]['st_mtime'] = now
                    files[path]['st_atime'] = now
                collect(entry.path)
            elif entry.is_file():
                with open(entry.path, 'rb') as f:
                    content = f.read()
                if path not in files:
                    files[path] = dict(st_mode=(stat.S_IFREG | 0o644), st_ctime=os.path.getctime(entry.path),
                                       st_mtime=os.path.getmtime(entry.path), st_atime=os.path.getatime(entry.path),
                                       st_size=len(content))
                else:
                    files[path]['st_mtime'] = os.path.getmtime(entry.path)
                    files[path]['st_atime'] = os.path.getatime(entry.path)
                    files[path]['st_size'] = len(content)
                data[path] = content

    collect(directory)
    return {'files': files, 'data': data}


def save_metadata_to_storage(directory, metadata_path, data_path):
    # Load existing metadata if it exists
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                existing_metadata = json.load(f)
            existing_files = existing_metadata.get('files', {})
        except Exception as e:
            logger.error(f"Error loading existing metadata from {metadata_path}: {e}")
            existing_files = {}
    else:
        existing_files = {}

    # Collect new metadata and merge it with existing metadata
    state = collect_metadata(directory, existing_files)

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


def load_metadata():
    try:
        with open(STORAGE_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading metadata from {STORAGE_PATH}: {e}")
        return {'files': {}}


def format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def get_ctime(filename):
    metadata = load_metadata()
    if filename in metadata['files']:
        ctime = metadata['files'][filename].get('st_ctime')
        if ctime:
            return format_timestamp(ctime)
        else:
            return "Дата создания не найдена для файла."
    else:
        return "Файл не найден."


def get_mtime(filename):
    metadata = load_metadata()
    if filename in metadata['files']:
        mtime = metadata['files'][filename].get('st_mtime')
        if mtime:
            return format_timestamp(mtime)
        else:
            return "Дата последнего изменения не найдена для файла."
    else:
        return "Файл не найден."

