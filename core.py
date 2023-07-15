import mousehook
import pieFunctions

from ctypes import windll
import keyboard
from re import match as re_match
import sys
from threading import Thread
import win32gui as w32gui

from PySide2 import QtGui, QtWidgets, QtCore


DEBUGMODE = False
WM_QUIT = 0x0012
IS_MULTI_MONITOR_SETUP = False
APP_SUSPENDED = False
WINCHANGE_latency = 100  # ms


def UpdateGlobalVariables(settingsManager):
    global WINCHANGE_latency

    if 25 <= settingsManager.globalSettings.get('winChangeLatency', 1000) <= 200:
        WINCHANGE_latency = settingsManager.globalSettings['winChangeLatency']


MODES = {'QtCore.QtInfoMsg': 'INFO',
         'QtCore.QtWarningMsg': 'WARNING',
         'QtCore.QtCriticalMsg': 'CRITICAL',
         'QtCore.QtFatalMsg': 'FATAL'}


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
    print(f"{MODES.get(mode, 'DEBUG')}: {message}")


def suspendApp(window, activeProfile, timerWinChange):
    global APP_SUSPENDED

    if window.isMenuOpen():
        # toast msg close open pie menus
        return

    activeProfile.hotkeyManager.flushHotkeys()
    keyboard.unhook_all()

    # stop all timers and threads in app
    timerWinChange.stop()
    activeProfile.hotkeyManager.timerCheckHotkey.stop()

    APP_SUSPENDED = True


def resumeApp(activeProfile, timerWinChange):
    global APP_SUSPENDED

    # resume all timers and threads in app
    timerWinChange.start(WINCHANGE_latency)
    activeProfile.loadProfile(globalProfile=True)
    activeProfile.hotkeyManager.timerCheckHotkey.start(25)

    APP_SUSPENDED = False
    # do not call construction of active_profile or instantiate it again, let's keep it clean.


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


class TriggerKeyManager:
    def __init__(self, activeProfile):
        self.loadedTriggerKeys: list[str] = []
        self.triggerKey = None
        self.sameTKeyHKey = None
        self.triggeredPieSlice = None

        self.activeProfile = activeProfile

        activeProfile.timerKeyHeld.timeout.connect(self.isTKeyEvent)

    def loadTriggerKeys(self):
        # enable the following logic if hotkeys and triggerkeys are allowed to be same/clash.
        # for key in self.loadedHotkeys:
        #     if key != self.A_ThisHotkey:
        #         keyboard.remove_hotkey(key)

        for slices in self.activeProfile.displayManager.openPieMenu["slices"]:
            if slices.get("triggerkey", "None") == "None":
                return

            if slices.get("triggerkey") == self.activeProfile.hotkeyManager.hotkeyPressed:
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
        self.activeProfile.hotkeyManager.loadHotkeys()

    def launchByTriggerKey(self):
        self.activeProfile.window.launchByTrigger(int(self.triggeredPieSlice["SliceNumber"]) - 1)
        self.activeProfile.resetAttributes()

    def resetAttributes(self):
        self.unloadTriggerKeys()
        self.triggerKey = None
        self.sameTKeyHKey = None


