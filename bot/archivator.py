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
    # Создаем временную директорию и временное имя для нового архива
    temp_dir = tempfile.mkdtemp()
    temp_tar = os.path.join(temp_dir, "temp.tar")

    try:
        # Открываем исходный архив для чтения
        with tarfile.open(tar_name, 'r') as tar_ref:
            # Фильтруем члены архива, исключая указанный файл
            files_to_keep = [member for member in tar_ref.getmembers() if member.name != file_name]

            # Открываем новый архив для записи
            with tarfile.open(temp_tar, 'w') as new_tar:
                for member in files_to_keep:
                    if member.isfile():
                        # Добавляем файлы в новый архив
                        src = tar_ref.extractfile(member)
                        if src:
                            new_tar.addfile(member, src)
                    else:
                        # Добавляем папки в новый архив
                        new_tar.add(member, tar_ref.extractfile(member).read())

        # Перемещаем новый архив на место старого
        shutil.move(temp_tar, tar_name)

        # Удаляем исходный архив
        os.remove(tar_name)
    finally:
        # Удаляем временную директорию
        shutil.rmtree(temp_dir, ignore_errors=True)


def delete_file_from_archive(archive_path, file_name):
    temp_dir = tempfile.mkdtemp()
    temp_extracted_dir = os.path.join(temp_dir, "extracted_archive")
    temp_new_dir = os.path.join(temp_dir, "new_archive")

    try:
        # Разархивируем архив во временную директорию
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extracted_dir)
        elif archive_path.endswith('.tar'):
            with tarfile.open(archive_path, 'r') as tar_ref:
                tar_ref.extractall(temp_extracted_dir)

        # Создаем новую директорию и копируем туда все файлы, кроме указанного
        os.makedirs(temp_new_dir)
        for root, _, files in os.walk(temp_extracted_dir):
            for file in files:
                if file != file_name:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, temp_extracted_dir)
                    new_file_path = os.path.join(temp_new_dir, rel_path)
                    os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
                    shutil.copy2(file_path, new_file_path)

        # Удаляем исходный архив
        os.remove(archive_path)

        # Архивируем новую директорию
        new_archive_path = archive_path
        if archive_path.endswith('.zip'):
            new_archive_path = new_archive_path.replace('.zip', '_new.zip')
            with zipfile.ZipFile(new_archive_path, 'w') as new_zip:
                for root, _, files in os.walk(temp_new_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, temp_new_dir)
                        new_zip.write(file_path, rel_path)
        elif archive_path.endswith('.tar'):
            new_archive_path = new_archive_path.replace('.tar', '_new.tar')
            with tarfile.open(new_archive_path, 'w') as new_tar:
                new_tar.add(temp_new_dir, arcname='')

        return new_archive_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
