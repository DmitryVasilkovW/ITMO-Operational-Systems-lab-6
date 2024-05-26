import os
import shutil
import threading
import re

from telegram import Update, MessageEntity, Bot
from telegram.ext import CallbackContext, ConversationHandler, MessageHandler, Filters

from bot.converter import convert_png_to_jpg, create_empty_jpg
from bot.collect_metadata import save_metadata_to_storage
from config import logger, MOUNT_POINT, TOKEN, STORAGE_PATH, BACKUP_FILE
from fs_utils import unmount_fs, start_fuse

fuse_stopped = False


def check_mention(update, context) -> bool:
    if 'bot_username' not in context.user_data:
        context.user_data['bot_username'] = "@" + Bot(TOKEN).get_me().username

    bot_username = context.user_data['bot_username']
    entities = update.message.parse_entities([MessageEntity.MENTION]).values()

    return bot_username in entities


def handle_private(update, context):
    message_text = update.message.text

    if message_text == '/stop':
        stop_command(update, context)

    elif message_text == '/start':
        start_command(update, context)

    elif '/mkdir' in message_text:
        mkdir(update, context)

    elif '/mv' in message_text:
        move(update, context)

    elif message_text.startswith('/convert '):
        convert_command(update, context)


def handle_mention(update, context):
    if check_mention(update, context):
        message_text = update.message.text

        if '/start' in message_text:
            start_command(update, context)

        elif '/stop' in message_text:
            stop_command(update, context)

        elif '/mkdir' in message_text:
            mkdir(update, context)

        elif '/mv' in message_text:
            move(update, context)

        elif '/convert ' in message_text:
            convert_command(update, context)


def save_file_command(update, context):
    update.message.reply_text('Отправьте файл: ')
    context.user_data['save_context'] = 'waiting_for_file_private'
    return 'waiting_for_file_private'


def save_file_mention_command(update, context):
    if check_mention(update, context):
        update.message.reply_text('Отправьте файл: ')
        context.user_data['save_context'] = 'waiting_for_file_mention'
        return 'waiting_for_file_mention'


def save_file(update: Update, context: CallbackContext):
    if update.message.document:
        document = update.message.document
        file_id = document.file_id
        filename = document.file_name
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id
        logger.info(f"Received document from chat_id: {chat_id}")
        logger.info(f"Received document from user_id: {user_id}")
        logger.info(f"Document received: file_id={file_id}, filename={filename}")

        local_path = os.path.join(MOUNT_POINT, filename)

        if os.path.exists(local_path):
            update.message.reply_text(
                f"Файл с именем {filename} уже существует. Пожалуйста, отправьте файл с другим именем.")
            return context.user_data['save_context']

        file = context.bot.get_file(file_id)
        file.download(local_path)
        logger.info(f"File downloaded to: {local_path}")

        update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
        save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        return ConversationHandler.END
    else:
        update.message.reply_text("Пожалуйста, отправьте документ.")
        return ConversationHandler.END


def mkdir(update: Update, context: CallbackContext):
    match = re.search(r'/mkdir\s+(\S+)', update.message.text)
    if match:
        directory_name = match.group(1)

        logger.info(match)
        if re.search(r'/mkdir\s+(\S+)\s+(\S+)', update.message.text) is not None:
            update.message.reply_text(
                "Ошибка: команда должна содержать только одно слово.")
            return ConversationHandler.END

        if '/' in directory_name:
            update.message.reply_text(
                "Ошибка: команда должна содержать только одно слово без символов '/'.")
            return ConversationHandler.END

        new_dir_path = os.path.join(MOUNT_POINT, directory_name)

        try:
            os.makedirs(new_dir_path, exist_ok=True, mode=0o777)
            update.message.reply_text(f"Директория {directory_name} успешно создана.")
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(
                f"Directory {directory_name} created successfully at {new_dir_path} from chat_id {chat_id} and user_id {user_id}.")
            save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Error creating directory {directory_name}: {e}")
            update.message.reply_text(f"Ошибка при создании директории")
    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь имя директории. Убедитесь, что команда введена правильно.")

    return ConversationHandler.END


