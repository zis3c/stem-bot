# User Messages
WELCOME_MSG = (
    "*Hi {name}!*\n\n"
    "I am the **Eligible STEM Bot**.\n"
    "I can verify your membership status instantly.\n\n"
    "👇 *Use the menu below to begin.*"
)

HELP_MSG = (
    "**About This Bot**\n\n"
    "This service checks the STEM USAS membership database.\n"
    "It connects securely to the official records.\n\n"
    "Dev: @zis3c"
)

# Prompts
PROMPT_MATRIC = "Step 1/2\n\nPlease type your **Matric Number**:\n(Example: `I24107504`)"
PROMPT_IC = "Matric: `{matric}`\n\nStep 2/2\nNow enter the **Last 4 Digits** of your IC:"
PROMPT_LOADING = "**Verifying...**"

VERIFICATION_SUCCESS = (
    "*MEMBERSHIP VERIFIED*\n\n"
    "*Name*: *{name}*\n"
    "*Matric*: *{matric}*\n"
    "*Program*: *{program}*\n\n"
    "**Status: ACTIVE**"
)

# Errors
ERR_INVALID_MATRIC = "**Invalid Matric Format!**\nPlease try again (e.g. `I24107504`)"
ERR_INVALID_IC = "**Invalid IC!**\nPlease enter exactly 4 digits."
ERR_DB_CONNECTION = "System Error: Database unavailable."
ERR_NOT_FOUND = "**Not Found**\nMatric Number not in records."
ERR_CANCEL = "Operation Cancelled."
ERR_ACCESS_DENIED = "**Access Denied**\nYou are not an admin."

# Admin Strings
ADMIN_DASHBOARD = "**Admin Dashboard**\nSelect an action:"
ADMIN_STATS = "**Database Stats**\n\nTotal Members: **{total}**"
ADMIN_ADD_MATRIC = "**Add Member**\nEnter Matric Number:"
ADMIN_ADD_NAME = "Enter **Full Name**:"
ADMIN_ADD_IC = "Enter **Full IC Number** (e.g. 020512081234):"
ADMIN_ADD_PROG = "Enter **Program Code** (e.g. CS230):"
ADMIN_ADD_SUCCESS = "**Success!**\nAdded {name} ({matric})"
ADMIN_DEL_START = "**Delete Member**\nEnter Matric Number to delete:"
ADMIN_DEL_SUCCESS = "**Deleted**\nRow {row} removed."
ADMIN_DEL_NOT_FOUND = "Matric not found."
ADMIN_SAVING = "Saving..."
ADMIN_SEARCHING = "Searching..."
ADMIN_EXIT = "Exiting Admin Mode."

# Buttons
BTN_CHECK = "Check Membership"
BTN_HELP = "Help / Info"
BTN_CANCEL = "Cancel"
BTN_TRY_AGAIN = "Try Again"

BTN_ADMIN_ADD = "Add Member"
BTN_ADMIN_DEL = "Delete Member"
BTN_ADMIN_STATS = "Stats"
BTN_ADMIN_EXIT = "Exit Admin"
