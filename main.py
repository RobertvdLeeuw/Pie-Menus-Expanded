import mousehook
import pieFunctions
from piemenu_backend import Window
from settings.pie_themes import tray_theme
from settingsMenu import SettingsManager
from systemTrayIcon import SystemTrayIcon

from collections import defaultdict
import os, time, shutil
from re import match as re_match
import sys
from threading import Thread

from ctypes import windll
import keyboard
from PySide2 import QtGui, QtWidgets, QtCore
# import pywin32
import win32gui as w32gui


# allow only single instance of this script to run
os.environ["PBR_VERSION"] = "4.0.2"  # this removes  tendo/pbr error after pyinstaller compiles it.
from tendo import singleton


if len(sys.argv) > 1:
    try:
        os.chdir(sys.argv[1])
        print("Changed working directory.")
    except OSError as e:
        print(e)

_ = singleton.SingleInstance()


class WindowMgr:
    """Encapsulates some calls to the winapi for window management"""

    def __init__(self):
        self._handle = None

    def findWindow(self, classname, windowname=None):
        self._handle = w32gui.FindWindow(classname, windowname)

    def _windowEnumCallback(self, hwnd, wildcard):
        """Pass to w32gui.EnumWindows() to check all the opened windows"""
        if re_match(wildcard, str(w32gui.GetWindowText(hwnd))) is not None:
            self._handle = hwnd

    def findWindowWildcard(self, wildcard):
        self._handle = None
        w32gui.EnumWindows(self._windowEnumCallback, wildcard)

    def setForeground(self):
        w32gui.SetForegroundWindow(self._handle)


