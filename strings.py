# Localization (i18n)

STRINGS = {
    'EN': {
        'WELCOME_MSG': (
            "*Hi {name}!*\n\n"
            "I am the *Eligible STEM Bot*.\n"
            "I can verify your membership status instantly.\n\n"
            "👇 *Use the menu below to begin.*"
        ),
        'HELP_MSG': (
            "*About This Bot*\n\n"
            "This service checks the STEM USAS membership database.\n"
            "It connects securely to the official records.\n\n"
            "Dev: @zis3c"
        ),
        'PROMPT_MATRIC': "Step 1/2\n\nPlease type your *Matric Number*:\n(Example: `I24067510`)",
        'PROMPT_IC': "Matric: `{matric}`\n\nStep 2/2\nNow enter the *Last 4 Digits* of your IC:\n(Example: `********1807`)",
        'PROMPT_LOADING': "*Verifying...*",
        
        'VERIFICATION_SUCCESS': (
            "*MEMBERSHIP VERIFIED* 🎉\n\n"
            "*Name*: *{name}*\n"
            "*Matric*: *{matric}*\n"
            "*Program*: *{program}*\n\n"
            "*Register time*: {timestamp}"
        ),
        
        'ERR_INVALID_MATRIC': "*Invalid Matric Format!*\nPlease try again (e.g. `I24067510`)",
        'ERR_INVALID_IC': "*Invalid IC!*\nPlease enter exactly 4 digits.",
        'ERR_DB_CONNECTION': "System Error: Database unavailable.",
        'ERR_NOT_FOUND': "*Not Found*\nMatric Number not in records.",
        'ERR_CANCEL': "Oh okay cancelled.",
        'ERR_ACCESS_DENIED': "*Access Denied*\nYou are not an admin.",
        
        'STATUS_PENDING': "*MEMBERSHIP PENDING* ⏳",
        'STATUS_REJECT': "*MEMBERSHIP REJECTED* 🚫",
        'NOTIFY_NEW_REG': "🚨 *New Registration*\n\nName: {name}\nMatric: {matric}\nResit: {resit}",
        'BTN_APPROVE': "Approve ✅",
        'BTN_REJECT': "Reject 🚫",
        'MSG_APPROVED': "✅ Approved {name}.",
        'MSG_REJECTED': "🚫 Rejected {name}.",
        
        # Buttons
        'BTN_CHECK': "Check Membership",
        'BTN_HELP': "Help",
        'BTN_SETTINGS': "Settings",
        'BTN_CANCEL': "Cancel",
        'BTN_TRY_AGAIN': "Try Again",
        'BTN_BACK': "Back",
        
        'BTN_CLEAR_HISTORY': "Clear Chat History",
        'MSG_HISTORY_CLEARED': "Chat history cleared (session reset).",
        
        'BTN_LANGUAGES': "Languages",
        'BTN_LANG_EN': "🇬🇧 English",
        'BTN_LANG_MS': "🇲🇾 Bahasa Melayu",
        'MSG_LANG_CHANGED': "Language changed to English! 🇬🇧",
        'MSG_SELECT_LANG': "🌐 *Select Language*",
        
        # Admin - Keep English for Admins usually, but good to have structure
        'ADMIN_DASHBOARD': "*Admin Dashboard*\nSelect an action:",
        'ADMIN_STATS': "*Database Stats*\n\nTotal Members: *{total}*",
        'ADMIN_ADD_MATRIC': "*Add Member*\nEnter Matric Number:",
        'ADMIN_ADD_NAME': "Enter *Full Name*:",
        'ADMIN_ADD_IC': "Enter *Full IC Number*:\n(Example: 020512081234)",
        'ADMIN_ADD_PROG': "Enter *Program Code* (e.g. CS230):",
        'ADMIN_ADD_SUCCESS': "*Success!*\nAdded {name} ({matric})",
        'ADMIN_DEL_START': "*Delete Member*\nEnter Matric Number to delete:",
        'ADMIN_DEL_SUCCESS': "*Deleted*\nRow {row} removed.",
        'ADMIN_DEL_NOT_FOUND': "Matric not found.",
        'ADMIN_SAVING': "Saving...",
        'ADMIN_SEARCHING': "Searching...",
        'ADMIN_EXIT': "Exiting Admin Mode.",
        'ADMIN_LIST_HEADER': "*Member List* (Top {limit}):\n\n{items}",
        'ADMIN_LIST_EMPTY': "No members found.",
        'ADMIN_SEARCH_PROMPT': "Enter *Name*, *Matric*, or *IC* to search:",
        'ADMIN_SEARCH_RESULT': "*Search Results* for '{query}':\n\n{items}",
        'ADMIN_SEARCH_EMPTY': "No matches found for '{query}'.",
        
        'BTN_ADMIN_MANAGE': "Manage Members",
        'BTN_ADMIN_STATUS': "Status Members",
        'BTN_STATUS_VERIFIED': "Verified",
        'BTN_STATUS_PENDING': "Pending",
        'BTN_STATUS_REJECTED': "Rejected",
        'BTN_STATUS_PENDING': "Pending",
        'BTN_STATUS_REJECTED': "Rejected",
        'BTN_ADMIN_CHECK_PENDING': "Check Pending ⏳",
        'BTN_ADMIN_DEL': "Delete Member",
        
        'BTN_SA_MAINTENANCE': "Maintenance Mode",
        'BTN_SA_ADMINS': "Manage Admins",
        'BTN_SA_HEALTH': "System Health",
        'BTN_SA_REFRESH': "Refresh Config",
        'MSG_CONFIG_REFRESHED': "✅ *Configuration Refreshed!*",

        'BTN_SA_ADD_ADMIN': "Add Admin",
        'BTN_SA_DEL_ADMIN': "Delete Admin",
        'BTN_SA_LIST_ADMIN': "List Admins",
        'BTN_SA_EXIT': "Exit SuperAdmin",
        
        'PROMPT_SA_ADD': "Please reply with the *Telegram ID* (User ID) to add as Admin:",
        'PROMPT_SA_DEL': "Please reply with the *Telegram ID* to remove:",
        'MSG_SA_ADDED': "✅ Admin added successfully!",
        'MSG_SA_DELETED': "✅ Admin removed successfully!",
        'ERR_SA_INVALID_ID': "⚠️ Invalid ID format. Must be numeric.",

        'ERR_SA_ALREADY_ADMIN': "⚠️ User is already an Admin.",
        'MSG_SA_PROMOTED': "🎉 Congratulations! You have been promoted to Admin.",
        
        'BTN_ADMIN_LIST': "List Members",
        'BTN_ADMIN_SEARCH': "Search Member",
        'BTN_ADMIN_CHECK_PENDING': "Check Pending",
        'BTN_ADMIN_BROADCAST': "Broadcast",
        'BTN_ADMIN_STATS': "Stats",
        'BTN_ADMIN_EXIT': "Exit Admin",
        
        'BTN_CONFIRM_YES': "Confirm Send",
        'BTN_CONFIRM_NO': "Cancel",
        
        'ADMIN_BROADCAST_PROMPT': "Enter message to broadcast to all users:",
        'ADMIN_BROADCAST_CONFIRM': "Preview:\n\n{msg}\n\n*Send to {count} users?*",
        'ADMIN_BROADCAST_START': "Sending...",
        'ADMIN_BROADCAST_DONE': "*Broadcast Complete* 📢\n\nSuccess: {success}\nBlocked/Failed: {failed}",
        
        # Programs
        'BTN_PROG_IT': "DIPLOMA TEKNOLOGI MAKLUMAT",
        'BTN_PROG_MM': "DIPLOMA MULTIMEDIA DENGAN DAKWAH",
        'BTN_PROG_CS': "IJAZAH SARJANA MUDA SAINS KOMPUTER",
        'BTN_PROG_MD': "IJAZAH SARJANA MUDA MULTIMEDIA KREATIF",
        'BTN_PROG_AG': "IJAZAH SARJANA MUDA PERTANIAN",
        'BTN_PROG_LA': "IJAZAH SARJANA MUDA SENI BINA LANDSKAP",
    },
    'MS': {
        'WELCOME_MSG': (
            "*Hai {name}!*\n\n"
            "Saya *Eligible STEM Bot*.\n"
            "Saya boleh semak status keahlian anda dengan pantas.\n\n"
            "👇 *Gunakan menu di bawah untuk mula.*"
        ),
        'HELP_MSG': (
            "*Tentang Bot Ini*\n\n"
            "Perkhidmatan ini menyemak pangkalan data keahlian STEM USAS.\n"
            "Ia bersambung secara selamat ke rekod rasmi.\n\n"
            "Dev: @zis3c"
        ),
        'PROMPT_MATRIC': "Langkah 1/2\n\nSila taip *Nombor Matrik* anda:\n(Contoh: `I24067510`)",
        'PROMPT_IC': "Matrik: `{matric}`\n\nLangkah 2/2\nSekarang masukkan *4 Digit Terakhir* IC anda:\n(Contoh: `********1807`)",
        'PROMPT_LOADING': "*Sedang Semak...*",
        
        'VERIFICATION_SUCCESS': (
            "*KEAHLIAN DISAHKAN* 🎉\n\n"
            "*Nama*: *{name}*\n"
            "*Matrik*: *{matric}*\n"
            "*Program*: *{program}*\n\n"
            "*Masa Daftar*: {timestamp}"
        ),
        
        'ERR_INVALID_MATRIC': "*Format Matrik Tidak Sah!*\nSila cuba lagi (cth. `I24067510`)",
        'ERR_INVALID_IC': "*IC Tidak Sah!*\nSila masukkan tepat 4 digit.",
        'ERR_DB_CONNECTION': "Ralat Sistem: Pangkalan data tidak tersedia.",
        'ERR_NOT_FOUND': "*Tidak Dijumpai*\nNombor Matrik tiada dalam rekod.",
        'ERR_CANCEL': "Oh okay dibatalkan.",
        'ERR_ACCESS_DENIED': "*Akses Ditolak*\nAnda bukan admin.",
        
        'STATUS_PENDING': "*KEAHLIAN SEDANG DIPROSES* ⏳",
        'STATUS_REJECT': "*KEAHLIAN DITOLAK* 🚫",
        'NOTIFY_NEW_REG': "🚨 *Pendaftaran Baru*\n\nNama: {name}\nMatrik: {matric}\nResit: {resit}",
        'BTN_APPROVE': "Luluskan ✅",
        'BTN_REJECT': "Tolak 🚫",
        'MSG_APPROVED': "✅ Diluluskan {name}.",
        'MSG_REJECTED': "🚫 Ditolak {name}.",
        
        # Buttons
        'BTN_CHECK': "Semak Keahlian",
        'BTN_HELP': "Info",
        'BTN_SETTINGS': "Tetapan",
        'BTN_CANCEL': "Batal",
        'BTN_TRY_AGAIN': "Cuba Lagi",
        'BTN_BACK': "Kembali",
        
        'BTN_CLEAR_HISTORY': "Padam Sejarah Sembang",
        'MSG_HISTORY_CLEARED': "Sejarah sembang dipadam (sesi reset).",
        
        'BTN_LANGUAGES': "Bahasa",
        'BTN_LANG_EN': "🇬🇧 English",
        'BTN_LANG_MS': "🇲🇾 Bahasa Melayu",
        'MSG_LANG_CHANGED': "Bahasa ditukar kepada Bahasa Melayu! 🇲🇾",
        'MSG_SELECT_LANG': "🌐 *Pilih Bahasa*",
        
        # Admin - Fallback to English often okay, but can translate
        'ADMIN_DASHBOARD': "*Admin Dashboard*\nPilih tindakan:",
        'ADMIN_STATS': "*Statistik Pangkalan Data*\n\nJumlah Ahli: *{total}*",
        'ADMIN_ADD_MATRIC': "*Tambah Ahli*\nMasukkan Nombor Matrik:",
        'ADMIN_ADD_NAME': "Masukkan *Nama Penuh*:",
        'ADMIN_ADD_IC': "Masukkan *No Kad Pengenalan Penuh*:\n(Contoh: 020512081234)",
        'ADMIN_ADD_PROG': "Masukkan *Kod Program* (cth: CS230):",
        'ADMIN_ADD_SUCCESS': "*Berjaya!*\nDitambah {name} ({matric})",
        'ADMIN_DEL_START': "*Padam Ahli*\nMasukkan Nombor Matrik untuk dibuang:",
        'ADMIN_DEL_SUCCESS': "*Dipadam*\nBaris {row} dikeluarkan.",
        'ADMIN_DEL_NOT_FOUND': "Matrik tidak dijumpai.",
        'ADMIN_SAVING': "Menyimpan...",
        'ADMIN_SEARCHING': "Mencari...",
        'ADMIN_EXIT': "Keluar Mod Admin.",
        'ADMIN_LIST_HEADER': "*Senarai Ahli* (Top {limit}):\n\n{items}",
        'ADMIN_LIST_EMPTY': "Tiada ahli dijumpai.",
        'ADMIN_SEARCH_PROMPT': "Masukkan *Nama*, *Matrik*, atau *IC* untuk carian:",
        'ADMIN_SEARCH_RESULT': "*Keputusan Carian* untuk '{query}':\n\n{items}",
        'ADMIN_SEARCH_EMPTY': "Tiada padanan untuk '{query}'.",
        
        'BTN_ADMIN_MANAGE': "Urus Ahli",
        'BTN_ADMIN_STATUS': "Status Ahli",
        'BTN_STATUS_VERIFIED': "Disahkan",
        'BTN_STATUS_PENDING': "Sedang Diproses",
        'BTN_STATUS_REJECTED': "Ditolak",
        'BTN_ADMIN_ADD': "Tambah Ahli",
        'BTN_ADMIN_DEL': "Padam Ahli",
        'BTN_ADMIN_LIST': "Senarai Ahli",
        'BTN_ADMIN_SEARCH': "Cari Ahli",
        'BTN_ADMIN_CHECK_PENDING': "Semak Tertunda ⏳",
        'BTN_ADMIN_BROADCAST': "Hebahan",
        'BTN_ADMIN_STATS': "Statistik",
        'BTN_ADMIN_EXIT': "Keluar Admin",
        
        'BTN_SA_MAINTENANCE': "Mod Penyelenggaraan",
        'BTN_SA_ADMINS': "Urus Admin",
        'BTN_SA_HEALTH': "Kesihatan Sistem",
        'BTN_SA_REFRESH': "Muat Semula Konfigurasi",

        'BTN_SA_ADD_ADMIN': "Tambah Admin",
        'BTN_SA_DEL_ADMIN': "Padam Admin",
        'BTN_SA_LIST_ADMIN': "Senarai Admin",
        'BTN_SA_EXIT': "Keluar SuperAdmin",
        
        'PROMPT_SA_ADD': "Sila balas dengan *ID Telegram* untuk ditambah:",
        'PROMPT_SA_DEL': "Sila balas dengan *ID Telegram* untuk dipadam:",
        'MSG_SA_ADDED': "✅ Admin berjaya ditambah!",
        'MSG_SA_DELETED': "✅ Admin berjaya dipadam!",
        'ERR_SA_INVALID_ID': "⚠️ Format ID tidak sah.",
        
        'ERR_SA_ALREADY_ADMIN': "⚠️ Pengguna ini sudah menjadi Admin.",
        'MSG_SA_PROMOTED': "🎉 Tahniah! Anda telah dilantik sebagai Admin.",
        
        'BTN_CONFIRM_YES': "Sahkan Hantar",
        'BTN_CONFIRM_NO': "Batal",
        
        'ADMIN_BROADCAST_PROMPT': "Masukkan mesej untuk hebahan kepada semua:",
        'ADMIN_BROADCAST_CONFIRM': "Pratonton:\n\n{msg}\n\n*Hantar kepada {count} pengguna?*",
        'ADMIN_BROADCAST_START': "Sedang menghantar...",
        'ADMIN_BROADCAST_DONE': "*Hebahan Selesai* 📢\n\n✅ Berjaya: {success}\n❌ Gagal: {failed}",
        
        # Programs (Same for both languages usually, or translate if needed)
        'BTN_PROG_IT': "DIPLOMA TEKNOLOGI MAKLUMAT",
        'BTN_PROG_MM': "DIPLOMA MULTIMEDIA DENGAN DAKWAH",
        'BTN_PROG_CS': "IJAZAH SARJANA MUDA SAINS KOMPUTER",
        'BTN_PROG_MD': "IJAZAH SARJANA MUDA MULTIMEDIA KREATIF",
        'BTN_PROG_AG': "IJAZAH SARJANA MUDA PERTANIAN",
        'BTN_PROG_LA': "IJAZAH SARJANA MUDA SENI BINA LANDSKAP",
    }
}

DEFAULT_LANG = 'EN'

def get(key, lang='EN'):
    """Get string by key and language, fall back to Default if missing"""
    return STRINGS.get(lang, STRINGS[DEFAULT_LANG]).get(key, STRINGS[DEFAULT_LANG].get(key, key))

def get_all(key):
    """Get a list of values for a key across all languages (for Filters)"""
    return [STRINGS[l].get(key) for l in STRINGS if STRINGS[l].get(key)]
