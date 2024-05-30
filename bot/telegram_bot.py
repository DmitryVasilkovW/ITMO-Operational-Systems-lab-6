import grp
import os
import pwd
import shutil
import subprocess
import tarfile
import tempfile
import threading
import re
import yaml
from functools import partial

from telegram import Update, MessageEntity, Bot
from telegram.ext import CallbackContext, ConversationHandler

import config
from bot.archivator import untar_file, unzip_file
from bot.converter import create_empty_jpg, convert_png_to_jpg
from bot.collect_metadata import save_metadata_to_storage, get_ctime, get_mtime
from bot.custom_fs_utils import custom_start_fuse, custom_unmount_fs
from bot.custom_listing_utils import parse_directory_listing
from config import logger, TOKEN, STORAGE_PATH, BACKUP_FILE, CUSTOM_STORAGE_PATH, CUSTOM_BACKUP_FILE
from fs_utils import unmount_fs, start_fuse
from mutagen.easyid3 import EasyID3
from mutagen.id3 import error

fuse_stopped = False
custom_fuse_stopped = False
custom_mount_point = ''
custom_config_path = ''


def help_command(update: Update, context):
    if '-b' in update.message.text:
        text = "(Help) I need somebody\n(Help) Not just anybody\n(Help) You know I need someone\n(Help!)"
        update.message.reply_text(text)
        return ConversationHandler.END
    else:
        commands = [
            "/start - запуск ФС после остановки",
            "/stop - остановка ФС",
            "/mkdir <dir> - создание директории",
            "/save <dir> - отправка файла на сервер",
            "/get <file> - получение файла от сервера",
            "/cp <src> <dst> - копирование файла или директории ",
            "/mv <src> <dst> - перемещение файла или директории",
            "/cd <dir> - переход к директории",
            "/returnmount - возврат к примонтированной директории",
            "/ls <dir> - листинг с тегами",
            "/trls <dir> - листинг деревом",
            "/rm <file | dir> - удаление файла или директории",
            "/getdir <dir> - получении директории от сервера",
            "/ctime' <file | dir> - время создания файла или директории",
            "/mtime <file | dir> - время изменения файла или директории",
            "/group <srs> <dir> - группировка mp3",
            "/ungroup - удаление группировки mp3",
            "/archget <dir> - получений разархивированных копий директории dir",
            "/convert <dir> - подключение  директории для конвертации",
            "/c_start <mount> <conf> - подключение кастомной ФС",
            "/c_stop - отключение кастомной ФС",
            "/c_ls <dir> - листинг кастомной ФС",
            "/c_save <dir> - отправка файла на кастомную ФС сервера",
            "/c_get <file> - получение файла из кастомной ФС сервера"
        ]
        update.message.reply_text("\n".join(commands))
        return ConversationHandler.END


def check_custom_fuse(update):
    if custom_fuse_stopped:
        update.message.reply_text('Кастомная файловая система не активна.')
        return ConversationHandler.END


def check_fuse(update):
    if fuse_stopped:
        update.message.reply_text('Файловая система не активна.')
        return ConversationHandler.END


def escape_markdown(text: str) -> str:
    escape_chars = r'\`*_{}[]()#+-.!|>'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])


def split_and_send_message(update, message):
    MAX_MESSAGE_LENGTH = 4096 - 10
    escaped_message = escape_markdown(message)
    lines = escaped_message.split('\n')

    current_message = ""
    for line in lines:
        if len(current_message) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            update.message.reply_text(f"```\n{current_message}\n```", parse_mode='MarkdownV2')
            current_message = line
        else:
            if current_message:
                current_message += "\n"
            current_message += line

    if current_message:
        update.message.reply_text(f"```\n{current_message}\n```", parse_mode='MarkdownV2')


def check_mention(update, context) -> bool:
    if 'bot_username' not in context.user_data:
        context.user_data['bot_username'] = "@" + Bot(TOKEN).get_me().username

    bot_username = context.user_data['bot_username']
    entities = update.message.parse_entities([MessageEntity.MENTION]).values()

    return bot_username in entities


def handle_private(update, context):
    message_text = update.message.text.split()[0]
    command_mapping = {
        '/stop': stop_command,
        '/start': start_command,
        '/mkdir': mkdir,
        '/mv': move,
        '/ls': list_files,
        '/trls': tree_list_files,
        '/rm': remove,
        '/cp': cp,
        '/get': get_document,
        '/getdir': get_directory,
        '/ctime': ctime_command,
        '/mtime': mtime_command,
        '/cd': set_mount_dir,
        '/returnmount': revert_mount_dir,
        '/archget': get_archive,
        '/group': group_files,
        '/ungroup': rm_group,
        '/c_start': custom_start_command,
        '/c_stop': custom_stop_command,
        '/c_ls': custom_list_files,
        '/c_get': custom_get_document,
        '/help': help_command,
        '/finfo': file_info,
    }

    command_function = command_mapping.get(message_text)
    if command_function:
        command_function(update, context)


def handle_mention(update, context):
    if check_mention(update, context):
        message_text = update.message.text
        words = message_text.split()

        if len(words) > 1:
            command = words[1]

            command_mapping = {
                '/start': start_command,
                '/stop': stop_command,
                '/mkdir': mkdir,
                '/mv': move,
                '/ls': list_files,
                '/trls': tree_list_files,
                '/rm': remove,
                '/cp': cp,
                '/get': get_document,
                '/getdir': get_directory,
                '/ctime': ctime_command,
                '/mtime': mtime_command,
                '/cd': set_mount_dir,
                '/returnmount': revert_mount_dir,
                '/archget': get_archive,
                '/group': group_files,
                '/ungroup': rm_group,
                '/c_start': custom_start_command,
                '/c_stop': custom_stop_command,
                '/c_ls': custom_list_files,
                '/c_get': custom_get_document,
                '/help': help_command,
                '/finfo': file_info,
            }

            command_function = command_mapping.get(command)
            if command_function:
                command_function(update, context)


