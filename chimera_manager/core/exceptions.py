
from chimera.core.exceptions import ChimeraException

class CheckAborted(ChimeraException):
    pass

class CheckExecutionException(ChimeraException):
    pass

class StatusUpdateException(ChimeraException):
    pass