class ActiveProfile:
    def __init__(self):
        self.activeWindow = None
        self.handle_foreground = None
        self.profile = None
        self.loadedHotkeys: list[str] = []
        self.loadedTriggerKeys: list[str] = []
        self.hotkeyPressed = None
        self.hotkeyFunction = None
        self.hotkeyParameters = None
        self.hotkeyForPieMenu = None
        self.hotkeyHandled = None
        self.triggerKey = None

        self.sameTKeyHKey = None

        self.keyHeld = False
        self.openPieMenu = None
        self.triggeredPieSlice = None
        self.hotkeyReleased = True

        self.isRMBup = False
        self.isLMBup = False
        self.isWheel = False

        # First default runs
        self.loadProfile(globalProfile=True)
        self.timerCheckHotkey = QtCore.QTimer()
        self.timerCheckHotkey.timeout.connect(self.isHotkeyEvent)
        self.timerCheckHotkey.start(25)

        self.mouseThread = Thread(target=mousehook.mouseHook)
        mousehook.mouseHandlers.append(self.regLowLevelMouseEvent)

        # Timers
        self.timerKeyHeld = QtCore.QTimer()
        self.timerKeyHeld.timeout.connect(self.checkHeldKeyReleased)
        self.timerKeyHeld.timeout.connect(self.isTKeyEvent)
        self.timerKeyHeld.timeout.connect(self.lowLevelMouseEvent)
        self.timerKeyHeld.timeout.connect(self.menuCancel)
        self.timer_checkKeyHeld = QtCore.QTimer()
        self.timer_checkKeyHeld.timeout.connect(self.checkKeyHeld)
        self.waitHKey = QtCore.QTimer()
        self.waitHKey.timeout.connect(self.waitHKeyrelease)
        self.hotkeyReleaseCounter = 0

    def changeDetected(self, activeWindow, handle_foreground):
        """
        Checks if the new active window has a profile attached to it. If so, it loads that profile.
        Otherwise, the global profile is loaded.

        Args:
            activeWindow (QMainWindow): The new active window.
            handle_foreground (int): The id of the foreground window.

        """

        self.handle_foreground = handle_foreground
        if activeWindow not in settingsManager.registeredApps:
            self.loadProfile(globalProfile=True)
            return

        self.activeWindow = activeWindow
        self.loadProfile()
        self.appendWithGeneralHotKeys()
        self.loadHotkeys()

    def loadHotkeys(self):
        """
        Deletes old hotkeys. Afterwards, loops over each pie menu corresponding to the active window,
        and adds their hotkeys if the menu is enabled.
        """

        self.flushHotkeys()

        for option in ("piemenus", "hotkeys"):
            if option not in self.profile:
                continue

            for item in self.profile[option]:
                if not item.get("enabled", True):
                    continue

                args = (item["hotkey"], item) if option == "piemenus" else \
                    (item['hotkey'], None, item['function'], item.get("params"))

                keyboard.add_hotkey(item["hotkey"],
                                    self.registerHotkeyEvent,
                                    suppress=True,
                                    args=args)
                self.loadedHotkeys.append(item["hotkey"])

    def loadTriggerKeys(self):
        # enable the following logic if hotkeys and triggerkeys are allowed to be same/clash.
        # for key in self.loadedHotkeys:
        #     if key != self.A_ThisHotkey:
        #         keyboard.remove_hotkey(key)

        for slices in self.openPieMenu["slices"]:
            if slices.get("triggerkey", "None") == "None":
                return

            if slices.get("triggerkey") == self.hotkeyPressed:
                self.sameTKeyHKey = slices
                continue

            keyboard.add_hotkey(slices["triggerkey"], self.registerTKeyEvent, suppress=True,
                                args=[slices["triggerkey"], slices])
            self.loadedTriggerKeys.append(slices["triggerkey"])

    def loadFinalTriggerKey(self):
        if self.sameTKeyHKey is None:
            return

        keyboard.add_hotkey(self.sameTKeyHKey["triggerkey"], self.registerTKeyEvent, suppress=True,
                            args=[self.sameTKeyHKey["triggerkey"], self.sameTKeyHKey])
        self.loadedTriggerKeys.append(self.sameTKeyHKey["triggerkey"])

    def registerTKeyEvent(self, triggerKey, pie):
        self.triggerKey = triggerKey
        self.triggeredPieSlice = pie

    def isTKeyEvent(self):
        if self.triggerKey is None:
            return
        self.launchByTriggerKey()

    def unloadTriggerKeys(self):
        self.loadedTriggerKeys.clear()
        self.loadHotkeys()

    def launchByTriggerKey(self):
        window.launchByTrigger(int(self.triggeredPieSlice["SliceNumber"]) - 1)
        self.resetAttributes()

    def flushHotkeys(self):
        if self.loadedHotkeys:
            keyboard.unhook_all_hotkeys()

        self.loadedHotkeys.clear()

    def loadProfile(self, globalProfile=False):
        handle = "Default" if globalProfile else self.activeWindow

        self.profile = [p for p in settingsManager.appProfiles if
                        p["ahkHandle"] == handle][0]

        if globalProfile:
            self.activeWindow = None
            self.loadHotkeys()

    def registerActiveProfileHotkeys(self) -> list[str]:
        hotkeys = []

        def getProfileHotkeys(obj):
            for item in obj:
                if not item.get("enabled", True):
                    continue

                hotkeys.append(item["hotkey"])

        if self.profile["label"] == "Default Profile":
            return hotkeys

        for option in ["piemenus", "hotkeys"]:
            if option in self.profile:
                getProfileHotkeys(self.profile[option])
        return hotkeys

    def appendWithGeneralHotKeys(self):
        """
        Adding global (or general) hotkeys and piemenus to the profile ones to load in one go,
        unless the loaded profile contains a hotkey overriding the general entry.
        """

        globalProfile = [p for p in settingsManager.appProfiles if
                         p["ahkHandle"] == "Default"][0]
        currentHotkeys = self.registerActiveProfileHotkeys()

        for option in ("piemenus", "hotkeys"):
            for item in globalProfile.get(option, []):
                if not item.get("general", True) or not item.get("enabled", True):
                    continue

                if item["hotkey"] in currentHotkeys:
                    continue

                if option not in self.profile:
                    self.profile[option] = []

                self.profile[option].append(item)

    def runHotkey(self):
        if not self.hotkeyFunction or self.hotkeyFunction.lower() == "none":
            return

        if self.hotkeyFunction not in pieFunctions.FUNCTIONS:
            print(f"Invalid button self.A_ThisHotkeyFunction: {self.hotkeyFunction}")
            return

        func = pieFunctions.FUNCTIONS[self.hotkeyFunction]

        if self.hotkeyParameters:
            func(self.hotkeyParameters)
        else:
            func()

        self.hotkeyPressed = None

    def registerHotkeyEvent(self, hotkey: str, pieMenu=None, function=None, params=None):
        """
        Registers a hotkey when pressed. Bound to keyboard.add_hotkey().
        Requires either a pieMenu, or a function and its potential parameters - in case of a standalone hotkey.
        """

        self.hotkeyPressed = hotkey
        self.hotkeyForPieMenu = bool(pieMenu)

        if self.hotkeyForPieMenu:
            self.openPieMenu = pieMenu
            return

        self.hotkeyFunction = function
        self.hotkeyParameters = params
        self.hotkeyHandled = False

    def isHotkeyEvent(self):
        """Checks whether any hotkey has been pressed. Runs every 25ms."""

        if self.hotkeyPressed is None:
            return

        if not self.hotkeyForPieMenu:  # Adaptation to the system as to not 'hold' standalone hotkeys.
            if self.hotkeyHandled:
                return
            self.hotkeyHandled = True
        self.hotkeyEvent()

    def hotkeyEvent(self):
        if self.hotkeyForPieMenu:
            if not window.isMenuOpen() and self.hotkeyReleased:
                self.launchPieMenu()
        else:
            self.runHotkey()

    def launchPieMenu(self):
        cursorpos = QtGui.QCursor.pos()

        if IS_MULTI_MONITOR_SETUP:
            detectMonitorChange(cursorpos, self.handle_foreground)

        window.showMenu(self.openPieMenu, cursorpos, settingsManager.globalSettings)
        self.loadTriggerKeys()

        self.timerKeyHeld.start(25)

        self.mouseThread = Thread(target=mousehook.mouseHook)
        self.mouseThread.start()

        # 194 is a special value, do not change unless you what you are doing
        self.timer_checkKeyHeld.start(194)

    def checkKeyHeld(self):
        if not window.isMenuOpen():
            # If right click is pressed immediately after opening pie menus, currentMousePos becomes None,
            # and this causes errors, so better check if pie menu is open or not.
            return

        mouseInCircle = window.menu.checkMouseInCircle()

        self.keyHeld = keyboard.is_pressed(self.hotkeyPressed) or not mouseInCircle

        if not self.keyHeld:
            self.loadFinalTriggerKey()
        self.timer_checkKeyHeld.stop()

    def checkHeldKeyReleased(self):
        if self.keyHeld and keyboard.is_pressed(self.hotkeyPressed):
            pass
        elif not self.keyHeld:
            if not window.isMenuOpen():
                self.resetAttributes()
        else:
            window.releasedHeldKey()
            self.resetAttributes()

    def lowLevelMouseEvent(self):
        if self.isLMBup:
            window.releasedHeldKey()
            self.resetAttributes()

        if self.isWheel:
            window.llWheelEvent(self.isWheel)
            self.isWheel = False

    def menuCancel(self):
        if keyboard.is_pressed('esc') or self.isRMBup:
            window.killMenu()
            self.resetAttributes()

    def regLowLevelMouseEvent(self, event) -> int:
        # register low level mouse event
        event_type = event.event_type

        if event_type in ('RButton Down', 'LButton Down'):
            return -1  # Block rmb and lmb down

        if event_type == 'RButton Up':
            self.isRMBup = True
            return -1

        if event_type == 'LButton Up' and not self.keyHeld:
            self.isLMBup = True
            return -1
        if event_type == 'LButton Up' and self.keyHeld:
            return -1

        if event_type == 'wheel':
            # scan code === lParam[1]
            self.isWheel = event

    def waitHKeyrelease(self):
        if self.hotkeyPressed is None:
            self.hotkeyForPieMenu = None
            self.hotkeyFunction = None
            self.hotkeyParameters = None
            self.hotkeyReleased = True
            self.waitHKey.stop()
            return

        self.hotkeyReleaseCounter += int(self.hotkeyReleaseCounter < 100)

        if (not keyboard.is_pressed(self.hotkeyPressed)) and self.hotkeyReleaseCounter >= 6:
            self.hotkeyForPieMenu = None
            self.hotkeyFunction = None
            self.hotkeyParameters = None
            self.hotkeyPressed = None
            self.hotkeyReleased = True
            self.waitHKey.stop()

    def resetAttributes(self):
        # stop timers
        self.timerKeyHeld.stop()

        # stop thread and join in main thread
        if self.mouseThread.is_alive():
            windll.user32.PostThreadMessageW(self.mouseThread.ident, WM_QUIT, 0, 0)
            self.mouseThread.join()

        # reset attributes
        self.isLMBup = False
        self.isRMBup = False
        self.unloadTriggerKeys()
        self.keyHeld = False
        self.openPieMenu = None
        self.hotkeyForPieMenu = None
        self.hotkeyFunction = None
        self.hotkeyParameters = None
        self.hotkeyHandled = None
        self.triggerKey = None
        self.sameTKeyHKey = None
        self.hotkeyReleased = False
        self.hotkeyReleaseCounter = 0
        self.waitHKey.start(25)


