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
            [strings.get('BTN_LANGUAGES', lang)],
            [strings.get('BTN_CLEAR_HISTORY', lang)], 
            [strings.get('BTN_BACK', lang)]
        ],
        resize_keyboard=True
    )

def get_language_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_LANG_EN'), strings.get('BTN_LANG_MS')],
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
    return ReplyKeyboardMarkup([
        [strings.get('BTN_ADMIN_MANAGE', lang)],
        [strings.get('BTN_ADMIN_BROADCAST', lang), strings.get('BTN_ADMIN_STATS', lang)],
        [strings.get('BTN_ADMIN_EXIT', lang)]
    ], resize_keyboard=True, one_time_keyboard=False)

def get_admin_manage_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_ADMIN_DEL', lang)],
            [strings.get('BTN_ADMIN_LIST', lang), strings.get('BTN_ADMIN_SEARCH', lang)],
            [strings.get('BTN_BACK', lang)]
        ],
        resize_keyboard=True
    )


def get_search_mode_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_SEARCH_SIMPLE', lang)],
            [strings.get('BTN_SEARCH_DETAIL', lang)],
            [strings.get('BTN_CANCEL', lang)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_confirm_menu(lang='EN'):
    return ReplyKeyboardMarkup(
        [
            [strings.get('BTN_CONFIRM_YES', lang), strings.get('BTN_CONFIRM_NO', lang)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
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