def file_info(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/finfo\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /finfo <file | dir>.")
        return ConversationHandler.END

    relative_path = match.group(1) or match.group(2)
    if relative_path is None:
        update.message.reply_text("Ошибка: используйте /finfo <file | dir>.")
        return ConversationHandler.END

    full_path = os.path.join(config.MOUNT_POINT, relative_path)

    if not os.path.exists(full_path):
        update.message.reply_text("Ошибка: файл или директория не существует.")
        return ConversationHandler.END

    try:
        file_stats = os.stat(full_path)
        file_size = file_stats.st_size
        file_owner = pwd.getpwuid(file_stats.st_uid).pw_name
        file_group = grp.getgrgid(file_stats.st_gid).gr_name
        file_permissions_octal = oct(file_stats.st_mode & 0o777)

        file_type = 'Файл' if os.path.isfile(full_path) else 'Директория' if os.path.isdir(
            full_path) else 'Символическая ссылка' if os.path.islink(full_path) else 'Другой'

        file_info_message = (
            f"Информация о {file_type.lower()} {relative_path}:\n"
            f"Размер: {file_size} байт\n"
            f"Владелец: {file_owner}\n"
            f"Группа: {file_group}\n"
            f"Права доступа: {file_permissions_octal}\n"
        )

        split_and_send_message(update, file_info_message)
    except Exception as e:
        logger.error(e)
        update.message.reply_text("Ошибка при получении информации о файле")
        return ConversationHandler.END

    return ConversationHandler.END


def cancel(update, context):
    update.message.reply_text('Операция отменена.')
    return ConversationHandler.END


def save_file_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'^/save(?:\s+"([^"]+)"|\s+(\S+))?$', message_text)
    if not match:
        update.message.reply_text('Неверный формат команды. Используйте /save или /save "<directory>"')
        return ConversationHandler.END

    directory = match.group(1) or match.group(2)
    if directory:
        if directory.startswith('/'):
            update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
            return ConversationHandler.END
        context.user_data['save_dir'] = directory
    else:
        context.user_data['save_dir'] = config.MOUNT_POINT

    update.message.reply_text('Отправьте файл или введите /cancel_save для отмены.')
    context.user_data['save_user_id'] = update.message.from_user.id
    context.user_data['save_context'] = 'waiting_for_file_private'
    context.user_data['attempt_count'] = 0
    return 'waiting_for_file_private'


def save_file_mention_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if check_mention(update, context):
        bot_username = context.bot.username
        message_text = update.message.text
        pattern = fr'^@{bot_username}\s+/save(?:\s+"([^"]+)"|\s+(\S+))?$'
        match = re.search(pattern, message_text)
        if not match:
            update.message.reply_text(f'Неверный формат команды. Используйте /save или /save "<directory>"')
            return ConversationHandler.END

        directory = match.group(1) or match.group(2)
        if directory:
            if directory.startswith('/'):
                update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
                return ConversationHandler.END
            context.user_data['save_dir'] = directory
        else:
            context.user_data['save_dir'] = config.MOUNT_POINT

        update.message.reply_text(f'Отправьте файл или введите /cancel_save@{bot_username} для отмены.')
        context.user_data['save_user_id'] = update.message.from_user.id
        context.user_data['save_context'] = 'waiting_for_file_mention'
        context.user_data['attempt_count'] = 0
        return 'waiting_for_file_mention'


