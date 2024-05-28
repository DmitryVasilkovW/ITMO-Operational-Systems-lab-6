import threading
import signal
import sys

from telegram import Bot, MessageEntity
from telegram.ext import Updater, MessageHandler, Filters, ConversationHandler, CommandHandler
from telegram_bot import handle_private, handle_mention, save_file_command, save_file, save_file_mention_command, \
    handle_overwrite_response, convert_mention_command, convert_private_command, cancel, file_list
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
    bot_username = dp.user_data['bot_username']
    file_list()

    conv_handler_convert_command_private = ConversationHandler(
        entry_points=[MessageHandler(Filters.chat_type.private & Filters.regex(fr'^(/convert(?:\s+\S+)+)$'), convert_private_command)],
        states={
            'handle_overwrite_response_private': [MessageHandler(Filters.text & ~Filters.command, handle_overwrite_response)]
        },
        fallbacks=[]
    )

    conv_handler_convert_command_mention = ConversationHandler(
        entry_points=[MessageHandler(Filters.entity(MessageEntity.MENTION) & Filters.regex(fr'^{bot_username}\s+(/convert(?:\s+\S+)+)$'),
                                     convert_mention_command)],
        states={
            'handle_overwrite_response_mention': [MessageHandler(~Filters.command, handle_overwrite_response)]
        },
        fallbacks=[]
    )

    conv_handler_save_file_mention = ConversationHandler(
        entry_points=[MessageHandler(
            Filters.entity(MessageEntity.MENTION) & Filters.regex(fr'^{bot_username}\s+(/save|(/save(?:\s+\S+)+))$'),
            save_file_mention_command)],
        states={
            'waiting_for_file_mention': [
                MessageHandler(Filters.regex(
                    fr'^({bot_username}\s+/cancel_save|/cancel_save{bot_username}|/cancel_save\s+{bot_username})$'),
                    cancel),
                MessageHandler(~Filters.command, save_file)
            ]
        },
        fallbacks=[]
    )

    conv_handler_save_file_private = ConversationHandler(
        entry_points=[MessageHandler(Filters.chat_type.private & Filters.regex(fr'^(/save|(/save(?:\s+\S+)+))$'),
                                     save_file_command)],
        states={
            'waiting_for_file_private': [
                CommandHandler('cancel_save', cancel),
                MessageHandler(~Filters.command, save_file)
            ]
        },
        fallbacks=[]
    )

    #########################################################
    # IMPORTANT! DO NOT CHANGE THE ORDER OF ADDING HANDLERS #
    #########################################################
    dp.add_handler(conv_handler_save_file_private)
    dp.add_handler(conv_handler_save_file_mention)
    dp.add_handler(conv_handler_convert_command_private)
    dp.add_handler(conv_handler_convert_command_mention)

    dp.add_handler(MessageHandler(Filters.command & Filters.chat_type.private, handle_private))
    dp.add_handler(MessageHandler(Filters.entity(MessageEntity.MENTION), handle_mention))

    updater.start_polling()
    updater.idle()

    fuse_thread.join()


if __name__ == '__main__':
    main()