# -------------------------------Class End--------------------------------------

def detectWindowChange():
    previousActiveWindow = activeProfile.activeWindow
    try:
        handle_foreground = w32gui.GetForegroundWindow()
    # except pywin32.error as e:
    except Exception as e:
        print(e)

        sys.exit(-1)

    activeWindow = w32gui.GetClassName(handle_foreground)

    if previousActiveWindow == activeWindow:
        return

    activeProfile.changeDetected(activeWindow, handle_foreground)


def detectMonitorChange(cursorpos, handle_foreground):
    if mon_manager.move_to_active_screen(cursorpos, window) == "no_change":
        return
    window.showFullScreen()
    w32gui.SetForegroundWindow(handle_foreground)


settingsManager = SettingsManager()

# ------- Global variables ----------------
DEBUGMODE = False
WM_QUIT = 0x0012
IS_MULTI_MONITOR_SETUP = False
APP_SUSPENDED = False
WINCHANGE_latency = 100  # ms

if settingsManager.globalSettings['winChangeLatency'] and \
        25 <= settingsManager.globalSettings['winChangeLatency'] <= 200:
    WINCHANGE_latency = settingsManager.globalSettings['winChangeLatency']

# ------- /END Global variables ----------------

MODES = defaultdict(lambda: 'DEBUG')
MODES['QtCore.QtInfoMsg'] = 'INFO'
MODES['QtCore.QtWarningMsg'] = 'WARNING'
MODES['QtCore.QtCriticalMsg'] = 'CRITICAL'
MODES['QtCore.QtFatalMsg'] = 'FATAL'


