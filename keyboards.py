from telegram import ReplyKeyboardMarkup
import strings

def get_main_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_CHECK', lang)],
            [strings.get('BTN_HELP', lang), strings.get('BTN_SETTINGS', lang)]
        ], 
        resize_keyboard=True
    )

def get_settings_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_LANG_EN'), strings.get('BTN_LANG_MS')], # Language buttons usually static or localized names
            [strings.get('BTN_CLEAR_HISTORY', lang)], 
            [strings.get('BTN_BACK', lang)]
        ],
        resize_keyboard=True
    )

def get_cancel_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [[strings.get('BTN_CANCEL', lang)]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def get_retry_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [[strings.get('BTN_TRY_AGAIN', lang), strings.get('BTN_CANCEL', lang)]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def get_admin_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_ADMIN_ADD', lang), strings.get('BTN_ADMIN_DEL', lang)],
            [strings.get('BTN_ADMIN_STATS', lang), strings.get('BTN_ADMIN_EXIT', lang)]
        ],
        resize_keyboard=True
    )

def get_program_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_PROG_IT', lang)],
            [strings.get('BTN_PROG_MM', lang)],
            [strings.get('BTN_PROG_CS', lang)],
            [strings.get('BTN_PROG_MD', lang)],
            [strings.get('BTN_PROG_AG', lang)],
            [strings.get('BTN_PROG_LA', lang)],
            [strings.get('BTN_CANCEL', lang)]
        ],
        resize_keyboard=True
    )
