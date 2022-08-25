from collections import defaultdict
import datetime
import json
import os
from re import match as re_match

import psutil
from PySide2.QtGui import QCursor
import win32gui as w32gui
import win32process as w32pcs

import mousehook
from fastIO import *
from piemenu_backend import *
from systemTrayIcon import SystemTrayIcon


# allow only single instance to run
os.environ["PBR_VERSION"] = "4.0.2"  # this remove tendo/pbr error after pyinstaller compiles it.
from tendo import singleton


me = singleton.SingleInstance()  # will sys.exit(-1) if other instance is running


class WindowMgr:
    """Encapsulates some calls to the winapi for window management"""

    def __init__(self):
        """Constructor"""
        self._handle = None

    def find_window(self, class_name, window_name=None):
        """find a window by its class_name"""
        self._handle = w32gui.FindWindow(class_name, window_name)

    def _window_enum_callback(self, hwnd, wildcard):
        """Pass to w32gui.EnumWindows() to check all the opened windows"""
        if re_match(wildcard, str(w32gui.GetWindowText(hwnd))) is not None:
            self._handle = hwnd

    def find_window_wildcard(self, wildcard):
        """find a window whose title matches the wildcard regex"""
        self._handle = None
        w32gui.EnumWindows(self._window_enum_callback, wildcard)

    def set_foreground(self):
        """put the window in the foreground"""
        w32gui.SetForegroundWindow(self._handle)


# active window example calls
# w = WindowMgr()
# w.find_window_wildcard(".*Hello.*")
# w.set_foreground()

# Important Note: As of now Trigger keys cannot be same as hotkeys in a single profile


