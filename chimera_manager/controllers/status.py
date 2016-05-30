from chimera.util.enum import Enum

InstrumentOperationFlag = Enum("UNSET",      # No info about instrument operation condition
                               "READY",      # Instrument can open and operate normally
                               "OPERATING",  # Instrument was instanciated by manager and should be operating
                               "CLOSE",      # Instrument should be closed and must not be operated
                               "LOCK",       # Instrument was locked. It will require a key to unlock
                                             # (known to the one that locked it).
                               "ERROR"       # Instrument in error. Operation condition is uncertain
                                )

OperationStatus = Enum("DAYTIME_IDLE",
                       "NIGHTTIME_IDLE",
                       "DAYTIME_OPERATING",
                       "NIGHTTIME_OPERATING",
                       "WEATHER_CLOSED",
                       "NETWORK_CLOSED",
                       "TECHNICAL_CLOSED",
                       "UNSPECIFIED_CLOSED")

FlagStatus = Enum("UNKNOWN",
                  "UNSET",
                  "OK",
                  "WARNING",
                  "ALERT",
                  "ABORTED",
                  "ERROR")

ResponseStatus = Enum("OK",
                      "ERROR",
                      "ABORTED")