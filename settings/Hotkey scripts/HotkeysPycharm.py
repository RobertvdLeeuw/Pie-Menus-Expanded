import sys

import keyboard


# F13 and F14 are reserved for the pie menus.

if sys.argv[1] == "F15":  # Reload
    keyboard.press("Ctrl")
    keyboard.press("F2")
    keyboard.release("F2")  # TODO: test just using write()
    keyboard.release("Ctrl")

    keyboard.press("Ctrl")
    keyboard.press("F2")
    keyboard.release("F2")  # TODO: test just using write()
    keyboard.release("Ctrl")

    keyboard.press("Ctrl")
    keyboard.press("F5")
    keyboard.release("F5")  # TODO: test just using write()
    keyboard.release("Ctrl")

elif sys.argv[1] == "F16":  # TODO: Untoggle.
    keyboard.write("I# ")

    keyboard.press("Esc")
    keyboard.release("Esc")

# F17 and F18 are bound using Pycharm itself, and F19 is global bound.

elif sys.argv[1] == "F20":
    pass

elif sys.argv[1] == "F21":
    pass

elif sys.argv[1] == "F22":
    pass

elif sys.argv[1] == "F23":
    pass

elif sys.argv[1] == "F24":
    pass

elif sys.argv[1] == "Alt+F13":
    keyboard.press("Ctrl")
    keyboard.press("-")
    keyboard.release("-")
    keyboard.release("Ctrl")


elif sys.argv[1] == "Alt+F14":
    keyboard.press("Ctrl")
    keyboard.press("+")
    keyboard.release("+")
    keyboard.release("Ctrl")

elif sys.argv[1] == "Alt+F15":  # Previous function
    keyboard.write("?def \n")  # TODO: Add modes with keys (c -> class, f -> function, etc)

elif sys.argv[1] == "Alt+F16":  # Next function
    keyboard.write("/def \n")

elif sys.argv[1] == "Alt+F17":
    pass

elif sys.argv[1] == "Alt+F18":
    pass

elif sys.argv[1] == "Alt+F19":
    pass

elif sys.argv[1] == "Alt+F20":
    pass

elif sys.argv[1] == "Alt+F21":
    pass

if sys.argv[1] == "Alt+F22":
    pass

if sys.argv[1] == "Alt+F23":
    pass

if sys.argv[1] == "Alt+F24":
    pass