class ActiveProfile:
    def __init__(self) -> None:
        # Attributes
        self.activeWindow = None
        self.activeTitle = None
        self.handle_foreground = None
        self.profile = None
        self.loadedHotkeys = []
        self.loadedTriggerKeys = []
        self.A_ThisHotkey = None
        self.A_ThisHotkeyFunction = None
        self.A_ThisHotkeyParameters = None
        self.A_ThisHotkeyIsForPieMenu = None
        self.A_ThisHotkeyHandled = None
        self.A_TriggerKey = None

        self.sameTKeyHKey = None

        self.keyHeld = False
        self.isMenuOpen = False
        self.openPieMenu = None
        self.menu_open_time = None
        self.init_cursorpos = None
        self.triggeredPieSlice = None
        self.HKeyLetgo = True

        self.isRMBup = False
        self.isRMBdown = False
        self.isLMBup = False
        self.isLMBdown = False
        self.isMMBup = False
        self.isMMBdown = False
        self.isWheel = False

        # First default runs
        self.loadGlobal()
        self.timerCheckHotkey = QTimer()
        self.timerCheckHotkey.timeout.connect(self.isHotkeyEvent)
        self.timerCheckHotkey.start(25)

        self.mouseThread = Thread(target=mousehook.mouseHook)
        mousehook.mouseHandlers.append(self.reg_low_level_mouse_event)

        # Timers
        self.timerKeyHeld = QTimer()
        self.timerKeyHeld.timeout.connect(self.checkHeldKeyReleased)
        self.timerKeyHeld.timeout.connect(self.isTKeyEvent)
        self.timerKeyHeld.timeout.connect(self.low_level_mouse_event)
        self.timerKeyHeld.timeout.connect(self.menuCancel)
        self.timer_checkKeyHeld = QTimer()
        self.timer_checkKeyHeld.timeout.connect(self.checkKeyHeld)
        self.waitHKey = QTimer()
        self.waitHKey.timeout.connect(self.waitHKeyrelease)
        self.hkey_release_counter = 0

        # Aliases
        pass

        # Beta variables
        pass

    def changeDetected(self, activeWindow, activeTitle, handle_foreground):
        """Checks if the new active window has a profile attached to it. If so, it loads that profile.
        Otherwise, the global profile is loaded.

        Args:
            activeWindow (QMainWindow): The new active window.
            activeTitle (str): The title of the active window.
            handle_foreground (int): The id of the foreground window.
        """

        global regApps
        self.handle_foreground = handle_foreground
        if activeWindow not in regApps:
            self.loadGlobal()
            return

        self.activeWindow = activeWindow
        self.activeTitle = activeTitle
        self.loadProfile()
        self.appendWithGeneralHotKeys()
        self.loadHotkeys()

    def loadHotkeys(self):
        """Deletes old hotkeys. Afterwards, loops over each pie menu corresponding to the active window,
        and adds their hotkeys if the menu is enabled."""

        self.flushHotkeys()

        for pieMenu in self.profile["pieMenus"]:
            if not pieMenu["enable"]:
                continue

            keyboard.add_hotkey(pieMenu["hotkey"],
                                self.registerHotkeyEvent,
                                suppress=True,
                                args=(pieMenu["hotkey"], pieMenu))
            self.loadedHotkeys.append(pieMenu["hotkey"])

        if "hotkeys" not in self.profile.keys():
            return

        for hotkey in self.profile["hotkeys"]:
            if not hotkey["enable"]:
                continue

            params = None if "params" not in hotkey.keys() else hotkey["params"]

            keyboard.add_hotkey(hotkey['hotkey'],
                                self.registerHotkeyEvent,
                                suppress=True,
                                args=(hotkey['hotkey'], None, hotkey['function'], params))
            self.loadedHotkeys.append(hotkey["hotkey"])

    def loadTriggerKeys(self):
        # enable the following logic if hotkeys and triggerkeys are allowed to be same/clash.
        # for key in self.loadedHotkeys:
        #     if key != self.A_ThisHotkey:
        #         keyboard.remove_hotkey(key)

        for slices in self.openPieMenu["slices"]:
            if slices["triggerKey"] == self.A_ThisHotkey:
                self.sameTKeyHKey = slices
                continue
            if slices["triggerKey"] == "None":
                pass
            else:
                keyboard.add_hotkey(slices["triggerKey"], self.registerTKeyEvent, suppress=True,
                                    args=[slices["triggerKey"], slices])
                self.loadedTriggerKeys.append(slices["triggerKey"])

    def loadFinalTriggerKey(self):
        if self.sameTKeyHKey is None:
            return

        keyboard.add_hotkey(self.sameTKeyHKey["triggerKey"], self.registerTKeyEvent, suppress=True,
                            args=[self.sameTKeyHKey["triggerKey"], self.sameTKeyHKey])
        self.loadedTriggerKeys.append(self.sameTKeyHKey["triggerKey"])
        # self.sameTKeyHKey = None

    def registerTKeyEvent(self, Tkey, pie):
        self.A_TriggerKey = Tkey
        self.triggeredPieSlice = pie

    def isTKeyEvent(self):
        if self.A_TriggerKey is None:
            return
        self.launchByTriggerKey()

    def unloadTriggerKeys(self):
        # if len(self.loadedTriggerKeys) == 0:
        #     return
        # for Tkey in self.loadedTriggerKeys:
        #     keyboard.remove_hotkey(Tkey)
        self.loadedTriggerKeys.clear()
        self.loadHotkeys()

    def launchByTriggerKey(self):
        window.launchByTrigger(int(self.triggeredPieSlice["SliceNumber"]) - 1)
        self.resetAttributes()

    def flushHotkeys(self):
        if len(self.loadedHotkeys):
            keyboard.unhook_all_hotkeys()

        self.loadedHotkeys.clear()

    def loadProfile(self):
        global settings

        self.profile = [p for p in settings["appProfiles"] if
                        p["ahkHandle"] == self.activeWindow][0]

    def loadGlobal(self):
        global settings

        # Store the global profile in a variable globalProfile
        # so no need to search for it, and keep this logic below if global is not found in globalProfile var

        self.activeWindow = None

        self.profile = [p for p in settings["appProfiles"] if
                        p["ahkHandle"] == "Default"][0]

        self.loadHotkeys()

    def registerActiveProfileHotkeys(self) -> list[str]:
        hotkeys = list()

        def getProfileHotkeys(obj, key, profile):
            for item in obj:
                if not item["enable"]:
                    continue

                hotkeys.append(item["hotkey"])


        # for profile in settings["appProfiles"]:  # For the general hotkeys and piemenus.
        if self.profile["profile_name"] == "Default Profile":
            return hotkeys

        for option in ["pieMenus", "hotkeys"]:
            if option in self.profile.keys():
                getProfileHotkeys(self.profile[option],
                                  "hotkey",
                                  self.profile["ahkHandle"])
        return hotkeys

    def appendWithGeneralHotKeys(self):
        """Adding global (or general) hotkeys and piemenus to the profile ones to load in one go,
         unless the loaded profile contains a hotkey overriding the general entry."""

        globalProfile = [p for p in settings["appProfiles"] if
                         p["ahkHandle"] == "Default"][0]
        currentHotkeys = self.registerActiveProfileHotkeys()

        for option in ["pieMenus", "hotkeys"]:
            for item in globalProfile[option]:
                if "general" not in item.keys():
                    continue

                if not item["general"] or not item["enable"]:
                    continue

                if item["hotkey"] in currentHotkeys:
                    continue

                self.profile[option].append(item)

    def runHotkey(self):  # TODO: Resolve duplicate code.
        if self.A_ThisHotkeyFunction.lower() == "none" or not self.A_ThisHotkeyFunction:
            return

        if "brightness" in self.A_ThisHotkeyFunction:
            pieFunctions.sendHotkey([self.A_ThisHotkeyFunction, self.A_ThisHotkeyParameters[0]])
            return

        if self.A_ThisHotkeyFunction == "GetWindowName":
            print(w32gui.GetClassName(
                w32gui.GetForegroundWindow()))  # Key for the default profile. Makes creating new profiles easier.
            return

        if self.A_ThisHotkeyFunction not in pieFunctions.FUNCTIONS.keys():
            print(f"Invalid button self.A_ThisHotkeyFunction: {self.A_ThisHotkeyFunction}")
            return

        func = pieFunctions.FUNCTIONS[self.A_ThisHotkeyFunction]
        func(self.A_ThisHotkeyParameters)

        self.A_ThisHotkey = None

    def registerHotkeyEvent(self, hotkey, pieMenus=None, function=None, params=None):  # TODO: Resolve duplicate code.
        self.A_ThisHotkey = hotkey
        self.A_ThisHotkeyIsForPieMenu = bool(pieMenus)

        if self.A_ThisHotkeyIsForPieMenu:
            self.openPieMenu = pieMenus
            return

        self.A_ThisHotkeyFunction = function
        self.A_ThisHotkeyParameters = params
        self.A_ThisHotkeyHandled = False

    def isHotkeyEvent(self):
        if self.A_ThisHotkey is None:
            return

        if not self.A_ThisHotkeyIsForPieMenu:  # Adaptation to the system as to not 'hold' standalone hotkeys.
            if self.A_ThisHotkeyHandled:
                return
            self.A_ThisHotkeyHandled = True
        self.hotkeyEvent()

    def hotkeyEvent(self):
        if self.A_ThisHotkeyIsForPieMenu:
            if not self.isMenuOpen and self.HKeyLetgo:
                self.launch_pie_menus()
        else:
            self.runHotkey()
            # keep the following call as it is, do not run it on separate thread(no problems though in doing that,
            # just saving some CPU power).
            # self.checkKeyHeld()

    def launch_pie_menus(self):
        cursorpos = QCursor.pos()
        self.init_cursorpos = cursorpos

        if IS_MULTI_MONITOR_SETUP:
            detectMonitorChange(cursorpos, self.handle_foreground)

        self.isMenuOpen = True
        window.showMenu(self.openPieMenu, cursorpos)
        self.loadTriggerKeys()

        self.timerKeyHeld.start(25)

        # example of passing arguments to function call in different thread
        # self.mouseThread = Thread(target = mousehook.mouseHook, args = [self.keyHeld] )

        self.mouseThread = Thread(target=mousehook.mouseHook)
        self.mouseThread.start()

        self.menu_open_time = datetime.datetime.now()

        # 194 is special value, do not change unless you what you are doing
        self.timer_checkKeyHeld.start(194)

    def checkKeyHeld(self):
        # if self.menu_open_time == None:
        #     self.timer_checkKeyHeld.stop()
        #     return
        # time_elapsed = datetime.datetime.now() - self.menu_open_time
        # fast_out( time_elapsed.total_seconds())
        # if time_elapsed.total_seconds() < 0.2:
        # return

        """This function will be called once almost exactly after 2 secs to check 
           for whether key is held down or not and quick/speedy gesture activation.
           above comments are code to test time elapsed."""

        if not self.isMenuOpen:
            # if right click is pressed immediately after opening pie menus, currentMousePos becomes None,
            # and this causes errors over.
            # so better check if pie menu is open or not.
            return

        currentMousePos = QCursor.pos()
        inRadius = float(self.openPieMenu["in_out_radius"].split("_")[0])
        mouseInCircle = (currentMousePos.x() - self.init_cursorpos.x()) ** 2 + (
                currentMousePos.y() - self.init_cursorpos.y()) ** 2 < inRadius ** 2

        self.keyHeld = keyboard.is_pressed(self.A_ThisHotkey) or not mouseInCircle

        if not self.keyHeld:
            self.loadFinalTriggerKey()
        self.timer_checkKeyHeld.stop()

    def checkHeldKeyReleased(self):
        if self.keyHeld and keyboard.is_pressed(self.A_ThisHotkey):
            pass
        elif not self.keyHeld:
            if not window.isMenuOpen():
                self.resetAttributes()
        else:
            window.releasedHeldKey()
            self.resetAttributes()

    def low_level_mouse_event(self):
        if self.isLMBup:
            window.releasedHeldKey()
            self.resetAttributes()

        if self.isWheel:
            window.ll_wheel_event(self.isWheel)
            self.isWheel = False

    def menuCancel(self):
        if keyboard.is_pressed('esc') or self.isRMBup:
            window.killMenu()
            self.resetAttributes()

    def reg_low_level_mouse_event(self, event):
        # register low level mouse event
        event_type = event.event_type

        if event_type == 'RButton Down':
            return -1  # Block rmb down
        if event_type == 'LButton Down':
            return -1  # Block lmb down

        if event_type == 'RButton Up':
            self.isRMBup = True
            return -1

        if event_type == 'LButton Up' and not self.keyHeld:
            self.isLMBup = True
            return -1
        elif event_type == 'LButton Up' and self.keyHeld:
            return -1

        if event_type == 'wheel':
            # scan code === lParam[1]
            self.isWheel = event

    def waitHKeyrelease(self):
        if self.A_ThisHotkey is None:
            self.A_ThisHotkeyIsForPieMenu = None
            self.A_ThisHotkeyFunction = None
            self.A_ThisHotkeyParameters = None
            self.HKeyLetgo = True
            self.waitHKey.stop()
            return

        self.hkey_release_counter += int(self.hkey_release_counter < 100)

        if (not keyboard.is_pressed(self.A_ThisHotkey)) and self.hkey_release_counter >= 6:
            self.A_ThisHotkeyIsForPieMenu = None
            self.A_ThisHotkeyFunction = None
            self.A_ThisHotkeyParameters = None
            self.A_ThisHotkey = None
            self.HKeyLetgo = True
            self.waitHKey.stop()

    def resetAttributes(self):
        # stop timers
        self.timerKeyHeld.stop()

        # stop thread and join in main thread
        if self.mouseThread.is_alive():
            windll.user32.PostThreadMessageW(self.mouseThread.ident, WM_QUIT, 0, 0)
            self.mouseThread.join()

        # reset attributes
        self.menu_open_time = None
        self.init_cursorpos = None
        self.isLMBup = False
        self.isRMBup = False
        self.unloadTriggerKeys()
        self.keyHeld = False
        self.isMenuOpen = False
        self.openPieMenu = None
        # self.A_ThisHotkeyIsForPieMenu = None
        self.A_ThisHotkeyFunction = None
        self.A_ThisHotkeyParameters = None
        self.A_ThisHotkeyHandled = None
        self.A_TriggerKey = None
        self.sameTKeyHKey = None
        self.HKeyLetgo = False
        self.hkey_release_counter = 0
        self.HKeyLetgo = False
        self.waitHKey.start(25)
        # self.A_ThisHotkey = set to None in waitHKeyrelease method
        # window.hide() # this will hide the window after menu is closed.


