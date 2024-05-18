import os
import threading
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
from config import logger, USER_ID, MOUNT_POINT
from fs_utils import unmount_fs, start_fuse

fuse_stopped = False


def start(update: Update, context: CallbackContext):
    global fuse_stopped

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    fuse_stopped = False

    update.message.reply_text('Готов принимать команды для работы с файловой системой.')
    return ConversationHandler.END



def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    logger.info(f"Received document from user_id: {user_id}")

    if user_id != int(USER_ID):
        update.message.reply_text('Вы не авторизованы для использования этой команды.')
        return ConversationHandler.END

    document = update.message.document
    file_id = document.file_id
    filename = document.file_name
    logger.info(f"Document received: file_id={file_id}, filename={filename}")

    file = context.bot.get_file(file_id)
    local_path = os.path.join(MOUNT_POINT, filename)
    file.download(local_path)
    logger.info(f"File downloaded to: {local_path}")

    update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
    return ConversationHandler.END


def stop(update: Update, context: CallbackContext):
    global fuse_stopped

    user_id = update.message.from_user.id
    logger.info(f"Stop command received from user_id: {user_id}")

    if user_id != int(USER_ID):
        update.message.reply_text('Вы не авторизованы для использования этой команды.')
        return ConversationHandler.END

    update.message.reply_text('Останавливаю работу файловой системы...')

    unmount_fs()
    fuse_stopped = True

    logger.info("Fuse stopped")

    return ConversationHandler.END
