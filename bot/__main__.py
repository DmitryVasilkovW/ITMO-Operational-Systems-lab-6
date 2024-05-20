import threading
import signal
import sys

from telegram import Bot, MessageEntity
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram_bot import start, handle_message, stop
from config import TOKEN, BOT_USERNAME
from fs_utils import start_fuse, unmount_fs


def signal_handler(sig, frame):
    unmount_fs()
    sys.exit(0)


def handle_private(update, context):
    message_text = update.message.text
    if message_text == '/stop':
        stop(update, context)
    elif message_text == '/start':
        start(update, context)


# TODO: fix group mention
def handle_mention(update, context):
    entities = update.message.parse_entities([MessageEntity.MENTION])
    for entity in entities.values():
        if entity.lower() == BOT_USERNAME.lower():
            message_text = update.message.text
            if '/start' in message_text:
                start(update, context)
            elif '/stop' in message_text:
                stop(update, context)



def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.private, handle_private))
    dp.add_handler(MessageHandler(Filters.document & Filters.chat_type.private, handle_message))

    dp.add_handler(MessageHandler(Filters.entity(MessageEntity.MENTION), handle_mention))

    updater.start_polling()
    updater.idle()

    fuse_thread.join()


if __name__ == '__main__':
    main()