# -------------------------------Class End--------------------------------------

def detectWindowChange():
    global activeProfile, settings

    previousActiveWindow = activeProfile.activeWindow
    try:
        handle_foreground = w32gui.GetForegroundWindow()
        activeTitle = w32gui.GetWindowText(handle_foreground)
    except Exception as e:
        print(e)
        sys.exit(-1)

    activeWindow = w32gui.GetClassName(handle_foreground)

    if previousActiveWindow == activeWindow:
        return

    activeProfile.changeDetected(activeWindow, activeTitle, handle_foreground)


def detectMonitorChange(cursorpos, handle_foreground):
    if mon_manager.move_to_active_screen(cursorpos, window) == "no_change":
        return
    window.showFullScreen()
    w32gui.SetForegroundWindow(handle_foreground)


# Json settings loading
script_dir = os.path.dirname(__file__)
try:
    with open("settings/appProfiles.json") as appProfilesFile:
        settings = json.load(appProfilesFile)
except Exception as e:
    print("could not locate or load the json settings - appProfiles: ", e)
    sys.exit(-1)

try:
    with open("settings/globalSettings.json") as globalSettingsFile:
        globalSettings = json.load(globalSettingsFile)
        globalSettings = globalSettings['globalSettings']
except Exception as e:
    print("could not locate or load the json globalSettings - globalSettings: ", e)
    sys.exit(-1)

