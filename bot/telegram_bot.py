import os
import threading
import re

from telegram import Update, MessageEntity, Bot
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, Filters
from config import logger, MOUNT_POINT, TOKEN
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


def handle_mention(update, context):
    if check_mention(update, context):
        message_text = update.message.text
        if '/start' in message_text:
            start_command(update, context)
        elif '/stop' in message_text:
            stop_command(update, context)
        elif '/mkdir' in message_text:
            mkdir(update, context)


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
        return ConversationHandler.END
    else:
        update.message.reply_text("Пожалуйста, отправьте документ.")
        return ConversationHandler.END


def mkdir(update, context):
    logger.info('in mkdir')
    match = re.search(r'/mkdir\s+(\S+)', update.message.text)
    if match:
        directory_name = match.group(1)
        new_dir_path = os.path.join(MOUNT_POINT, directory_name)

        try:
            os.makedirs(new_dir_path, exist_ok=True)
            update.message.reply_text(f"Директория {directory_name} успешно создана.")
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(
                f"Directory {directory_name} created successfully at {new_dir_path} from chat_id {chat_id} and user_id {user_id}.")
        except Exception as e:
            logger.error(f"Error creating directory {directory_name}: {e}")
            update.message.reply_text(f"Ошибка при создании директории: {e}")
    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь имя директории. Убедитесь, что команда введена правильно.")

    return ConversationHandler.END


def start_command(update: Update, context: CallbackContext):
    global fuse_stopped

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    fuse_stopped = False

    update.message.reply_text('Готов принимать команды для работы с файловой системой.')
    return ConversationHandler.END


def stop_command(update: Update, context: CallbackContext):
    global fuse_stopped

    user_id = update.message.from_user.id
    logger.info(f"Stop command received from user_id: {user_id}")

    update.message.reply_text('Останавливаю работу файловой системы...')

    unmount_fs()
    fuse_stopped = True

    logger.info("Fuse stopped")

    return ConversationHandler.END
