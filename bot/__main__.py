import threading
import signal
import sys

from telegram import Bot, MessageEntity
from telegram.ext import Updater, MessageHandler, Filters
from telegram_bot import handle_file_save, handle_private, handle_mention
from config import TOKEN
from fs_utils import start_fuse, unmount_fs


def signal_handler(sig, frame):
    unmount_fs()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.user_data['bot_username'] = "@" + Bot(TOKEN).get_me().username

    dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.private, handle_private))
    dp.add_handler(MessageHandler(Filters.entity(MessageEntity.MENTION), handle_mention))

    dp.add_handler(MessageHandler(Filters.document, handle_file_save))

    updater.start_polling()
    updater.idle()

    fuse_thread.join()


if __name__ == '__main__':
    main()