hotkeysPerProfile = defaultdict(list)

# /END Json loading ------------------


# ------- Global variables ----------------
DEBUGMODE = False
WM_QUIT = 0x0012
IS_MULTI_MONITOR_SETUP = False
APP_SUSPENDED = False
WINCHANGE_latency = 100  # ms

if globalSettings['winChangeLatency'] and 25 <= globalSettings['winChangeLatency'] <= 200:
    WINCHANGE_latency = globalSettings['winChangeLatency']

# ------- /END Global variables ----------------

MODES = defaultdict(lambda: 'DEBUG')
MODES['QtCore.QtInfoMsg'] = 'INFO'
MODES['QtCore.QtWarningMsg'] = 'WARNING'
MODES['QtCore.QtCriticalMsg'] = 'CRITICAL'
MODES['QtCore.QtFatalMsg'] = 'FATAL'


# Qt warning message handler callback
def qt_message_handler(mode, context, message):
    """This method handles warning messages, sometimes, it might eat up
       some warning which won't be printed, so it is good to disable this
       when developing, debugging and testing."""

    global MODES

    if "QWindowsWindow::setGeometry: Unable to set geometry" in message:

        """This is ignore the warning message when changing the 
           screen on which app is shown on multi monitor systems.
           Qt automatically decides best size, that's I have ignored it here."""

        return

    mode = MODES[mode]

    print(f'qt_message_handler: line: {context.line}, func: {context.function}(), file: {context.file}')
    print(f'{mode}: {message}')


