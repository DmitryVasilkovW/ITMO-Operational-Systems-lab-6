import threading
import signal
import sys

from telegram import Bot, MessageEntity
from telegram.ext import Updater, MessageHandler, Filters, ConversationHandler, CommandHandler
from telegram_bot import handle_private, handle_mention, save_file_command, save_file, save_file_mention_command, \
    mkdir_command, mkdir, mkdir_command_mention
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

    conv_handler_save_file_mention = ConversationHandler(
        entry_points=[MessageHandler(Filters.entity(MessageEntity.MENTION) & Filters.regex(r'\bsave\b'),
                                     save_file_mention_command)],
        states={
            'waiting_for_file_mention': [MessageHandler(~Filters.command, save_file)]
        },
        fallbacks=[]
    )

    conv_handler_save_file_private = ConversationHandler(
        entry_points=[CommandHandler('save', save_file_command)],
        states={
            'waiting_for_file_private': [MessageHandler(~Filters.command, save_file)]
        },
        fallbacks=[]
    )

    conv_handler_mkdir_private = ConversationHandler(
        entry_points=[CommandHandler('mkdir', mkdir_command)],
        states={
            'mkdir_private': [MessageHandler(Filters.text & ~Filters.command, mkdir)]
        },
        fallbacks=[]
    )

    conv_handler_mkdir_mention = ConversationHandler(
        entry_points=[MessageHandler(Filters.entity(MessageEntity.MENTION) & Filters.regex(r'mkdir'),
                                     mkdir_command_mention)],
        states={
            'mkdir_mention': [MessageHandler(Filters.text & ~Filters.command, mkdir)]
        },
        fallbacks=[]
    )

    #########################################################
    # IMPORTANT! DO NOT CHANGE THE ORDER OF ADDING HANDLERS #
    #########################################################
    dp.add_handler(conv_handler_save_file_private)
    dp.add_handler(conv_handler_save_file_mention)
    dp.add_handler(conv_handler_mkdir_private)
    dp.add_handler(conv_handler_mkdir_mention)

    dp.add_handler(MessageHandler(Filters.command & Filters.chat_type.private, handle_private))
    dp.add_handler(MessageHandler(Filters.entity(MessageEntity.MENTION), handle_mention))

    updater.start_polling()
    updater.idle()

    fuse_thread.join()


if __name__ == '__main__':
    main()
