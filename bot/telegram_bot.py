import os
import threading

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


def handle_mention(update, context):
    if check_mention(update, context):
        message_text = update.message.text
        if '/start' in message_text:
            start_command(update, context)
        elif '/stop' in message_text:
            stop_command(update, context)


def save_file_command(update, context):
    update.message.reply_text('Отправьте файл: ')

    return 'waiting_for_file'


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

        file = context.bot.get_file(file_id)
        local_path = os.path.join(MOUNT_POINT, filename)
        file.download(local_path)
        logger.info(f"File downloaded to: {local_path}")

        update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
        return ConversationHandler.END
    else:
        update.message.reply_text("Пожалуйста, отправьте документ.")
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
