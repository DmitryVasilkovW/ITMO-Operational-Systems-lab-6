import errno
import logging
import os
import stat
import time
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


class MemoryFS(Operations):
    def __init__(self):
        self.files = {}
        self.data = {}
        now = time.time()
        self.files['/'] = dict(st_mode=(stat.S_IFDIR | 0o755), st_ctime=now, st_mtime=now, st_atime=now, st_nlink=2)

    def getattr(self, path, fh=None):
        if path not in self.files:
            raise FuseOSError(errno.ENOENT)
        return self.files[path]

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files if x != '/' and x.startswith(path)]

    def create(self, path, mode):
        self.files[path] = dict(st_mode=(stat.S_IFREG | mode), st_nlink=1, st_size=0,
                                st_ctime=time.time(), st_mtime=time.time(), st_atime=time.time())
        self.data[path] = b''
        return 0

    def write(self, path, data, offset, fh):
        self.data[path] = self.data[path][:offset] + data
        self.files[path]['st_size'] = len(self.data[path])
        return len(data)

    def read(self, path, size, offset, fh):
        return self.data[path][offset:offset + size]

    def mkdir(self, path, mode):
        self.files[path] = dict(st_mode=(stat.S_IFDIR | mode), st_nlink=2,
                                st_ctime=time.time(), st_mtime=time.time(), st_atime=time.time())
        self.files['/']['st_nlink'] += 1

    def unlink(self, path):
        self.files.pop(path)
        self.data.pop(path, None)

    def rmdir(self, path):
        self.files.pop(path)
        self.files['/']['st_nlink'] -= 1


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


def main():
    if not os.path.exists(MOUNT_POINT):
        os.makedirs(MOUNT_POINT)

    # Запускаем файловую систему FUSE
    FUSE(MemoryFS(), MOUNT_POINT, foreground=True)

    # Настраиваем Telegram бота
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