class HotkeyManager:
    def __init__(self, activeProfile):
        self.activeProfile = activeProfile

        self.loadedHotkeys: list[str] = []

        self.hotkeyPressed = None
        self.hotkeyHandled = None

        self.hotkeyReleased = True
        activeProfile.timerKeyHeld.timeout.connect(self.checkHeldKeyReleased)

        self.hotkeyFunction = None
        self.hotkeyParameters = None
        self.hotkeyForPieMenu = None

        self.timerCheckHotkey = QtCore.QTimer()
        self.timerCheckHotkey.timeout.connect(self.isHotkeyEvent)
        self.timerCheckHotkey.start(25)

        self.keyHeld = False
        self.timer_checkKeyHeld = QtCore.QTimer()
        self.timer_checkKeyHeld.timeout.connect(self.checkKeyHeld)

        self.waitHKey = QtCore.QTimer()
        self.waitHKey.timeout.connect(self.waitHKeyrelease)
        self.hotkeyReleaseCounter = 0

    def loadHotkeys(self):
        """
        Deletes old hotkeys. Afterwards, loops over each pie menu corresponding to the active window,
        and adds their hotkeys if the menu is enabled.
        """

        self.flushHotkeys()

        for option in ("piemenus", "hotkeys"):
            if option not in self.activeProfile.profile:
                continue

            for item in self.activeProfile.profile[option]:
                if not item.get("enabled", True):
                    continue

                args = (item["hotkey"], item) if option == "piemenus" else \
                    (item['hotkey'], None, item['function'], item.get("params"))

                keyboard.add_hotkey(item["hotkey"],
                                    self.registerHotkeyEvent,
                                    suppress=True,
                                    args=args)
                self.loadedHotkeys.append(item["hotkey"])

    def flushHotkeys(self):
        if self.loadedHotkeys:
            keyboard.unhook_all_hotkeys()

        self.loadedHotkeys.clear()

    def registerActiveProfileHotkeys(self) -> list[str]:
        hotkeys = []

        def getProfileHotkeys(obj):
            for item in obj:
                if not item.get("enabled", True):
                    continue

                hotkeys.append(item["hotkey"])

        if self.activeProfile.profile["label"] == "Default Profile":
            return hotkeys

        for option in ["piemenus", "hotkeys"]:
            if option in self.activeProfile.profile:
                getProfileHotkeys(self.activeProfile.profile[option])
        return hotkeys

    def runHotkey(self):
        if not self.hotkeyFunction or self.hotkeyFunction.lower() == "none":
            return

        if self.hotkeyFunction not in pieFunctions.FUNCTIONS:
            print(f"Invalid button self.A_ThisHotkeyFunction: {self.hotkeyFunction}")
            return

        func = pieFunctions.FUNCTIONS[self.hotkeyFunction]
        func(self.hotkeyParameters) if self.hotkeyParameters else func()

        self.hotkeyPressed = None

    def registerHotkeyEvent(self, hotkey: str, pieMenu=None, function=None, params=None):
        """
        Registers a hotkey when pressed. Bound to keyboard.add_hotkey().
        Requires either a pieMenu, or a function and its potential parameters - in case of a standalone hotkey.
        """

        self.hotkeyPressed = hotkey
        self.hotkeyForPieMenu = bool(pieMenu)

        if self.hotkeyForPieMenu:
            self.activeProfile.displayManager.openPieMenu = pieMenu
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
            if not self.activeProfile.window.isMenuOpen() and self.hotkeyReleased:
                self.activeProfile.displayManager.launchPieMenu()
        else:
            self.runHotkey()

    def checkKeyHeld(self):
        if not self.activeProfile.window.isMenuOpen():
            # If right click is pressed immediately after opening pie menus, currentMousePos becomes None,
            # and this causes errors, so better check if pie menu is open or not.
            return

        mouseInCircle = self.activeProfile.window.menu.checkMouseInCircle()

        self.keyHeld = keyboard.is_pressed(self.hotkeyPressed) or not mouseInCircle

        if not self.keyHeld:
            self.activeProfile.triggerKeyManager.loadFinalTriggerKey()
        self.timer_checkKeyHeld.stop()

    def checkHeldKeyReleased(self):
        if self.keyHeld and keyboard.is_pressed(self.hotkeyPressed):
            pass
        elif not self.keyHeld:
            if not self.activeProfile.window.isMenuOpen():
                self.activeProfile.resetAttributes()
        else:
            self.activeProfile.window.releasedHeldKey()
            self.activeProfile.resetAttributes()

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
        self.hotkeyForPieMenu = None
        self.hotkeyFunction = None
        self.hotkeyParameters = None

        self.hotkeyHandled = None
        self.keyHeld = False

        self.hotkeyReleased = False
        self.hotkeyReleaseCounter = 0
        self.waitHKey.start(25)


class InputManager:
    def __init__(self, activeProfile):
        self.activeProfile = activeProfile

        self.isRMBup = False
        self.isLMBup = False
        self.isWheel = False

        self.mouseThread = Thread(target=mousehook.mouseHook)
        mousehook.mouseHandlers.append(self.regLowLevelMouseEvent)

        activeProfile.timerKeyHeld.timeout.connect(self.lowLevelMouseEvent)

    def lowLevelMouseEvent(self):
        if self.isLMBup:
            self.activeProfile.window.releasedHeldKey()
            self.activeProfile.resetAttributes()

        if self.isWheel:
            self.activeProfile.window.llWheelEvent(self.isWheel)
            self.isWheel = False

    def regLowLevelMouseEvent(self, event) -> int:
        # register low level mouse event
        event_type = event.event_type

        if event_type in ('RButton Down', 'LButton Down'):
            return -1  # Block rmb and lmb down

        if event_type == 'RButton Up':
            self.isRMBup = True
            return -1

        if event_type == 'LButton Up' and not self.activeProfile.hotkeyManager.keyHeld:
            self.isLMBup = True
            return -1
        if event_type == 'LButton Up' and self.activeProfile.hotkeyManager.keyHeld:
            return -1

        if event_type == 'wheel':
            # scan code === lParam[1]
            self.isWheel = event

    def resetAttributes(self):
        # stop thread and join in main thread
        if self.mouseThread.is_alive():
            windll.user32.PostThreadMessageW(self.mouseThread.ident, WM_QUIT, 0, 0)
            self.mouseThread.join()

        self.isLMBup = False
        self.isRMBup = False


