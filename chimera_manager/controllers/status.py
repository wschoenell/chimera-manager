from chimera.util.enum import Enum

OperationStatus = Enum("DAYTIME_IDLE",
                       "NIGHTTIME_IDLE",
                       "OPERATING",
                       "WEATHER_CLOSED",
                       "NETWORK_CLOSED",
                       "TECHNICAL_CLOSED",
                       "CLOSED")
