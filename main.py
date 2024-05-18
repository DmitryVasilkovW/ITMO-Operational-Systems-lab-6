import os
from fuse import FUSE
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from memory_fs import MemoryFS
from telegram_bot import start, handle_message
from config import TOKEN, MOUNT_POINT, logger


def main():
    if not os.path.exists(MOUNT_POINT):
        os.makedirs(MOUNT_POINT)

    if not os.path.ismount(MOUNT_POINT):
        FUSE(MemoryFS(), MOUNT_POINT, foreground=True, allow_other=True, nonempty=True)
        logger.info(f"File system successfully mounted at {MOUNT_POINT}")
    else:
        logger.info(f"File system already mounted at {MOUNT_POINT}")

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
