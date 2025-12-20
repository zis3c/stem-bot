from telegram import ReplyKeyboardMarkup
import strings

def get_main_menu():
    return ReplyKeyboardMarkup(
        [[strings.BTN_CHECK, strings.BTN_HELP]], 
        resize_keyboard=True
    )

def get_cancel_menu():
    return ReplyKeyboardMarkup(
        [[strings.BTN_CANCEL]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def get_retry_menu():
    return ReplyKeyboardMarkup(
        [[strings.BTN_TRY_AGAIN, strings.BTN_CANCEL]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def get_admin_menu():
    return ReplyKeyboardMarkup(
        [
            [strings.BTN_ADMIN_ADD, strings.BTN_ADMIN_DEL],
            [strings.BTN_ADMIN_STATS, strings.BTN_ADMIN_EXIT]
        ],
        resize_keyboard=True
    )
