# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from .loader import Loader
from .callback import CallBack
from .security import MXUS
from .langs import STRINGS, init as lang_init, switch as lang_switch, available as lang_available, current as lang_current
from . import loader
from . import utils