def suspend_app():
    if activeProfile.isMenuOpen:
        # toast msg close open pie menus
        return

    activeProfile.flushHotkeys()
    keyboard.unhook_all()

    # stop all timers and threads in app
    timerWinChange.stop()
    activeProfile.timerCheckHotkey.stop()

    global APP_SUSPENDED
    APP_SUSPENDED = True
    # Do not call this here, it will mess up things.
    # activeProfile.resetAttributesOnMenuClose()


def resume_app():
    # resume all timers and threads in app
    timerWinChange.start(WINCHANGE_latency)
    activeProfile.loadGlobal()
    activeProfile.timerCheckHotkey.start(25)

    global APP_SUSPENDED
    APP_SUSPENDED = False
    # do not call construction of active_profile or instantiate it again, let's keep it clean.


def get_all_references(with_funcs=False):
    only_vars = {
        "DEBUGMODE": DEBUGMODE,
        "WM_QUIT": WM_QUIT,
        "IS_MULTI_MONITOR_SETUP": IS_MULTI_MONITOR_SETUP,
        "APP_SUSPENDED": APP_SUSPENDED,
        "WINCHANGE_latency": WINCHANGE_latency
        }

    if not with_funcs:
        return only_vars

    with_funcs = {}
    with_funcs.update(only_vars)
    with_funcs.update({
        "suspend_app": suspend_app,
        "resume_app": resume_app
        })

    return with_funcs


