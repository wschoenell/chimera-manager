#!/usr/bin/env python

################################################################################

__author__ = 'Ribeiro, T.'

################################################################################

import sys
import os
import time
import datetime as dt

from chimera.core.cli import ChimeraCLI, action
from chimera.core.callback import callback
from chimera.util.output import blue, green, red

################################################################################

class Manager(ChimeraCLI):
    ############################################################################

    def __init__(self):
        ChimeraCLI.__init__(self, "chimera-manager",
                            "Manager controller", 0.0, port=9010)

        '''
        Check manager status and control some actions.
        '''

        self.addHelpGroup("RUN", "Start/Stop/Monitor")

    ############################################################################

    @action(help="Start manager", helpGroup="RUN", actionGroup="RUN")
    def start(self, options):

        return 0

    ############################################################################

    @action(help="Stop manager", helpGroup="RUN", actionGroup="RUN")
    def stop(self, options):

        return 0

    ############################################################################

    @action(help="Monitor manager", helpGroup="RUN", actionGroup="RUN")
    def monitor(self, options):

        return 0

    ############################################################################

################################################################################

def main():
    cli = Manager()
    cli.run(sys.argv)
    cli.wait()

################################################################################

if __name__ == '__main__':
    main()

################################################################################
