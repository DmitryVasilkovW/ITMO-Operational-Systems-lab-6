import os
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from config import logger, USER_ID, MOUNT_POINT


def start(update: Update, context: CallbackContext):
    update.message.reply_text('Привет! Я готов принимать команды для работы с файловой системой.')
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
