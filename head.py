import core
from frontend import Window
from settings.pie_themes import tray_theme
from settingsMenu import SettingsManager
from systemTrayIcon import SystemTrayIcon

from functools import partial
import os
import sys

from PySide2 import QtGui, QtWidgets, QtCore


# allow only single instance of this script to run
os.environ["PBR_VERSION"] = "4.0.2"  # this removes  tendo/pbr error after pyinstaller compiles it.
from tendo import singleton


def GetAllReferences(app: QtWidgets.QApplication, with_funcs=False):  # TODO: This is really fucking smart. Remember
    # this for
    # future projects.
    only_vars = {"DEBUGMODE": core.DEBUGMODE,
                 "WM_QUIT": core.WM_QUIT,
                 "IS_MULTI_MONITOR_SETUP": core.IS_MULTI_MONITOR_SETUP,
                 "APP_SUSPENDED": core.APP_SUSPENDED,
                 "WINCHANGE_latency": core.WINCHANGE_latency,
                 "APP": app}

    if not with_funcs:
        return only_vars

    with_funcs = {}
    with_funcs.update(only_vars)
    with_funcs.update({"suspend_app": core.suspendApp,
                       "resume_app": core.resumeApp})

    return with_funcs


def CreateTrayWidget(app, settingsManager):
    trayIcon = QtGui.QIcon(os.path.join(os.path.dirname(__file__),
                                        "resources/icons/tray_icon.png"))

    trayWidgetQT = QtWidgets.QWidget()
    trayWidget = SystemTrayIcon(QtGui.QIcon(trayIcon), partial(GetAllReferences, app), settingsManager, trayWidgetQT)
    trayWidgetQT.setStyleSheet(tray_theme.QMenu)
    trayWidget.show()


def CreateMonitorManager():
    if len(app.screens()) == 1:
        return

    from monitor_manager import MonitorManager


    core.IS_MULTI_MONITOR_SETUP = True
    return MonitorManager(app.screens(), app.primaryScreen())


def SetHighDPISettings():
    # High DPI stuff
    # This should be in this sequence and before creating QApplication
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "2"
    if settingsManager.globalSettings['ScaleFactor']:
        # following line scales the entire app by the given factor.
        os.environ["QT_SCALE_FACTOR"] = str(settingsManager.globalSettings['ScaleFactor'])

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)  # enable highdpi scaling
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)  # use highdpi icons


if __name__ == "__main__":
    _ = singleton.SingleInstance()

    if len(sys.argv) > 1:
        try:
            os.chdir(sys.argv[1])
            print("Changed working directory.")
        except OSError as e:
            print(e)

    settingsManager = SettingsManager()
    core.UpdateGlobalVariables(settingsManager)

    SetHighDPISettings()

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    CreateTrayWidget(app, settingsManager)

    window = Window()
    window.showFullScreen()

    activeProfile = core.ActiveProfile(settingsManager, window, CreateMonitorManager())

    timerWinChange = QtCore.QTimer()
    timerWinChange.timeout.connect(partial(core.detectWindowChange, activeProfile))

    timerWinChange.start(core.WINCHANGE_latency)

    sys.exit(app.exec_())