def save_file(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if 'save_user_id' in context.user_data and context.user_data['save_user_id'] == update.message.from_user.id:
        file_info = None
        filename = None

        if update.message.document:
            file_info = update.message.document
            filename = file_info.file_name
        elif update.message.photo:
            file_info = update.message.photo[-1]
            filename = f"photo_{file_info.file_unique_id}.jpg"
        elif update.message.video:
            file_info = update.message.video
            filename = file_info.file_name
        elif update.message.animation:
            file_info = update.message.animation
            filename = file_info.file_name
        elif update.message.audio:
            file_info = update.message.audio
            filename = file_info.file_name

        if file_info:
            file_id = file_info.file_id
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(f"Received file from chat_id: {chat_id}")
            logger.info(f"Received file from user_id: {user_id}")
            logger.info(f"File received: file_id={file_id}, filename={filename}")

            save_dir = context.user_data.get('save_dir', config.MOUNT_POINT)
            local_path = os.path.join(config.MOUNT_POINT, save_dir, filename)

            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            if os.path.exists(local_path):
                update.message.reply_text(
                    f"Файл с именем {filename} уже существует. Пожалуйста, отправьте файл с другим именем.")
                return context.user_data['save_context']

            file = context.bot.get_file(file_id)
            file.download(local_path)
            logger.info(f"File downloaded to: {local_path}")

            update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
            save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
            return ConversationHandler.END
        else:
            context.user_data['attempt_count'] += 1
            if context.user_data['attempt_count'] >= 3:
                update.message.reply_text("Превышено количество попыток отправки файла.")
                return ConversationHandler.END
            else:
                if context.user_data['save_context'] == 'waiting_for_file_mention':
                    bot_username = context.user_data['bot_username']
                    update.message.reply_text(f'Отправьте файл или введите /cancel_save{bot_username} для отмены.')
                else:
                    update.message.reply_text('Отправьте файл или введите /cancel_save для отмены.')
                return context.user_data['save_context']
    else:
        return context.user_data['save_context']


def get_document(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/get\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /get <filename>.")
        return

    relative_path = match.group(1) or match.group(2)
    if relative_path is None:
        update.message.reply_text("Ошибка: используйте /get <filename>.")
        return

    absolute_path = os.path.join(config.MOUNT_POINT, relative_path)

    if not os.path.exists(absolute_path) or not os.path.isfile(absolute_path):
        update.message.reply_text(f"Ошибка: файл {relative_path} не найден.")
        return

    if absolute_path.endswith('.jpg'):
        png_path = absolute_path[:-3] + 'png'
        if os.path.exists(png_path) and os.path.isfile(png_path):
            convert_png_to_jpg(png_path)
            jpg_path = png_path[:-3] + 'jpg'
            with open(jpg_path, 'rb') as file:
                update.message.reply_document(document=file)
            os.remove(jpg_path)
            return

    with open(absolute_path, 'rb') as file:
        update.message.reply_document(document=file)


def get_directory(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/getdir\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /getdir <directory>.")
        return

    relative_path = match.group(1) or match.group(2)
    if relative_path is None:
        update.message.reply_text("Ошибка: используйте /getdir <directory>.")
        return

    absolute_path = os.path.join(config.MOUNT_POINT, relative_path)

    if not os.path.exists(absolute_path) or not os.path.isdir(absolute_path):
        update.message.reply_text(f"Ошибка: директория {relative_path} не найдена.")
        return

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_path = temp_file.name

    try:
        with tarfile.open(temp_file_path, 'w') as tar:
            tar.add(absolute_path, arcname=os.path.basename(absolute_path))

        with open(temp_file_path, 'rb') as file:
            update.message.reply_document(document=file, filename=f"{os.path.basename(absolute_path)}.tar")

    finally:
        os.unlink(temp_file_path)


def mkdir(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/mkdir\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, message_text)
    if not match:
        pattern = r'/mkdir\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, message_text)

    if match:
        directory_name = match.group(1) or match.group(2)

        if re.search(r'/mkdir\s+(\S+)\s+(\S+)', update.message.text) and re.search(r'/mkdir\s+"([^"]+)"',
                                                                                   message_text) is None:
            update.message.reply_text("Ошибка: команда должна содержать только одно слово.")
            return ConversationHandler.END

        if directory_name.startswith('/'):
            update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
            return ConversationHandler.END

        new_dir_path = os.path.join(config.MOUNT_POINT, directory_name)

        if os.path.exists(new_dir_path):
            update.message.reply_text(f"Ошибка: директория {directory_name} уже существует.")
            return ConversationHandler.END

        try:
            os.makedirs(new_dir_path, exist_ok=True, mode=0o777)
            update.message.reply_text(f"Директория {directory_name} успешно создана.")
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(
                f"Directory {directory_name} created successfully at {new_dir_path} from chat_id {chat_id} and user_id {user_id}.")
            save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при создании директории {directory_name}: {e}")
            update.message.reply_text(f"Ошибка при создании директории.")
    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь имя директории. Убедитесь, что команда введена правильно.")

    return ConversationHandler.END


def move(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/mv\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, message_text)
    if not match:
        pattern = r'/mv\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, message_text)

    if match:
        source = match.group(1) or match.group(2)
        destination = match.group(3) or match.group(4)

        source_path = os.path.join(config.MOUNT_POINT, source.lstrip('/'))
        destination_path = os.path.join(config.MOUNT_POINT, destination.lstrip('/'))

        if source_path == destination_path:
            update.message.reply_text(f"Ошибка: Исходный путь {source} и путь назначения {destination} равны.")
            return ConversationHandler.END

        if not os.path.exists(source_path):
            update.message.reply_text(f"Ошибка: Исходный путь {source} не существует.")
            return ConversationHandler.END

        if not os.path.exists(destination_path):
            update.message.reply_text(f"Ошибка: Путь назначения {destination} не существует.")
            return ConversationHandler.END

        try:
            shutil.move(source_path, destination_path)
            update.message.reply_text(f"{source} успешно перемещен(а) в {destination}.")

            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(f"{source} перемещен(а) в {destination} от chat_id {chat_id} и user_id {user_id}.")
            save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при перемещении {source} в {destination}: {e}")
            update.message.reply_text(f"Ошибка при перемещении")
    else:
        update.message.reply_text("Ошибка: неправильный формат команды. Используйте /mv <источник> <назначение>.")

    return ConversationHandler.END


def copy_path_with_suffix(src, dst):
    if os.path.exists(dst) and os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    original_dst = dst
    counter = 1
    while os.path.exists(dst):
        dst = add_suffix(original_dst, counter, os.path.isdir(src))
        counter += 1
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy(src, dst)

    return dst


def add_suffix(path, counter, is_dir):
    dirname, basename = os.path.split(path)
    if is_dir:
        new_basename = f"{basename}({counter})"
    else:
        name, ext = os.path.splitext(basename)
        new_basename = f"{name}({counter}){ext}"
    return os.path.join(dirname, new_basename)


def cp(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/cp\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, update.message.text)
    if not match:
        pattern = r'/cp\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, update.message.text)

    if match:
        src = match.group(1) or match.group(2)
        dst = match.group(3) or match.group(4)

        if src and dst:
            src = src.lstrip('/')
            dst = dst.lstrip('/')

            src_path = os.path.join(config.MOUNT_POINT, src)
            dst_path = os.path.join(config.MOUNT_POINT, dst)

            if not os.path.exists(src_path):
                update.message.reply_text(f"Ошибка: исходный путь {src} не существует.")
                return ConversationHandler.END

            try:
                new_dst_path = copy_path_with_suffix(src_path, dst_path)
                relative_new_dst_path = os.path.relpath(new_dst_path, config.MOUNT_POINT)
                update.message.reply_text(f"{src} успешно скопирован в {relative_new_dst_path}.")
                chat_id = update.message.chat_id
                user_id = update.message.from_user.id
                logger.info(
                    f"Path {src} copied to {relative_new_dst_path} from chat_id {chat_id} and user_id {user_id}.")
                save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
            except Exception as e:
                logger.error(f"Error copying {src} to {dst}: {e}")
                update.message.reply_text(f"Ошибка при копировании {src} в {dst}.")
        else:
            update.message.reply_text("Ошибка: используйте /cp <src> <dst>.")
    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь пути. Убедитесь, что команда введена правильно в формате /cp \"<src>\" \"<dst>\" или /cp <src> <dst>."
        )

    return ConversationHandler.END


def file_list() -> list[str]:
    files_list = []

    for root, dirs, files in os.walk(config.MOUNT_POINT, followlinks=True):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(root, config.MOUNT_POINT)
            if relative_path == '.':
                relative_path = '/'
            else:
                relative_path = f"/{relative_path}"
            if os.path.islink(file_path):
                files_list.append(f"<{relative_path}> {file} ->")
            else:
                files_list.append(f"<{relative_path}> {file}")
    return files_list


def tree(directory: str, prefix: str = '') -> str:
    result = []
    contents = os.listdir(directory)
    contents = sorted(contents, key=lambda s: s.lower())
    pointers = ['├── '] * (len(contents) - 1) + ['└── ']

    for pointer, path in zip(pointers, contents):
        full_path = os.path.join(directory, path)
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            result.append(f"{prefix}{pointer}{path}/")
            if pointer == '└── ':
                extension = '    '
            else:
                extension = '│   '
            result.append(tree(full_path, prefix=prefix + extension))
        else:
            if os.path.islink(full_path):
                result.append(f"{prefix}{pointer}{path} ->")
            else:
                result.append(f"{prefix}{pointer}{path}")
    return '\n'.join(result)


def list_path_check(update, directory_path):
    if '/' != directory_path[0]:
        update.message.reply_text("Ошибка: имя директории должно начинаться с `/`.")
        return ConversationHandler.END

    check_dir_path = os.path.join(config.MOUNT_POINT, directory_path[1:])

    if not os.path.exists(check_dir_path):
        update.message.reply_text(f"Ошибка: директории {directory_path} не существует")
        return ConversationHandler.END


def list_files(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    directory_path = '/'
    match = re.search(r'/ls\s+(?:"([^"]+)"|(\S+))', update.message.text)

    if match:
        directory_path = match.group(1) or match.group(2)
        if directory_path is None:
            update.message.reply_text("Ошибка: используйте /ls или /ls <dir>.")
            return ConversationHandler.END

        if list_path_check(update, directory_path) is ConversationHandler.END:
            return ConversationHandler.END

    files_list = file_list()

    filtered_files = [file for file in files_list if file.startswith(f"<{directory_path}")]

    if filtered_files:
        files_output = '\n'.join(filtered_files)
        message = files_output
    else:
        message = f"Директория {directory_path} и все поддиректории пусты."

    split_and_send_message(update, message)
    return ConversationHandler.END


def tree_list_files(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    directory_path = '/'
    match = re.search(r'/trls\s+(?:"([^"]+)"|(\S+))', update.message.text)

    if match:
        directory_path = match.group(1) or match.group(2)
        if directory_path is None:
            update.message.reply_text("Ошибка: используйте /trls или /trls <dir>.")
            return ConversationHandler.END

        if list_path_check(update, directory_path) is ConversationHandler.END:
            return ConversationHandler.END

    tree_output = tree(os.path.join(config.MOUNT_POINT, directory_path.strip('/')))
    tree_lines = [line for line in tree_output.split('\n') if line.strip()]
    if tree_lines:
        message = '\n'.join(tree_lines)
    else:
        message = f"Директория {directory_path} и все поддиректории пусты."

    split_and_send_message(update, message)
    return ConversationHandler.END


def remove_file(update, context, target_path):
    if target_path.startswith('/'):
        update.message.reply_text("Ошибка: путь не должен начинаться с `/`.")
        return ConversationHandler.END

    full_path = os.path.join(config.MOUNT_POINT, target_path)

    if not os.path.exists(full_path):
        update.message.reply_text(f"Ошибка: путь {target_path} не существует.")
        return ConversationHandler.END

    try:
        if os.path.isdir(full_path):
            logger.info("in dir")
            shutil.rmtree(full_path)
        else:
            logger.info("in file")
            os.remove(full_path)
        update.message.reply_text(f"{target_path} успешно удален(а).")
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id
        logger.info(f"{target_path} удален(а) от chat_id {chat_id} и user_id {user_id}.")
        save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    except Exception as e:
        logger.error(f"Ошибка при удалении {target_path}: {e}")
        update.message.reply_text(f"Ошибка при удалении {target_path}.")


def remove(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    match = re.search(r'/rm\s+"([^"]+)"', update.message.text)
    if match:
        target_path = match.group(1)

        if re.search(r'/rm\s+"([^"]+)"\s+"([^"]+)"', update.message.text) is not None:
            update.message.reply_text("Ошибка: команда должна содержать только один аргумент.")
            return ConversationHandler.END

        remove_file(update, context, target_path)

    elif re.search(r'/rm\s+(\S+)', update.message.text):
        match = re.search(r'/rm\s+(\S+)', update.message.text)

        target_path = match.group(1)

        if re.search(r'/rm\s+(\S+)\s+(\S+)', update.message.text) is not None:
            update.message.reply_text("Ошибка: команда должна содержать только один аргумент.")
            return ConversationHandler.END

        remove_file(update, context, target_path)

    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь путь. Убедитесь, что команда введена правильно и путь заключен в кавычки.")

    return ConversationHandler.END


def ctime_command(update, context):
    message_text = update.message.text
    match = re.search(r'/ctime\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /ctime <filename>.")
        return

    filename = match.group(1) or match.group(2)
    ctime = get_ctime(filename)
    update.message.reply_text(f"Дата создания файла {filename}: {ctime}")


def mtime_command(update, context):
    message_text = update.message.text
    match = re.search(r'/mtime\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /mtime <filename>.")
        return

    filename = match.group(1) or match.group(2)
    mtime = get_mtime(filename)
    update.message.reply_text(f"Дата последнего изменения файла {filename}: {mtime}")


def start_command(update: Update, context: CallbackContext):
    global fuse_stopped

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    fuse_stopped = False

    update.message.reply_text('Готов принимать команды для работы с файловой системой.')
    save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    return ConversationHandler.END


def stop_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    global fuse_stopped

    user_id = update.message.from_user.id
    logger.info(f"Stop command received from user_id: {user_id}")

    update.message.reply_text('Останавливаю работу файловой системы...')

    unmount_fs()
    fuse_stopped = True

    logger.info("Fuse stopped")
    save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    return ConversationHandler.END


def convert_mention_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if check_mention(update, context):
        context.user_data['overwrite_context'] = 'handle_overwrite_response_mention'
        return convert_command(update, context)


def convert_private_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    context.user_data['overwrite_context'] = 'handle_overwrite_response_private'
    return convert_command(update, context)


def handle_overwrite_response(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    response = update.message.text.lower()
    overwrite_confirmation = context.user_data['overwrite_confirmation']
    conflicting_files = context.user_data['conflicting_files']
    path = context.user_data['path']

    if response in ["да", "ок", "конечно", "хорошо", "+"]:
        overwrite_confirmation.append(True)
    elif response in ["нет", "не", "неа", "-"]:
        overwrite_confirmation.append(False)
    else:
        update.message.reply_text("Пожалуйста, ответьте 'да' или 'нет'.")
        return

    if len(overwrite_confirmation) < len(conflicting_files):
        next_file = conflicting_files[len(overwrite_confirmation)]
        filename, conflicting_filename, message = next_file

        if not filename.endswith(".png"):
            filename += ".png"

        if not conflicting_filename.endswith(".jpg"):
            conflicting_filename = filename[:-4] + '.jpg'

        update.message.reply_text(f"Хотите перезаписать файл {filename} -> {conflicting_filename}? (да/нет)")
    else:
        process_overwrites(update, context)
        return ConversationHandler.END


def process_overwrites(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    overwritten_files = []
    conflicting_files = context.user_data['conflicting_files']
    overwrite_confirmation = context.user_data['overwrite_confirmation']
    path = context.user_data['path']

    for i, (filename, conflicting_filename, message) in enumerate(conflicting_files):
        if overwrite_confirmation[i]:
            source_path = os.path.join(path, filename)
            destination_path = os.path.join(config.MOUNT_POINT, conflicting_filename)

            if os.path.exists(destination_path):
                os.remove(destination_path)

            if filename.endswith(".png"):
                output_filename_jpg = filename[:-4] + '.jpg'
                overwritten_files.append(f"{filename} -> {output_filename_jpg}")
                output_path_png = os.path.join(config.MOUNT_POINT, filename)

                shutil.copy(source_path, output_path_png)
                create_empty_jpg(output_path_png)

            elif filename.endswith(".jpg"):
                output_filename_png = filename[:-4] + '.png'
                output_filename_jpg = filename[:-4] + '.jpg'
                output_path_png = os.path.join(config.MOUNT_POINT, output_filename_png)
                overwritten_files.append(f"{filename} -> {output_filename_jpg}")

                shutil.copy(source_path, output_path_png)
                create_empty_jpg(output_path_png)

    overwrite_response_message = "Перезаписанные файлы:\n" + "\n".join(overwritten_files)
    update.message.reply_text(overwrite_response_message)


def convert_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/convert\s+(\S+)$', message_text)

    if match:
        path = match.group(1)

        if not os.path.exists(path):
            update.message.reply_text(f"Ошибка: Путь {path} не существует.")
            return ConversationHandler.END

        try:
            converted_files = []
            moved_files = []
            existing_files = []
            conflicting_files = []

            for filename in os.listdir(path):
                source_path = os.path.join(path, filename)

                if filename.endswith(".png"):
                    output_filename_jpg = filename[:-4] + '.jpg'
                    output_path_jpg = os.path.join(config.MOUNT_POINT, output_filename_jpg)
                    output_path_png = os.path.join(config.MOUNT_POINT, filename)

                    if os.path.exists(output_path_jpg) and os.path.exists(output_path_png):
                        existing_files.append(f"{filename} - PNG и JPG файлы уже существуют")
                    elif os.path.exists(output_path_jpg):
                        conflicting_files.append((filename, output_filename_jpg, "JPG файл уже существует"))
                    elif os.path.exists(output_path_png):
                        conflicting_files.append((filename, filename, "PNG файл уже существует"))
                    else:
                        create_empty_jpg(output_path_jpg)
                        shutil.copy(source_path, output_path_png)
                        converted_files.append(f"{filename} -> {output_filename_jpg}")

                elif filename.endswith(".jpg"):
                    output_filename_png = filename[:-4] + '.png'
                    output_path_png = os.path.join(config.MOUNT_POINT, output_filename_png)
                    output_path_jpg = os.path.join(config.MOUNT_POINT, filename)

                    if os.path.exists(output_path_png) and os.path.exists(output_path_jpg):
                        existing_files.append(f"{filename} - JPG и PNG файлы уже существуют")
                    elif os.path.exists(output_path_png):
                        conflicting_files.append((filename, output_filename_png, "PNG файл уже существует"))
                    elif os.path.exists(output_path_jpg):
                        conflicting_files.append((filename, filename, "JPG файл уже существует"))
                    else:
                        shutil.copy(source_path, output_path_jpg)
                        converted_files.append(f"{filename} -> {output_filename_png}")

                else:
                    output_path = os.path.join(config.MOUNT_POINT, filename)
                    shutil.copy(source_path, output_path)
                    moved_files.append(filename)

            response_message = f"Файлы в директории {path} успешно обработаны:\n\n"

            if converted_files:
                response_message += "Конвертированные файлы:\n" + "\n".join(converted_files) + "\n\n"

            if existing_files:
                response_message += "Файлы, которые уже существуют:\n" + "\n".join(existing_files) + "\n\n"

            if moved_files:
                response_message += "Перемещенные файлы:\n" + "\n".join(moved_files) + "\n\n"

            if conflicting_files:
                response_message += "Конфликтующие файлы:\n"

                for filename, conflicting_filename, message in conflicting_files:
                    response_message += f"  - {filename} -> {conflicting_filename} ({message})\n"

                context.user_data['conflicting_files'] = conflicting_files
                context.user_data['overwrite_confirmation'] = []
                context.user_data['path'] = path

                update.message.reply_text(response_message)
                next_file = conflicting_files[0]
                update.message.reply_text(f"Хотите перезаписать файл {next_file[0]} -> {next_file[1]}? (да/нет)")

                return context.user_data['overwrite_context']

            update.message.reply_text(response_message)

            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)

            logger.info(
                f"Files in directory {path} processed successfully from chat_id {chat_id} and user_id {user_id}.")
        except Exception as e:
            logger.error(f"Error processing files in directory {path}: {e}")
            update.message.reply_text(f"Ошибка при копировании файлов из директории {path}")
    else:
        update.message.reply_text("Ошибка: неправильный формат команды. Используйте /convert <путь>.")

    return ConversationHandler.END


def group_mp3_files(src_directory, dest_directory):
    for root, _, files in os.walk(src_directory):
        for file in files:
            if file.endswith('.mp3'):
                file_path = os.path.join(root, file)
                try:
                    audio = EasyID3(file_path)
                    artist = audio.get('artist', ['no_artist'])[0]
                    genre = audio.get('genre', ['no_genre'])[0]
                    year = audio.get('date', ['no_year'])[0].split('-')[0]
                except error:
                    artist, genre, year = 'no_artist', 'no_genre', 'no_year'

                artist_path = os.path.join(dest_directory, 'Artist', artist)
                genre_path = os.path.join(dest_directory, 'Genre', genre)
                year_path = os.path.join(dest_directory, 'Year', year)

                os.makedirs(artist_path, exist_ok=True)
                os.makedirs(genre_path, exist_ok=True)
                os.makedirs(year_path, exist_ok=True)

                create_symlink(file_path, artist_path)
                create_symlink(file_path, genre_path)
                create_symlink(file_path, year_path)


def create_symlink(src, dest):
    try:
        symlink_path = os.path.join(dest, os.path.basename(src))
        if not os.path.exists(symlink_path):
            os.symlink(src, symlink_path)
    except Exception as e:
        logger.error(f"Ошибка при создании ссылки для {src} в {dest}: {e}")


def group_files(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/group\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, message_text)
    if not match:
        pattern = r'/group\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, message_text)

    if match:
        src_directory = match.group(1) or match.group(2)
        src_directory = src_directory.lstrip('/')

        src_path = os.path.join(config.MOUNT_POINT, src_directory)
        dest_path = os.path.join(config.MOUNT_POINT, 'grouped_mp3')

        if not os.path.exists(src_path) and not os.path.exists('/' + src_directory):
            update.message.reply_text(f"Ошибка: директория {src_directory} не существует.")
            return ConversationHandler.END
        elif os.path.exists('/' + src_directory):
            src_path = '/' + src_directory
        else:
            update.message.reply_text(f"Ошибка: директория {src_directory} не существует.")
            return ConversationHandler.END

        try:
            group_mp3_files(src_path, dest_path)
            update.message.reply_text(f"Файлы из {src_directory} успешно сгруппированы в grouped_mp3.")
            save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при группировке файлов из {src_directory}: {e}")
            update.message.reply_text(f"Ошибка при группировке файлов.")
    else:
        update.message.reply_text("Ошибка: неправильный формат команды. Используйте /group <директория>.")

    return ConversationHandler.END


def rm_group(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if re.search(r'/ungroup\s+(\S+)', update.message.text):
        update.message.reply_text("Ошибка: используйте /rmgroup без аргументов")
        return ConversationHandler.END

    dest_path = os.path.join(config.MOUNT_POINT, 'grouped_mp3')

    if os.path.exists(dest_path):
        try:
            shutil.rmtree(dest_path)
            relative_path = os.path.relpath(dest_path, config.MOUNT_POINT)
            update.message.reply_text(f"Директория {relative_path} успешно удалена.")
            save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при удалении директории {dest_path}: {e}")
            update.message.reply_text("Ошибка при удалении директории.")
    else:
        relative_path = os.path.relpath(dest_path, config.MOUNT_POINT)
        update.message.reply_text(f"Ошибка: директория {relative_path} не существует.")

    return ConversationHandler.END


def custom_start_command(update, context):
    global custom_fuse_stopped
    global custom_mount_point
    global custom_config_path

    message_text = update.message.text
    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/c_start\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, message_text)
    if not match:
        pattern = r'/c_start\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, message_text)

    if match:
        mount = match.group(1) or match.group(2)
        config_in = match.group(3) or match.group(4)

        config_path = os.path.join(config.MOUNT_POINT, config_in.lstrip('/'))

        if mount == config_path:
            update.message.reply_text(f"Ошибка: Точка монтирования {mount} и путь конфига {config} равны.")
            return ConversationHandler.END

        if not os.path.exists(config_path):
            update.message.reply_text(f"Ошибка: Файл конфига {config} не существует.")
            return ConversationHandler.END

        custom_fuse_thread = threading.Thread(target=partial(custom_start_fuse, mount))
        custom_fuse_thread.start()

        custom_mount_point = mount
        custom_config_path = config_path
        custom_fuse_stopped = False

        update.message.reply_text('Готов принимать команды для работы с кастомной файловой системой.')
        save_metadata_to_storage(custom_mount_point, CUSTOM_STORAGE_PATH, CUSTOM_BACKUP_FILE)

    return ConversationHandler.END


def custom_stop_command(update: Update, context: CallbackContext):
    if check_custom_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    global custom_fuse_stopped
    global custom_mount_point
    global custom_config_path

    user_id = update.message.from_user.id
    logger.info(f"Stop command received from user_id: {user_id}")

    update.message.reply_text('Останавливаю работу кастомной файловой системы...')

    custom_unmount_fs(custom_mount_point)
    custom_fuse_stopped = True

    logger.info("Fuse stopped")
    save_metadata_to_storage(config.MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    custom_mount_point = ''
    custom_config_path = ''
    return ConversationHandler.END


def custom_list_files(update, context):
    if check_custom_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    directory_path = custom_mount_point
    match = re.search(r'/c_ls\s+(?:"([^"]+)"|(\S+))', update.message.text)

    if match:
        directory_path = match.group(1) or match.group(2)
        if directory_path is None:
            update.message.reply_text("Ошибка: используйте /c_ls")
            return ConversationHandler.END

        if list_path_check(update, directory_path) is ConversationHandler.END:
            return ConversationHandler.END

    commands = parse_directory_listing(custom_config_path)

    outputs = []

    try:
        for command in commands:
            if command != "pass":
                full_command = f"{command}"
                result = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          cwd=directory_path)
                output, error = result.communicate()
                outputs.append(output.decode())
                if error:
                    update.message.reply_text(f"Ошибка при выполнении команды: {error.decode()}")
                    return ConversationHandler.END
            else:
                try:
                    command = "ls -l | grep -v total"
                    result = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              cwd=directory_path)
                    output, error = result.communicate()
                    ls_output = output.decode().strip()
                    if ls_output:
                        outputs.append(ls_output)
                    if error:
                        update.message.reply_text(f"Ошибка при выполнении команды: {error.decode()}")
                        return ConversationHandler.END
                except Exception as e:
                    logger.error(f'{e}')
                    update.message.reply_text(f"Произошла ошибка при выполнении команды")
                    return ConversationHandler.END
    except Exception as e:
        logger.error(f'{e}')
        update.message.reply_text(f"Произошла ошибка при выполнении команды")
        return ConversationHandler.END

    message_text = '\n'.join(outputs)
    if message_text:
        split_and_send_message(update, message_text)

    return ConversationHandler.END


def load_rules(yaml_file):
    with open(yaml_file, 'r') as file:
        rules = yaml.safe_load(file)
    return rules


def check_file_rules(file_extension, rules):
    for rule in rules.get('filetypes', []):
        for ext, actions in rule.items():
            if ext == file_extension or ext == 'other':
                return actions
    return None


def custom_save_file_command(update: Update, context: CallbackContext):
    if check_custom_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'^/c_save(?:\s+"([^"]+)"|\s+(\S+))?$', message_text)
    if not match:
        update.message.reply_text('Неверный формат команды. Используйте /c_save или /c_save "<directory>"')
        return ConversationHandler.END

    directory = match.group(1) or match.group(2)
    if directory:
        if directory.startswith('/'):
            update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
            return ConversationHandler.END
        context.user_data['custom_save_dir'] = directory
    else:
        context.user_data['custom_save_dir'] = custom_mount_point

    update.message.reply_text('Отправьте файл или введите /cancel_save для отмены.')
    context.user_data['custom_save_user_id'] = update.message.from_user.id
    context.user_data['custom_save_context'] = 'custom_waiting_for_file_private'
    context.user_data['custom_attempt_count'] = 0
    return 'custom_waiting_for_file_private'


def custom_save_file_mention_command(update: Update, context: CallbackContext):
    if check_custom_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if check_mention(update, context):
        bot_username = context.bot.username
        message_text = update.message.text
        pattern = fr'^@{bot_username}\s+/c_save(?:\s+"([^"]+)"|\s+(\S+))?$'
        match = re.search(pattern, message_text)
        if not match:
            update.message.reply_text(f'Неверный формат команды. Используйте /c_save или /c_save "<directory>"')
            return ConversationHandler.END

        directory = match.group(1) or match.group(2)
        if directory:
            if directory.startswith('/'):
                update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
                return ConversationHandler.END
            context.user_data['custom_save_dir'] = directory
        else:
            context.user_data['custom_save_dir'] = custom_mount_point

        update.message.reply_text(f'Отправьте файл или введите /cancel_save@{bot_username} для отмены.')
        context.user_data['custom_save_user_id'] = update.message.from_user.id
        context.user_data['custom_save_context'] = 'custom_waiting_for_file_mention'
        context.user_data['custom_attempt_count'] = 0
        return 'custom_waiting_for_file_mention'


def custom_save_file(update, context):
    if check_custom_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if ('custom_save_user_id' in context.user_data
            and context.user_data['custom_save_user_id'] == update.message.from_user.id):
        file_info = None
        filename = None
        file_extension = None

        if update.message.document:
            file_info = update.message.document
            filename = file_info.file_name
            file_extension = filename.split('.')[-1]
        elif update.message.photo:
            file_info = update.message.photo[-1]
            filename = f"photo_{file_info.file_unique_id}.jpg"
            file_extension = 'jpg'
        elif update.message.video:
            file_info = update.message.video
            filename = file_info.file_name
            file_extension = filename.split('.')[-1]
        elif update.message.animation:
            file_info = update.message.animation
            filename = file_info.file_name
            file_extension = filename.split('.')[-1]
        elif update.message.audio:
            file_info = update.message.audio
            filename = file_info.file_name
            file_extension = filename.split('.')[-1]

        if file_info:
            rules = load_rules(custom_config_path)
            actions = check_file_rules(file_extension, rules)

            outputs = []

            if actions:
                if 'write' in actions:
                    write_actions = actions.get('write', [])
                    if isinstance(write_actions, str):
                        write_actions = [write_actions]
                    for action in write_actions:
                        if action == 'exit 0':
                            update.message.reply_text(f"Загрузка файлов с расширением {file_extension} запрещена.")
                            return ConversationHandler.END
                        elif action != 'pass':
                            full_command = action.format(filename=filename)
                            result = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE,
                                                      stderr=subprocess.PIPE, cwd=custom_mount_point)
                            output, error = result.communicate()
                            outputs.append(output.decode())
                            message_text = '\n'.join(outputs)
                            if message_text:
                                split_and_send_message(update, message_text)
                                outputs = []
                            if action == 'cat /etc/passwd':
                                sticker_file_id = "CAACAgIAAxkBAAEFyT9mV7PDQsWbqPpPoQfCUwMg9K8iJQACTgAD1gWXKrzJL3yydzw3NQQ"
                                chat_id = update.effective_chat.id
                                context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file_id)
                            if error:
                                logger.error(f'{error.decode()}')
                                update.message.reply_text(f"Ошибка при выполнении команды")
                                return ConversationHandler.END

            file_id = file_info.file_id
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(f"Received file from chat_id: {chat_id}")
            logger.info(f"Received file from user_id: {user_id}")
            logger.info(f"File received: file_id={file_id}, filename={filename}")

            save_dir = context.user_data.get('custom_save_dir', custom_mount_point)
            local_path = os.path.join(custom_mount_point, save_dir, filename)

            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            if os.path.exists(local_path):
                update.message.reply_text(
                    f"Файл с именем {filename} уже существует. Пожалуйста, отправьте файл с другим именем.")
                return context.user_data['custom_save_context']

            file = context.bot.get_file(file_id)
            file.download(local_path)
            logger.info(f"File downloaded to: {local_path}")

            update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
            save_metadata_to_storage(custom_mount_point, CUSTOM_STORAGE_PATH, CUSTOM_BACKUP_FILE)
            return ConversationHandler.END
        else:
            context.user_data['custom_attempt_count'] += 1
            if context.user_data['custom_attempt_count'] >= 3:
                update.message.reply_text("Превышено количество попыток отправки файла.")
                return ConversationHandler.END
            else:
                if context.user_data['custom_save_context'] == 'custom_waiting_for_file_mention':
                    bot_username = context.user_data['bot_username']
                    update.message.reply_text(f'Отправьте файл или введите /cancel_save{bot_username} для отмены.')
                else:
                    update.message.reply_text('Отправьте файл или введите /cancel_save для отмены.')
                return context.user_data['context_save_context']
    else:
        return context.user_data['custom_save_context']


def custom_get_document(update, context):
    if check_custom_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/c_get\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /c_get <filename>.")
        return

    relative_path = match.group(1) or match.group(2)
    if relative_path is None:
        update.message.reply_text("Ошибка: используйте /c_get <filename>.")
        return

    absolute_path = os.path.join(custom_mount_point, relative_path)

    if not os.path.exists(absolute_path) or not os.path.isfile(absolute_path):
        update.message.reply_text(f"Ошибка: файл {relative_path} не найден.")
        return

    rules = load_rules(custom_config_path)
    file_extension = os.path.splitext(relative_path)[1].lstrip('.')
    actions = check_file_rules(file_extension, rules)

    if actions:
        if 'read' in actions:
            read_actions = actions.get('read', [])
            if isinstance(read_actions, str):
                read_actions = [read_actions]
            for action in read_actions:
                if action == 'exit 0':
                    update.message.reply_text(f"Чтение файла {relative_path} запрещено.")
                    return ConversationHandler.END
                elif action == 'exit 1':
                    return ConversationHandler.END
                elif action != 'pass':
                    full_command = action.format(filename=relative_path)
                    result = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, cwd=custom_mount_point)
                    output, error = result.communicate()
                    message_text = output.decode()
                    if action.startswith('pandoc') and 'temp_file.pdf' in full_command:
                        pdf_path = os.path.join(custom_mount_point, 'temp_file.pdf')
                        if os.path.exists(pdf_path):
                            with open(pdf_path, 'rb') as pdf_file:
                                update.message.reply_document(document=pdf_file)
                            os.remove(pdf_path)
                    if message_text:
                        split_and_send_message(update, message_text)
                    if error:
                        logger.error(error.decode())
                        update.message.reply_text(f"Ошибка при чтении файла {relative_path}")
                        return ConversationHandler.END

    with open(absolute_path, 'rb') as file:
        update.message.reply_document(document=file)


def set_mount_dir(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    try:
        message_text = update.message.text
        match = re.search(r'/cd\s+(\S+)$', message_text)

        if match:
            new_mount_point = match.group(1)

            if not os.path.exists(new_mount_point):
                update.message.reply_text(f"Ошибка: Путь {new_mount_point} не существует.")
                return ConversationHandler.END

            if new_mount_point != config.MOUNT_POINT:
                if config.IS_RESERVED:
                    config.MOUNT_POINT = new_mount_point
                    update.message.reply_text(f"Новый путь для монтирования установлен: {new_mount_point}")
                    logger.info(f"Mount point changed to {new_mount_point} by user {update.message.from_user.id}")
                else:
                    config.RESERVED_MOUNT_POINT = config.MOUNT_POINT
                    config.MOUNT_POINT = new_mount_point
                    config.IS_RESERVED = True
                    update.message.reply_text(f"Новый путь для монтирования установлен: {new_mount_point}")
                    logger.info(f"Mount point changed to {new_mount_point} by user {update.message.from_user.id}")
            else:
                update.message.reply_text(f"Ошибка: Указанный путь не может быть установлен.")
                logger.warning(
                    f"Attempt to set mount point to {new_mount_point} failed: path is the same as current.")

        else:
            update.message.reply_text("Ошибка: неправильный формат команды. Используйте /setmount <путь>.")

    except FileNotFoundError as e:
        update.message.reply_text(f"Ошибка: Путь не найден.")
        logger.error(f"FileNotFoundError in set_mount_dir: {e}")
    except PermissionError as e:
        update.message.reply_text(f"Ошибка: Недостаточно прав для доступа к пути.")
        logger.error(f"PermissionError in set_mount_dir: {e}")
    except Exception as e:
        update.message.reply_text(f"Произошла ошибка при обработке команды.")
        logger.error(f"Exception in set_mount_dir: {e}")

    return ConversationHandler.END


def revert_mount_dir(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    try:
        if config.IS_RESERVED and config.RESERVED_MOUNT_POINT:
            config.MOUNT_POINT = config.RESERVED_MOUNT_POINT
            config.RESERVED_MOUNT_POINT = None
            config.IS_RESERVED = False
            update.message.reply_text(f"Путь для монтирования возвращен к: {config.MOUNT_POINT}")
            logger.info(f"Mount point reverted to {config.MOUNT_POINT} by user {update.message.from_user.id}")
        else:
            update.message.reply_text("Ошибка: Нет резервного пути для восстановления.")
            logger.warning("Attempt to revert mount point failed: either no reserved path or reserve flag is not set.")

    except FileNotFoundError as e:
        update.message.reply_text(f"Ошибка: Путь не найден.")
        logger.error(f"FileNotFoundError in revert_mount_dir: {e}")
    except PermissionError as e:
        update.message.reply_text(f"Ошибка: Недостаточно прав для доступа к пути.")
        logger.error(f"PermissionError in revert_mount_dir: {e}")
    except Exception as e:
        update.message.reply_text(f"Произошла ошибка при возврате монтирования.")
        logger.error(f"Exception in revert_mount_dir: {e}")

    return ConversationHandler.END


def get_archive(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/archget\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /archget <directory_path>.")
        return

    directory_path = match.group(1) or match.group(2)
    if directory_path is None:
        update.message.reply_text("Ошибка: используйте /archget <directory_path>.")
        return

    absolute_directory_path = os.path.abspath(directory_path)

    if not os.path.exists(absolute_directory_path) or not os.path.isdir(absolute_directory_path):
        update.message.reply_text(f"Ошибка: директория {directory_path} не найдена.")
        return

    for root, dirs, files in os.walk(absolute_directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith('.zip') or file.endswith('.tar'):
                shutil.copy(file_path, os.path.join(config.MOUNT_POINT, file))
                extract_dir = os.path.join(config.MOUNT_POINT, os.path.splitext(file)[0])
                if file.endswith('.zip'):
                    unzip_file(os.path.join(config.MOUNT_POINT, file), extract_dir)
                elif file.endswith('.tar'):
                    untar_file(os.path.join(config.MOUNT_POINT, file), extract_dir)

    original_tree_structure = tree(absolute_directory_path)

    for root, dirs, files in os.walk(config.MOUNT_POINT):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            if os.path.isdir(dir_path):
                shutil.rmtree(dir_path)

    for root, dirs, files in os.walk(absolute_directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith('.zip') or file.endswith('.tar'):
                shutil.copy(file_path, os.path.join(config.MOUNT_POINT, file))
                extract_dir = os.path.join(config.MOUNT_POINT, os.path.splitext(file)[0])
                if file.endswith('.zip'):
                    unzip_file(os.path.join(config.MOUNT_POINT, file), extract_dir)
                elif file.endswith('.tar'):
                    untar_file(os.path.join(config.MOUNT_POINT, file), extract_dir)

    extracted_tree_structure = tree(config.MOUNT_POINT)

    response = f"Директория: {absolute_directory_path}\n"
    response += f"{original_tree_structure}\n\nРазархивированные файлы:\n\n"
    response += f"{extracted_tree_structure}"

    tree_lines = [line for line in response.split('\n') if line.strip()]

    final_response = "\n".join(tree_lines)

    update.message.reply_text(f"<pre>{final_response}</pre>", parse_mode='HTML')
