import shutil
import tempfile
import zipfile
import tarfile
import os


def zip_files(files, archive_name):
    with zipfile.ZipFile(archive_name, 'w') as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))


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


def delete_file_from_zip(zip_name, file_name):
    temp_dir = tempfile.mkdtemp()
    temp_zip = os.path.join(temp_dir, "temp.zip")

    with zipfile.ZipFile(zip_name, 'r') as zip_ref:
        files_to_keep = [f for f in zip_ref.namelist() if f != file_name]
        with zipfile.ZipFile(temp_zip, 'w') as new_zip:
            for file in files_to_keep:
                new_zip.writestr(file, zip_ref.read(file))

    shutil.move(temp_zip, zip_name)


def tar_files(files, archive_name):
    with tarfile.open(archive_name, 'w') as tarf:
        for file in files:
            tarf.add(file, arcname=os.path.basename(file))


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


def delete_file_from_tar(tar_name, file_name):
    temp_dir = tempfile.mkdtemp()
    temp_tar = os.path.join(temp_dir, "temp.tar")

    with tarfile.open(tar_name, 'r') as tar_ref:
        files_to_keep = [member for member in tar_ref.getmembers() if member.name != file_name]
        with tarfile.open(temp_tar, 'w') as new_tar:
            for member in files_to_keep:
                if member.isfile():
                    with tar_ref.extractfile(member) as src:
                        new_tar.addfile(member, src)
                else:
                    new_tar.add(member, tar_ref.extractfile(member))

    shutil.move(temp_tar, tar_name)
