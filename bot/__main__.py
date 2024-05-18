import threading
import signal
import sys
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram_bot import start, handle_message, stop
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

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("stop", stop))
    dp.add_handler(MessageHandler(Filters.document, handle_message))

    updater.start_polling()
    updater.idle()

    fuse_thread.join()


if __name__ == '__main__':
    main()