# ------------------------------------ MAIN ---------------------------------

# High DPI stuff
# these should be in this sequence 
# and before creating QApplication
# https://stackoverflow.com/questions/41331201/pyqt-5-and-4k-screen
# https://stackoverflow.com/questions/39247342/pyqt-gui-size-on-high-resolution-screens
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "2"
# os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
if globalSettings['ScaleFactor']:
    # following line scales the entire app by the given factor.
    os.environ["QT_SCALE_FACTOR"] = str(globalSettings['ScaleFactor'])

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)  # enable highdpi scaling
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)  # use highdpi icons

app = QtWidgets.QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

app_icon = "C:\\Users\\S\\Downloads\\pexels-pixabay-38537.jpg"
tray_icon = QtGui.QIcon(os.path.join(script_dir, "resources/icons/tray_icon.png"))

# tray icon attribution : # icon type 2: <div>Icons made by <a href="https://www.flaticon.com/authors/ultimatearm"
# title="ultimatearm">ultimatearm</a> from <a href="https://www.flaticon.com/"
# title="Flaticon">www.flaticon.com</a></div>
# tray icon link : https://www.flaticon.com/free-icon/pie_1411020?term=pies&related_id=1411020

trayWidgetQT = QWidget()
trayWidget = SystemTrayIcon(QtGui.QIcon(tray_icon), get_all_references, trayWidgetQT)
trayWidgetQT.setStyleSheet(tray_theme.QMenu)
trayWidget.show()

window = Window(settings, globalSettings)
window.showFullScreen()

# Qt warning messages handler installing
QtCore.qInstallMessageHandler(qt_message_handler)

# Registering the app profiles 
regApps = []
for profiles in settings["appProfiles"]:
    if profiles["ahkHandle"] == "Default":
        continue
    # do not register profile if not enabled
    if profiles["enable"] == 0:
        continue
    regApps.append(profiles["ahkHandle"])

# WARNING : ActiveProfile and Monitor_Manager should only have once instance.
# I mean, think why do you need two instance, no need, it will cause chaos.
activeProfile = ActiveProfile()

if len(app.screens()) > 1:
    IS_MULTI_MONITOR_SETUP = True
    from monitor_manager import Monitor_Manager


    mon_manager = Monitor_Manager(app.screens(), app.primaryScreen())

# Timers
timerWinChange = QTimer()
timerWinChange.timeout.connect(detectWindowChange)

# Timer starts
timerWinChange.start(WINCHANGE_latency)

# ----------------------END-----------------------------
# This statement has to stay the last line
# - everything below it will go out of scope of any thing.
sys.exit(app.exec_())
# ----------------------/END-----------------------------
