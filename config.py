# This file holds pinylib's configuration.
# Use a prefix, if you plan on adding your own.
# Tinychat account.
ACCOUNT = ''
# Password for account
PASSWORD = ''
# The swf version that tinychat is currently using.
SWF_VERSION = '0677'
# Log chat messages and events.
CHAT_LOGGING = True
# Show additional info/errors in console.
DEBUG_MODE = False
# Log debug info to file.
DEBUG_TO_FILE = False
# Logging level for the debug file.
DEBUG_LEVEL = 30
# Use colors for the console.
CONSOLE_COLORS = True
# Enable auto job (recommended)
ENABLE_AUTO_JOB = True
# Time format.
USE_24HOUR = True
# Reset the run time after a reconnect.
RESET_INIT_TIME = False
# Reconnect delay in seconds.
RECONNECT_DELAY = 10
# Auto job interval in seconds.
AUTO_JOB_INTERVAL = 360
# The name of pinylib's debug log file.
DEBUG_FILE_NAME = 'pinylib_debug.log'
# The path to the config folder.
CONFIG_PATH = 'rooms/'

# This section holds the bot's configuration.

# The prefix used for bot commands.
B_PREFIX = '!'
# Bot controller key.
B_KEY = '48hd99i'
# Bot super key.
B_SUPER_KEY = 'v783kdfml9w2'
B_MAX_MATCH_BANS = 1
# Public commands enabled.
B_PUBLIC_CMD = False
# Greet user when joining.
B_GREET = False
# Allow newuser to join the room.
B_ALLOW_NEWUSERS = True
# Allow broadcasting.
B_ALLOW_BROADCASTS = True
# Allow guests to enter the room.
B_ALLOW_GUESTS = True
# Allow lurkers to enter the room.
B_ALLOW_LURKERS = True
# Allow guest nicks.
B_ALLOW_GUESTS_NICKS = False
# Forgive auto bans.
B_FORGIVE_AUTO_BANS = True
# The file name of nick bans.
B_NICK_BANS_FILE_NAME = 'nick_bans.txt'
# A list of all the nick bans.
B_NICK_BANS = []
# The file name of account bans.
B_ACCOUNT_BANS_FILE_NAME = 'account_bans.txt'
# A list of account bans.
B_ACCOUNT_BANS = []
# The file name of string(words) bans.
B_STRING_BANS_FILE_NAME = 'string_bans.txt'
# A list of string bans.
B_STRING_BANS = []
# The name of the bot's debug file.
B_DEBUG_FILE_NAME = 'tinybot_debug.log'
