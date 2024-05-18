import logging
import os
import errno
from fuse import FUSE, FuseOSError, Operations
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from dotenv import load_dotenv

logging.basicConfig(
    filename='logfile.log', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

load_dotenv()

TOKEN = os.getenv('TOKEN')
USER_ID = os.getenv('USER_ID')
MOUNT_POINT = os.getenv('MOUNT_POINT')

class LocalFS(Operations):
    def getattr(self, path, fh=None):
        st = os.lstat(path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                                        'st_gid', 'st_mode', 'st_mtime',
                                                        'st_nlink', 'st_size', 'st_uid'))

    def readdir(self, path, fh):
        return ['.', '..'] + os.listdir(path)

    def read(self, path, size, offset, fh):
        with open(path, 'rb') as f:
            f.seek(offset)
            return f.read(size)

    def write(self, path, data, offset, fh):
        with open(path, 'r+b') as f:
            f.seek(offset)
            f.write(data)
        return len(data)

    def create(self, path, mode, fi=None):
        with open(path, 'w') as f:
            pass
        return 0

    def unlink(self, path):
        os.unlink(path)
        return 0

def start(update: Update, context: CallbackContext):
    update.message.reply_text('Привет! Я готов принимать команды для работы с файловой системой.')
    return ConversationHandler.END


def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if user_id != int(USER_ID):
        update.message.reply_text('Вы не авторизованы для использования этой команды.')
        return ConversationHandler.END

    document = update.message.document
    file_id = document.file_id
    filename = document.file_name

    file = context.bot.get_file(file_id)
    local_path = MOUNT_POINT + filename
    file.download(local_path)

    update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
    return ConversationHandler.END


def main():
    fuse = FUSE(LocalFS(), MOUNT_POINT, foreground=True)

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
