
import os

from chimera.core.constants import SYSTEM_CONFIG_DIRECTORY

DEFAULT_PROGRAM_DATABASE = os.path.join(
    SYSTEM_CONFIG_DIRECTORY, 'manager_checklist.db')

DEFAULT_STATUS_DATABASE = os.path.join(
    SYSTEM_CONFIG_DIRECTORY, 'manager_status.db')