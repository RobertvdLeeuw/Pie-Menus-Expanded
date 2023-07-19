import json
import subprocess
import sys
import win32gui as w32gui

import keyboard

from settings.menuScripts.menuScript import MenuOption


# as of now, receiving all params as one list in one var
# receive them directly as parameters

def sendKeys(params: list):
    params = params[0]
    keyboard.write(params)


def sendHotkey(params: list):
    hotkey = params[0]

    repeat_count = 1 if len(params) == 1 else params[1]

    for _ in range(int(repeat_count)):
        keyboard.send(hotkey)


def runScript(params: dict):  # TODO: Test for all code types.
    filePath: str = params["filePath"]

    for scriptType in ('.py', '.ahk'):
        if filePath.endswith(scriptType):
            args = None if "args" not in params else params["args"]
            subprocess.Popen([sys.executable, filePath] + args)
            return

    print(f"Invalid script type: {filePath}")


def runProgram(params: dict):
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


def runCommand(params: list):
    params.insert(0, 'start')
    print(' '.join(params))

    subprocess.run(params, shell=True)


def scriptedMenu(params: dict) -> list[MenuOption]:  # TODO: Rename to buildScriptedMenu.
    """
    Upon opening piemenu, runs the script and populates the menu with the given results.
    """

    filePath: str = params["filePath"]

    if not filePath.endswith('.py'):
        print(f"Invalid script type: {filePath}")
        return []

    parentFolder = '\\'.join(filePath.split('\\')[0:-1])
    sys.path.append(parentFolder)

    moduleName = filePath.replace('.py', '\\').split('\\')[-2]

    try:
        command = "import importlib"
        command += f"\nimport {moduleName}"
        command += f"\nimportlib.reload({moduleName})"
        command += f"\nmenuOptions = {moduleName}.menuOptions"

        exec(command, globals())

        return menuOptions
    except Exception as e:
        print(f'Failed to run {moduleName}:', e)

    return []


FUNCTIONS = {"sendKeys": sendKeys,
             "sendHotkey": sendHotkey,
             "runScript": runScript,
             "runProgram": runProgram,
             "getWindowName": getWindowName,
             "createProfile": createProfile,
             "runCommand": runCommand,
             "scriptedMenu": scriptedMenu}