def move(update, context):
    message_text = update.message.text
    match = re.search(r'/mv\s+(\S+)\s+(\S+)$', message_text)

    if match:
        source = match.group(1)
        destination = match.group(2)
        source_path = os.path.join(MOUNT_POINT, source)
        destination_path = os.path.join(MOUNT_POINT, destination)

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
            save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при перемещении {source} в {destination}: {e}")
            update.message.reply_text(f"Ошибка при перемещении")
    else:
        update.message.reply_text("Ошибка: неправильный формат команды. Используйте /mv <источник> <назначение>.")

    return ConversationHandler.END


def start_command(update: Update, context: CallbackContext):
    global fuse_stopped

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    fuse_stopped = False

    update.message.reply_text('Готов принимать команды для работы с файловой системой.')
    save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    return ConversationHandler.END


def stop_command(update: Update, context: CallbackContext):
    global fuse_stopped

    user_id = update.message.from_user.id
    logger.info(f"Stop command received from user_id: {user_id}")

    update.message.reply_text('Останавливаю работу файловой системы...')

    unmount_fs()
    fuse_stopped = True

    logger.info("Fuse stopped")
    save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    return ConversationHandler.END


def convert_command(update: Update, context: CallbackContext):
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
                    output_path_jpg = os.path.join(MOUNT_POINT, output_filename_jpg)
                    output_path_png = os.path.join(MOUNT_POINT, filename)

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
                    output_path_png = os.path.join(MOUNT_POINT, output_filename_png)
                    output_path_jpg = os.path.join(MOUNT_POINT, filename)

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
                    output_path = os.path.join(MOUNT_POINT, filename)
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
                response_message += "\nХотите перезаписать файлы? (да/нет)"

                conflicting_files_filtered = conflicting_files

                def handle_overwrite_response(update, context):
                    if update.message.text.lower() in ["да", "ок", "конечно", "хорошо", "+"]:
                        overwritten_files = []
                        for filename, conflicting_filename, message in conflicting_files_filtered:
                            source_path = os.path.join(path, filename)
                            destination_path = os.path.join(MOUNT_POINT, conflicting_filename)
                            shutil.copy(source_path, destination_path)
                            overwritten_files.append(f"{filename} -> {conflicting_filename}")
                            # Создаем пару PNG и JPG
                            if filename.endswith(".png"):
                                output_filename_jpg = filename[:-4] + '.jpg'
                                output_path_jpg = os.path.join(MOUNT_POINT, output_filename_jpg)
                                create_empty_jpg(output_path_jpg)
                                shutil.copy(source_path, output_path_jpg)
                            elif filename.endswith(".jpg"):
                                output_filename_png = filename[:-4] + '.png'
                                output_path_png = os.path.join(MOUNT_POINT, output_filename_png)
                                shutil.copy(source_path, output_path_png)

                        overwrite_response_message = "Перезаписанные файлы:\n" + "\n".join(overwritten_files)
                        update.message.reply_text(overwrite_response_message)
                    elif update.message.text.lower() in ["нет", "не", "неа", "-"]:
                        update.message.reply_text("Файлы не были перезаписаны.")

                    return ConversationHandler.END

                update.message.reply_text(response_message)

                context.dispatcher.add_handler(
                    MessageHandler(Filters.text & ~Filters.command, handle_overwrite_response))
                return

            update.message.reply_text(response_message)

            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)

            logger.info(f"Files in directory {path} processed successfully from chat_id {chat_id} and user_id {user_id}.")
        except Exception as e:
            logger.error(f"Error processing files in directory {path}: {e}")
            update.message.reply_text(f"Ошибка при копировании файлов из директории {path}")
    else:
        update.message.reply_text("Ошибка: неправильный формат команды. Используйте /convert <путь>.")

    return ConversationHandler.END
