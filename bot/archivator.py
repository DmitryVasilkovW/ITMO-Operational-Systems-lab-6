import zipfile
import tarfile
import os


def zip_directory(directory, zip_name):
    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for root, dirs, files in os.walk(directory):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), directory))


def unzip_read_only_file(zip_name, extract_dir):
    with zipfile.ZipFile(zip_name, 'r') as zipf:
        for file_info in zipf.infolist():
            file_info.filename = file_info.filename.encode('cp437').decode('utf-8', 'ignore')
            zipf.extract(file_info, extract_dir)
            extracted_file_path = os.path.join(extract_dir, file_info.filename)
            os.chmod(extracted_file_path, 0o444)

    os.chmod(extract_dir, 0o555)


def unzip_file(zip_name, extract_dir):
    with zipfile.ZipFile(zip_name, 'r') as zipf:
        for file_info in zipf.infolist():
            file_info.filename = file_info.filename.encode('cp437').decode('utf-8', 'ignore')
            zipf.extract(file_info, extract_dir)


def tar_directory(directory, tar_name):
    with tarfile.open(tar_name, 'w') as tarf:
        tarf.add(directory, arcname=os.path.basename(directory))


def untar_read_only_file(tar_name, extract_dir):
    with tarfile.open(tar_name, 'r') as tarf:
        for member in tarf.getmembers():
            member_path = os.path.join(extract_dir, member.name)
            tarf.extract(member, extract_dir)
            if not member.isdir():
                os.chmod(member_path, 0o444)

    os.chmod(extract_dir, 0o555)



def untar_file(tar_name, extract_dir):
    with tarfile.open(tar_name, 'r') as tarf:
        tarf.extractall(extract_dir)