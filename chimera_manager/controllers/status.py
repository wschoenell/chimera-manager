from chimera.util.enum import Enum

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