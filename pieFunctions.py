import subprocess
import sys
from time import sleep

import keyboard
import screen_brightness_control as sbc


# as of now, receiving all params as one list in one var
# receive them directly as parameters

def sendKeys(params):
    params = params[0]
    # print(params)
    keyboard.write(params)


def sendKeysTyping(params):
    params = params[0]
    for ch in params:
        keyboard.write(ch)


def sendHotkey(params):
    hotkey = params[0]

    repeat_count = 1 if len(params) == 1 else params[1]

    if "brightness" in hotkey:
        brightness_control(params)
        return

    for _ in range(int(repeat_count)):
        keyboard.send(hotkey)


def runScript(params):
    filePath: str = params["filePath"]

    if filePath.endswith(".py") or filePath.endswith(".ahk"):
        if args := params["args"]:
            subprocess.Popen([sys.executable, filePath] + args)
            return
        subprocess.Popen([sys.executable, filePath])
    else:
        print(f"Invalid script type: {filePath}")


def runProgram(params):
    filePath: str = params["filePath"]

    if ".exe" in filePath:
        subprocess.Popen(filePath)
    else:
        print(f"Invalid program type: {filePath}")


def brightness_control(params):
    hotkey = params[0]
    change_value = params[1]
    if "up" in hotkey:
        change_value = "+" + str(change_value)
        sbc.set_brightness(change_value)
    if "down" in hotkey:
        change_value = "-" + str(change_value)
        sbc.set_brightness(change_value)
    if "fade" in hotkey:
        change_value = int(change_value)
        sbc.fade_brightness(change_value, increment=10)


FUNCTIONS = {"sendKeys": sendKeys,
             "sendKeysAHK": sendKeysTyping,
             "sendHotkey": sendHotkey,
             "runScript": runScript,
             "runProgram": runProgram}