def qtMessageHandler(mode, context, message):
    """
    Handles warning messages, sometimes, it might eat up
    some warning which won't be printed, so it is good to disable this
    when developing, debugging and testing.
    """

    if "QWindowsWindow::setGeometry: Unable to set geometry" in message:
        # This is ignore the warning message when changing the
        # screen on which app is shown on multi monitor systems.
        # Qt automatically decides best size, that's I have ignored it here.

        return

    # print(f'qt_message_handler: line: {context.line}, func: {context.function}(), file: {context.file}')
    print(f'{MODES[mode]}: {message}')


def suspendApp():
    global APP_SUSPENDED

    if window.isMenuOpen():
        # toast msg close open pie menus
        return

    activeProfile.flushHotkeys()
    keyboard.unhook_all()

    # stop all timers and threads in app
    timerWinChange.stop()
    activeProfile.timerCheckHotkey.stop()

    APP_SUSPENDED = True


def resumeApp():
    global APP_SUSPENDED

    # resume all timers and threads in app
    timerWinChange.start(WINCHANGE_latency)
    activeProfile.loadProfile(globalProfile=True)
    activeProfile.timerCheckHotkey.start(25)

    APP_SUSPENDED = False
    # do not call construction of active_profile or instantiate it again, let's keep it clean.


def getAllReferences(with_funcs=False):  # TODO: This is really fucking smart. Remember this for future projects.
    only_vars = {"DEBUGMODE": DEBUGMODE,
                 "WM_QUIT": WM_QUIT,
                 "IS_MULTI_MONITOR_SETUP": IS_MULTI_MONITOR_SETUP,
                 "APP_SUSPENDED": APP_SUSPENDED,
                 "WINCHANGE_latency": WINCHANGE_latency,
                 "APP": app}

    if not with_funcs:
        return only_vars

    with_funcs = {}
    with_funcs.update(only_vars)
    with_funcs.update({"suspend_app": suspendApp,
                       "resume_app": resumeApp})

    return with_funcs


# ------------------------------------ MAIN ---------------------------------

# High DPI stuff
# these should be in this sequence and before creating QApplication
# https://stackoverflow.com/questions/41331201/pyqt-5-and-4k-screen
# https://stackoverflow.com/questions/39247342/pyqt-gui-size-on-high-resolution-screens
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "2"
if settingsManager.globalSettings['ScaleFactor']:
    # following line scales the entire app by the given factor.
    os.environ["QT_SCALE_FACTOR"] = str(settingsManager.globalSettings['ScaleFactor'])

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)  # enable highdpi scaling
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)  # use highdpi icons

app = QtWidgets.QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

trayIcon = QtGui.QIcon(os.path.join(os.path.dirname(__file__),
                                    "resources/icons/tray_icon.png"))

# tray icon attribution : # icon type 2: <div>Icons made by <a href="https://www.flaticon.com/authors/ultimatearm"
# title="ultimatearm">ultimatearm</a> from <a href="https://www.flaticon.com/"
# title="Flaticon">www.flaticon.com</a></div>
# tray icon link : https://www.flaticon.com/free-icon/pie_1411020?term=pies&related_id=1411020

trayWidgetQT = QtWidgets.QWidget()
trayWidget = SystemTrayIcon(QtGui.QIcon(trayIcon), getAllReferences, settingsManager, trayWidgetQT)
trayWidgetQT.setStyleSheet(tray_theme.QMenu)
trayWidget.show()

window = Window()
window.showFullScreen()

# Qt warning messages handler installing
QtCore.qInstallMessageHandler(qtMessageHandler)

# WARNING : ActiveProfile and Monitor_Manager should only have once instance.
# I mean, think why do you need two instance, no need, it will cause chaos.
activeProfile = ActiveProfile()

if len(app.screens()) > 1:
    from monitor_manager import Monitor_Manager


    IS_MULTI_MONITOR_SETUP = True
    mon_manager = Monitor_Manager(app.screens(), app.primaryScreen())

# Timers
timerWinChange = QtCore.QTimer()
timerWinChange.timeout.connect(detectWindowChange)

# Timer starts
timerWinChange.start(WINCHANGE_latency)

sys.exit(app.exec_())
