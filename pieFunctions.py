import json
import subprocess
import sys
import win32gui as w32gui

import keyboard


# as of now, receiving all params as one list in one var
# receive them directly as parameters

def sendKeys(params):
    params = params[0]
    keyboard.write(params)


def sendHotkey(params):
    hotkey = params[0]

    repeat_count = 1 if len(params) == 1 else params[1]

    for _ in range(int(repeat_count)):
        keyboard.send(hotkey)


def runScript(params):  # TODO: Test for all code types.
    filePath: str = params["filePath"]

    for scriptType in ('.py', '.ahk'):
        if filePath.endswith(scriptType):
            args = None if "args" not in params else params["args"]
            subprocess.Popen([sys.executable, filePath] + args)
            return

    print(f"Invalid script type: {filePath}")


def runProgram(params):
    filePath: str = params["filePath"]

    if ".exe" not in filePath:
        print(f"Invalid program type: {filePath}")
        return

    subprocess.Popen(filePath)


def getWindowName() -> str:
    try:
        handle_foreground = w32gui.GetForegroundWindow()
    except Exception as e:
        return "Failed to get selected window."

    name = w32gui.GetClassName(handle_foreground)
    print(name)

    return name


def createProfile():
    handle = getWindowName()
    newProfileJSON = {"ahkHandle": handle,
                      "label": "New Profile",
                      "piemenus": [],
                      "hotkeys": []}
    try:
        with open("settings/appProfiles.json", "r", encoding="utf-8") as file:
            jsonFile = json.load(file)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        print(f"Could not locate or load the JSON file: settings/appProfiles.json")
        sys.exit(-1)

    for profile in jsonFile["profiles"]:
        if profile["ahkHandle"] == handle:
            print("Profile already exists.")
            return

    jsonFile["profiles"].append(newProfileJSON)

    try:
        with open("settings/appProfiles.json", "w", encoding="utf-8") as file:
            json.dump(jsonFile, file, indent=2)
    except FileNotFoundError:
        print(f"Could not locate or save to JSON file: settings/appProfiles.json")
        sys.exit(-1)


def runCommand(params):
    subprocess.run


FUNCTIONS = {"sendKeys": sendKeys,
             "sendHotkey": sendHotkey,
             "runScript": runScript,
             "runProgram": runProgram,
             "getWindowName": getWindowName,
             "createProfile": createProfile,
             "runCommand": runCommand}
