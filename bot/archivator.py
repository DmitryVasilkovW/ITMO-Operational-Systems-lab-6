import zipfile
import tarfile
import os

# Архивация директории в ZIP
def zip_directory(directory, zip_name):
    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for root, dirs, files in os.walk(directory):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), directory))

# Разархивация ZIP файла
def unzip_file(zip_name, extract_dir):
    with zipfile.ZipFile(zip_name, 'r') as zipf:
        zipf.extractall(extract_dir)

# Архивация директории в TAR
def tar_directory(directory, tar_name):
    with tarfile.open(tar_name, 'w') as tarf:
        tarf.add(directory, arcname=os.path.basename(directory))

# Разархивация TAR файла
def untar_file(tar_name, extract_dir):
    with tarfile.open(tar_name, 'r') as tarf:
        tarf.extractall(extract_dir)