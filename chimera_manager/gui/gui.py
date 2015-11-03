
import os

from PyQt4 import QtCore, QtGui, uic
# from chimera.core.chimeraobject import ChimeraObject

class ManagerGUI(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)

        self.uipath = os.path.join(os.path.dirname(__file__),
                                   'main_manager.ui')

        self.ui = uic.loadUi(self.uipath,self)
