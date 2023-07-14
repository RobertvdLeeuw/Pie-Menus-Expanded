from menuScript import MenuOption


steamExe = r"C:\Program Files (x86)\Steam\Steam.exe"

labelsAndInstructions = {'Store': 'steam://store',
                         'Project Zomboid': 'steam://run/108600',
                         'Library': 'steam://open/games'}

menuOptions = [MenuOption(label, "runCommand", [instruction]) for label, instruction in
               labelsAndInstructions.items()]