class DisplayManager:
    def __init__(self, activeProfile):
        self.activeProfile = activeProfile

        self.activeWindow = None
        self.handle_foreground = None

        self.openPieMenu = None

        self.profile = activeProfile.profile
        self.timerKeyHeld = activeProfile.timerKeyHeld
        self.timerKeyHeld.timeout.connect(self.menuCancel)

    def changeDetected(self, activeWindow, handle_foreground):
        """
        Checks if the new active window has a profile attached to it. If so, it loads that profile.
        Otherwise, the global profile is loaded.

        Args:
            activeWindow (QMainWindow): The new active self.activeProfile.window.
            handle_foreground (int): The id of the foreground self.activeProfile.window.

        """

        self.handle_foreground = handle_foreground
        if activeWindow not in self.activeProfile.settingsManager.registeredApps:
            self.activeProfile.loadProfile(globalProfile=True)
            return

        self.activeWindow = activeWindow
        self.activeProfile.loadProfile()
        self.activeProfile.appendProfileWithGeneralHotKeys()
        self.activeProfile.hotkeyManager.loadHotkeys()

    def launchPieMenu(self):
        cursorpos = QtGui.QCursor.pos()

        if IS_MULTI_MONITOR_SETUP:
            detectMonitorChange(cursorpos, self.handle_foreground, self.activeProfile.mon_manager,
                                self.activeProfile.window)

        self.activeProfile.window.showMenu(self.openPieMenu, cursorpos,
                                           self.activeProfile.settingsManager.globalSettings)
        self.activeProfile.triggerKeyManager.loadTriggerKeys()

        self.timerKeyHeld.start(25)

        self.activeProfile.inputManager.mouseThread = Thread(target=mousehook.mouseHook)
        self.activeProfile.inputManager.mouseThread.start()

        # 194 is a special value, do not change unless you what you are doing
        self.activeProfile.hotkeyManager.timer_checkKeyHeld.start(194)

    def menuCancel(self):
        if keyboard.is_pressed('esc') or self.activeProfile.inputManager.isRMBup:
            self.activeProfile.window.killMenu()
            self.resetAttributes()

    def resetAttributes(self):
        self.openPieMenu = None


class ActiveProfile:
    def __init__(self, settingsManager, window, mon_manager):
        self.timerKeyHeld = QtCore.QTimer()
        self.profile: dict | None = None

        self.settingsManager = settingsManager
        self.window = window
        self.mon_manager = mon_manager

        self.triggerKeyManager = TriggerKeyManager(self)
        self.hotkeyManager = HotkeyManager(self)
        self.inputManager = InputManager(self)
        self.displayManager = DisplayManager(self)

        self.loadProfile(globalProfile=True)

    def loadProfile(self, globalProfile=False):
        handle = "Default" if globalProfile else self.displayManager.activeWindow

        self.profile = [p for p in self.settingsManager.appProfiles if
                        p["ahkHandle"] == handle][0]

        if globalProfile:
            self.displayManager.activeWindow = None
            self.hotkeyManager.loadHotkeys()

    def appendProfileWithGeneralHotKeys(self):
        """
        Adding global (or general) hotkeys and piemenus to the profile ones to load in one go,
        unless the loaded profile contains a hotkey overriding the general entry.
        """

        globalProfile = [p for p in self.settingsManager.appProfiles if
                         p["ahkHandle"] == "Default"][0]
        currentHotkeys = self.hotkeyManager.registerActiveProfileHotkeys()

        for option in ("piemenus", "hotkeys"):
            for item in globalProfile.get(option, []):
                if not item.get("general", True) or not item.get("enabled", True):
                    continue

                if item["hotkey"] in currentHotkeys:
                    continue

                if option not in self.profile:
                    self.profile[option] = []

                self.profile[option].append(item)

    def resetAttributes(self):
        self.timerKeyHeld.stop()

        self.triggerKeyManager.resetAttributes()
        self.hotkeyManager.resetAttributes()
        self.inputManager.resetAttributes()
        self.displayManager.resetAttributes()


def detectWindowChange(activeProfile):
    previousActiveWindow = activeProfile.displayManager.activeWindow
    try:
        handle_foreground = w32gui.GetForegroundWindow()
    # except pywin32.error as e:
    except Exception as e:
        print(e)

        sys.exit(-1)

    activeWindow = w32gui.GetClassName(handle_foreground)

    if previousActiveWindow == activeWindow:
        return

    activeProfile.displayManager.changeDetected(activeWindow, handle_foreground)


def detectMonitorChange(cursorpos, handle_foreground, mon_manager, window):
    if mon_manager.move_to_active_screen(cursorpos, window) == "no_change":
        return
    window.showFullScreen()
    w32gui.SetForegroundWindow(handle_foreground)
