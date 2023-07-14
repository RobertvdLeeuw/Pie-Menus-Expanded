from __future__ import annotations

from pieFunctions import FUNCTIONS

from enum import Enum
from functools import partial
import json
import sys

from PySide2 import QtWidgets, QtCore, QtGui


class NodeType(Enum):
    PROFILE = 0
    PIEMENU = 1
    PIESLICE = 2
    PIESUBSLICE = 3
    HOTKEY = 4


CHILDREN = {NodeType.PROFILE: [NodeType.PIEMENU, NodeType.HOTKEY],
            NodeType.PIEMENU: [NodeType.PIESLICE],
            NodeType.PIESLICE: [NodeType.PIESUBSLICE]}

NODENAMES = {NodeType.PROFILE: "Profiles",
             NodeType.PIEMENU: "Pie Menus",
             NodeType.PIESLICE: "Slices",
             NodeType.PIESUBSLICE: "Sub slices",
             NodeType.HOTKEY: "Hotkeys"}

CHILDTYPES = {name.lower().replace(" ", ""): ntype for ntype, name in NODENAMES.items()}


class InputType(Enum):
    TEXTFIELD = 0
    SELECTION = 1
    CHECKBOX = 2
    PARAMETERSINGLE = 3
    PARAMETERDOUBLE = 4
    KEYINPUT = 5


STANDARDATTRIBUTES = {NodeType.PROFILE: {"theme": InputType.TEXTFIELD,
                                         "enabled": InputType.CHECKBOX},
                      NodeType.PIEMENU: {"theme": InputType.TEXTFIELD,
                                         "hotkey": InputType.KEYINPUT,
                                         "general": InputType.CHECKBOX,
                                         "enabled": InputType.CHECKBOX,
                                         "offset_angle": InputType.TEXTFIELD,
                                         "offset_slices": InputType.TEXTFIELD,
                                         "returnMousePos": InputType.CHECKBOX},
                      NodeType.PIESLICE: {"triggerKey": InputType.KEYINPUT,
                                          "function": InputType.SELECTION,
                                          "enabled": InputType.CHECKBOX,
                                          "sliceNumber": InputType.TEXTFIELD,
                                          "icon": InputType.TEXTFIELD},
                      NodeType.PIESUBSLICE: {"triggerKey": InputType.KEYINPUT,
                                             "function": InputType.SELECTION,
                                             "enabled": InputType.CHECKBOX,
                                             "sliceNumber": InputType.TEXTFIELD,
                                             "icon": InputType.TEXTFIELD},
                      NodeType.HOTKEY: {"hotkey": InputType.KEYINPUT,
                                        "function": InputType.SELECTION,
                                        "general": InputType.CHECKBOX,
                                        "enabled": InputType.CHECKBOX}}


class SettingsManager:
    """A wrapper for everything JSON related."""

    def __init__(self):
        self.appProfiles = None
        self.globalSettings = None
        self.registeredApps = []

        self.reloadSettings()

    def reloadSettings(self):
        self.appProfiles = self.loadJSONFile("settings/appProfiles.json")["profiles"]
        self.globalSettings = self.loadJSONFile("settings/globalSettings.json")['globalSettings']
        self.registeredApps.clear()

        self.registerProfiles()

    @staticmethod
    def loadJSONFile(filePath: str) -> dict:
        try:
            with open(filePath, "r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            print(f"Could not locate or load the JSON file: {filePath} ")
            sys.exit(-1)

    def saveJSONFile(self, dataObject: QtCore.QObject, filePath: str):
        jsonData = self.buildJSONFile(dataObject)

        try:
            with open(filePath, "w", encoding="utf-8") as file:
                json.dump(jsonData, file, indent=2)
        except FileNotFoundError:
            print(f"Could not locate or save to JSON file: {filePath} ")
            sys.exit(-1)

        self.reloadSettings()

    def registerProfiles(self):
        """Re-registers the profiles after potential changes have been made."""

        self.registeredApps.clear()
        for profiles in self.appProfiles:
            if profiles["ahkHandle"] == "Default" or not profiles.get("enabled", True):
                continue

            self.registeredApps.append(profiles["ahkHandle"])

    @staticmethod
    def buildJSONFile(obj: SettingsNode | SettingsMenu) -> dict:
        """Serializes the data contained in all widgets into a new JSON file."""

        jsonData: dict[str, any] = {}

        if not isinstance(obj, SettingsMenu):
            if obj.nodeType == NodeType.PROFILE:
                jsonData["ahkHandle"] = obj.ahkHandle

            jsonData["label"] = obj.label if isinstance(obj.label, str) else obj.label.text()

            for label, inputObject in obj.attributes.items():
                label = inputObject.getLabel()

                if not str(inputObject.getValue()) or \
                        str(inputObject.getValue()).lower() == f"enter {label.lower()}":
                    continue

                jsonData[label.lower()] = inputObject.getValue()
        else:
            print('\n'.join([f"\t{child.label.text()}" for child in obj.children]))

        for child in obj.children:
            nodeName = NODENAMES[child.nodeType].lower().replace(" ", "")
            typeList = jsonData.get(nodeName, [])

            childData = SettingsManager.buildJSONFile(child)

            # TODO: Remove this ugly band-aid solution and fix the underlying issue of profile duplication
            if isinstance(obj, SettingsMenu):
                for jsonChild in typeList:
                    if jsonChild['ahkHandle'] == childData["ahkHandle"]:
                        typeList.remove(jsonChild)

            typeList.append(childData)
            jsonData[nodeName] = typeList

        if hasattr(obj, "paramsLayout"):
            if obj.paramTypeDouble:
                params: dict[str, str | int] = {}

                for param in obj.params:
                    params[param.getLabel()] = param.getValue()
            else:
                params: list[str | int] = []

                for param in obj.params:
                    params.append(param.getValue())

            if params:  # Not saving empty params list/dict.
                jsonData["params"] = params

        return jsonData


class SettingsMenu(QtWidgets.QTabWidget):
    """The 'main' widget of the settings menu. This contains each profile widget and the links to the instantiated
    SettingsManager."""

    def __init__(self, settingsManager: SettingsManager, systemTrayIcon: QtWidgets.QSystemTrayIcon):
        super().__init__()

        self.settingsManager = settingsManager
        self.systemTrayIcon = systemTrayIcon

        self.children: list[ProfileNode] = []

        self.setWindowTitle("Settings")
        self.hide()

    @staticmethod
    def getSpawnLocation(resolution: QtCore.QRect, menuSize: tuple[int, int]) -> tuple[int, int]:
        """Calculates the location to place the menu at when instantiating."""

        x = resolution.width() // 2 - menuSize[0] // 2
        y = resolution.height() // 2 - menuSize[1] // 2

        return x, y

    def setColors(self):
        """Changes the theme of the menu itself according to the CSS file."""

        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        with open(r"resources\settingsMenu.css", "r", encoding="utf-8") as cssFile:
            self.setStyleSheet(cssFile.read())

    def showMenu(self, resolution: QtCore.QRect):
        """Instantiates the menu and creates a profileNode for each profile in the JSON."""

        self.settingsManager.reloadSettings()

        size = (550, 650)
        location = self.getSpawnLocation(resolution, size)
        self.setGeometry(*location, *size)

        minimumSize = (300, 400)
        self.setMinimumSize(*minimumSize)

        self.clear()
        for profile in self.settingsManager.appProfiles:
            profileWidget = ProfileNode(self, profile)
            profileWidget.setParent(self)

            self.children.append(profileWidget)

            scrollWidget = QtWidgets.QScrollArea()
            scrollWidget.setWidget(profileWidget)
            scrollWidget.setWidgetResizable(True)
            profileWidget.scrollWidgetParent = scrollWidget

            self.addTab(scrollWidget,
                        profile["label"])

        self.setColors()
        super().show()

    def closeEvent(self, event):
        self.systemTrayIcon.resume_app()

    def keyPressEvent(self, event):
        recursiveSendKeyEvents(self, event)


class KeyInputField(QtWidgets.QLineEdit):
    def __init__(self, value: str):
        super().__init__()

        self.recording = False
        self.setPlaceholderText('Click to set input')
        self.setText(value)
        self.setReadOnly(True)

        self.priorKeys = ""

        self.focusPolicy = QtCore.Qt.ClickFocus

    def focusInEvent(self, event):
        self.recording = True

        self.setPlaceholderText('Recording...')
        self.setReadOnly(False)

        self.priorKeys = self.text()
        self.setText('')

        self.clearFocus()  # Clear focus to capture user input

    # TODO: Use HasFocus() to revert to prior state when something else is clicked.

    def keyPressEvent(self, event):
        if not self.recording:
            return

        self.setText('')

        key = event.key()
        modifiers = event.modifiers()

        if key == QtCore.Qt.Key_unknown:
            return

        # TODO: IMPORTANT QKeySequence(key | modifiers)
        key_sequence = QtGui.QKeySequence(key | modifiers).toString(QtGui.QKeySequence.NativeText)

        self.setText(key_sequence)
        self.setReadOnly(True)

        if '?' in key_sequence:
            return  # Quick fix for incomplete key inputs (such as just 'Ctrl + Shift').

        self.priorKeys = key_sequence
        self.recording = False


class InputObject(QtWidgets.QHBoxLayout):
    """A wrapper around every type of input field, with an accounting label to the describe the type of input."""

    def __init__(self, inputType: InputType, **kwargs):
        super().__init__()
        self.addSpacing(10)

        self.label = kwargs.get("label", "")
        self.inputType = inputType

        if inputType == InputType.PARAMETERDOUBLE:
            self.labelWidget = QtWidgets.QLineEdit(self.label)
            self.addWidget(self.labelWidget)
        elif inputType not in (InputType.PARAMETERSINGLE, InputType.CHECKBOX):
            self.labelWidget = QtWidgets.QLabel(self.label.capitalize())
            self.addWidget(self.labelWidget)

        self.value = kwargs.get("value", "")

        self.valueWidget = None
        self.createValueWidget(inputType, kwargs.get("selectionItems"), kwargs.get("toggleScriptedFunc"))

        if inputType in (InputType.PARAMETERSINGLE, InputType.PARAMETERDOUBLE):
            removeButton = QtWidgets.QPushButton("Remove")
            removeButton.clicked.connect(partial(recursiveDeleteLater, self))
            self.addWidget(removeButton)

    def createValueWidget(self, inputType: InputType, selectionItems: dict, toggleScriptedFunc):
        """Creates a widget that can be used to input options, corresponding to the right type of input type."""

        if inputType in (InputType.TEXTFIELD, InputType.PARAMETERSINGLE, InputType.PARAMETERDOUBLE):
            self.valueWidget = QtWidgets.QLineEdit()

            text = self.value if self.value else f"Enter {self.label.lower()}"
            self.valueWidget.setText(str(text))
        elif inputType == InputType.KEYINPUT:
            self.valueWidget = KeyInputField(self.value)
        elif inputType == InputType.SELECTION:
            self.valueWidget = QtWidgets.QComboBox()
            self.valueWidget.addItems(selectionItems)

            self.valueWidget.currentTextChanged.connect(partial(toggleScriptedFunc, self.valueWidget))

            if self.value:
                self.valueWidget.setCurrentText(self.value)
        elif inputType == InputType.CHECKBOX:
            self.valueWidget = QtWidgets.QCheckBox(self.label.capitalize())

            checkState = QtCore.Qt.Checked if self.value else QtCore.Qt.Unchecked
            self.valueWidget.setCheckState(checkState)

        self.addWidget(self.valueWidget)

    def getValue(self) -> str | int:
        """Returns the value of the input field."""

        if isinstance(self.valueWidget, QtWidgets.QCheckBox):
            return int(self.valueWidget.isChecked())
        elif isinstance(self.valueWidget, QtWidgets.QComboBox):
            return self.valueWidget.currentText()
        elif self.valueWidget.text().isnumeric():
            return int(self.valueWidget.text())
        else:
            return self.valueWidget.text()

    def getLabel(self) -> str:
        if isinstance(self.valueWidget, QtWidgets.QCheckBox):
            return self.valueWidget.text()

        return self.labelWidget.text()


class SettingsNode(QtWidgets.QVBoxLayout):  # TODO: Create collapsible layout class.
    """The standard template for every type of 'complex' input object. I.e. pie menus, its (sub)slices and hotkeys."""

    def __init__(self, nodeType: NodeType, objectData: dict = None):
        self.json = objectData if objectData else {}
        self.nodeType = nodeType

        self.children: list[SettingsNode] = []
        self.label = QtWidgets.QLineEdit()  # Only used a descriptor for user when it's an SSG.
        self.attributes: dict[str, InputObject] = {}

        if nodeType == NodeType.PROFILE:
            return  # End of shared init TODO: Check if this is necessary again.

        QtWidgets.QVBoxLayout.__init__(self)  # TODO: Replace with super?

        if nodeType != NodeType.PIEMENU:
            self.paramsLayout = QtWidgets.QVBoxLayout()
            self.params: list[InputObject] = []
            self.paramTypeDouble = True

        self.childrenLayout = QtWidgets.QVBoxLayout()

        # Name and remove options.
        self.createTopLevelOptions(f"New {NODENAMES[self.nodeType][:-1]}")

        if self.json:
            self.setAttributesFromJSON()
        self.insertStandardAttributes()

        self.createMenu()

    def setAttributesFromJSON(self):
        """Instantiates all attributes present in the JSON data of the object."""

        for label, data in self.json.items():
            if not data:
                continue

            if label in ("piemenus", "slices", "subslices", "hotkeys"):
                for child in data:
                    self.createChild(CHILDTYPES[label.lower()], objectData=child)  # Creates and registers child.
            elif label == "function":
                self.attributes[label] = InputObject(InputType.SELECTION,
                                                     label=label,
                                                     value=data,
                                                     selectionItems=FUNCTIONS if self.nodeType != NodeType.HOTKEY
                                                     else {k: v for k, v in FUNCTIONS.items() if k != 'scriptedMenu'},
                                                     toggleScriptedFunc=self.toggleScripted)
            elif label in ("theme", "icon", "sliceNumber", "offset_angles", "offset_slices"):
                self.attributes[label] = InputObject(InputType.TEXTFIELD,
                                                     label=label,
                                                     value=data)
            elif label in ("hotkey", "triggerKey"):
                self.attributes[label] = InputObject(InputType.KEYINPUT,
                                                     label=label,
                                                     value=data)
            elif label in ("general", "enabled"):
                self.attributes[label] = InputObject(InputType.CHECKBOX,
                                                     label=label,
                                                     value=data)
            elif label == "params":
                self.setParameter(data)

    def setParameter(self, data):
        """Appends the parameter layout with the given parameter."""

        if not hasattr(self, "paramsLayout"):
            return  # Fail safe.

        if isinstance(data, list):
            for item in data:
                self.paramTypeDouble = False

                inputObject = InputObject(InputType.PARAMETERSINGLE,
                                          label="hotkey",
                                          value=item)
                self.paramsLayout.addLayout(inputObject)
                self.params.append(inputObject)
            return

        for key, value in data.items():
            inputObject = InputObject(InputType.PARAMETERDOUBLE,
                                      label=key,
                                      value=value)
            self.paramsLayout.addLayout(inputObject)
            self.params.append(inputObject)

    def insertStandardAttributes(self):
        """Inserts the arguments that are always supposed to be accessible for a given node type. Needed for newly
        created nodes."""

        for label, attrType in STANDARDATTRIBUTES[self.nodeType].items():
            if label in self.attributes:
                continue

            kwargs = {"label": label}
            if label == "function":
                kwargs["selectionItems"] = FUNCTIONS if self.nodeType != NodeType.HOTKEY else {k: v for k, v in
                                                                                               FUNCTIONS.items() if
                                                                                               k != 'scriptedMenu'}
                kwargs['toggleScriptedFunc'] = self.toggleScripted
            elif label == "enabled":
                kwargs["value"] = True

            if functionField := self.attributes.get('function'):
                if functionField.valueWidget.currentText() == 'scriptedMenu':
                    if label in ('icon', 'triggerKey'):
                        return

            self.attributes[label] = InputObject(attrType, **kwargs)

    def createTopLevelOptions(self, initLabel):
        """Inserts the controls always needed for every nodetype. I.e. name/label field and 'remove self' button."""

        topOptions = QtWidgets.QHBoxLayout()  # Name and remove options.

        self.label.setText(self.json.get("label", initLabel))
        topOptions.addWidget(self.label)

        topOptions.addStretch()

        removeButton = QtWidgets.QPushButton("Remove")

        removeButton.clicked.connect(partial(recursiveDeleteLater, self))
        topOptions.addWidget(removeButton)

        layout = self if self.nodeType != NodeType.PROFILE else self.layout
        layout.insertLayout(0, topOptions)

    def toggleScripted(self, selectionItems: QtWidgets.QComboBox, newlySelected: str):
        if newlySelected == 'scriptedMenu':
            result = QtWidgets.QMessageBox.question(selectionItems,  # TODO: Fix popup on settings menu open.
                                                    "Confirmation",
                                                    "Are you sure? Previously entered information, such as subslices, "
                                                    "will be removed.",
                                                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

            if result != QtWidgets.QMessageBox.Yes:
                return

            if self.childrenLayout is None:  # Already deleted, just to be sure.
                return

            [recursiveDeleteLater(self.attributes[attr]) for attr in ('triggerKey', 'icon') if attr in self.attributes]

            recursiveDeleteLater(self.childrenLayout)
            self.childrenLayout = None
            self.children.clear()
            return

        if self.childrenLayout is not None:
            return

        # Insert attributes: icon and triggerkey
        triggerKey = InputObject(InputType.KEYINPUT, label='triggerKey')
        self.attributes['triggerKey'] = triggerKey
        self.insertLayout(1, triggerKey)

        icon = InputObject(InputType.TEXTFIELD, label='icon')
        self.attributes['icon'] = icon
        self.insertLayout(3, icon)

        # Insert childrenLayout
        self.childrenLayout = QtWidgets.QVBoxLayout()
        for childType in CHILDREN.get(self.nodeType, []):
            options = self.createChildOptions(childType, self.childrenLayout)
            self.childrenLayout.insertLayout(0, options)

        self.addLayout(self.childrenLayout)

    def createChild(self, nodeType: NodeType, **kwargs):
        """Creates a new node of the given type and appends it to the list of children of this node."""

        child = SettingsNode(nodeType, kwargs.get("objectData"))

        self.children.append(child)

        if kwargs.get("layout"):
            spacing = kwargs.get("spacing", 15 if self.nodeType != NodeType.PIESLICE else 10)
            layout = offsetWrap(child, spacing)

            kwargs["layout"].insertLayout(1, layout)

    def createChildOptions(self, nodeType: NodeType, layout: QtWidgets.QLayout) -> QtWidgets.QHBoxLayout:
        """Creates the options for instantiating children, corresponding to the given node type."""

        childOptions = QtWidgets.QHBoxLayout()

        labelField = QtWidgets.QLabel(NODENAMES[nodeType])
        childOptions.addWidget(labelField)

        childOptions.addStretch()

        addButton = QtWidgets.QPushButton("Add")
        addButton.clicked.connect(partial(self.createChild, nodeType, layout=layout))
        childOptions.addWidget(addButton)

        return childOptions

    def addParam(self):
        """Adds a new parameter to the node."""

        inputType = InputType.PARAMETERDOUBLE if self.paramTypeDouble else InputType.PARAMETERSINGLE

        parameter = InputObject(inputType,
                                label="parameter")
        self.paramsLayout.insertLayout(1, parameter)
        self.params.append(parameter)

    def toggleParamType(self, button):
        """Changes the type of accepted parameters from double to single, or vice versa.
         I.e. 'path/to/file' -> 'filepath: 'path/to/file'."""

        self.paramTypeDouble = not self.paramTypeDouble

        for param in self.params:
            recursiveDeleteLater(param)
        self.params.clear()

        button.setText(f"Change to {'single' if self.paramTypeDouble else 'double'}")

    def createMenu(self):
        """Adds every layout to the node, finally (visually) creating the actual menu."""

        for inputObject in self.attributes.values():
            self.insertLayout(1, inputObject)

        if hasattr(self, "paramsLayout"):
            paramsOptions = QtWidgets.QHBoxLayout()
            paramsOptions.addSpacing(10)

            labelField = QtWidgets.QLabel("Parameters")
            paramsOptions.addWidget(labelField)

            paramsOptions.addStretch()

            paramTypeButton = QtWidgets.QPushButton("Change to single")
            paramTypeButton.clicked.connect(partial(self.toggleParamType, paramTypeButton))
            paramsOptions.addWidget(paramTypeButton)

            addButton = QtWidgets.QPushButton("Add")
            addButton.clicked.connect(self.addParam)
            paramsOptions.addWidget(addButton)

            self.paramsLayout.insertLayout(0, paramsOptions)
            self.addLayout(self.paramsLayout)

        # Add children options
        if functionField := self.attributes.get('function'):
            if functionField.valueWidget.currentText() == 'scriptedMenu':
                return

        for childType in CHILDREN.get(self.nodeType, []):
            options = self.createChildOptions(childType, self.childrenLayout)
            self.childrenLayout.insertLayout(0, options)

        for child in self.children:
            layout = offsetWrap(child, 15 if self.nodeType != NodeType.PIESLICE else 10)
            self.childrenLayout.addLayout(layout)
        self.addLayout(self.childrenLayout)


class ProfileNode(QtWidgets.QWidget, SettingsNode):
    """A variation of the SettingsNode, altered to contain profile related data."""

    def __init__(self, settingsMenu: SettingsMenu, objectData: dict):
        SettingsNode.__init__(self, NodeType.PROFILE, objectData)
        QtWidgets.QWidget.__init__(self)

        try:
            self.ahkHandle = objectData["ahkHandle"]
        except KeyError:
            print("Profile missing ahkHandle.")  # TODO: Make this more elegant.

        self.pieMenuBoxLayout, self.hotkeyBoxLayout = QtWidgets.QVBoxLayout(), QtWidgets.QVBoxLayout()
        self.scrollWidgetParent = None

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.setLayout(self.layout)

        self.createTopLevelOptions(settingsMenu, objectData["label"])
        self.createMenu()

        if self.json:
            self.setAttributesFromJSON()

    def setAttributesFromJSON(self):
        """Instantiates all attributes present in the JSON data of the object."""

        self.label.setText(self.json.get("label"))

        for label, data in self.json.items():
            if not data:
                continue

            if label in ("piemenus", "slices", "subslices", "hotkeys"):
                layout = self.pieMenuBoxLayout if CHILDTYPES[label.lower()] is NodeType.PIEMENU \
                    else self.hotkeyBoxLayout

                for child in data:
                    self.createChild(CHILDTYPES[label.lower()],
                                     objectData=child,
                                     layout=layout,
                                     spacing=25)

    def createTopLevelOptions(self, settingsMenu: SettingsMenu, initLabel: str):
        """Inserts the controls always needed for every nodetype. I.e. name/label field and 'remove self' button."""

        saveButton = QtWidgets.QPushButton("Save")
        saveButton.clicked.connect(partial(settingsMenu.settingsManager.saveJSONFile,
                                           settingsMenu,
                                           "settings/appProfiles.json"))
        self.layout.addWidget(saveButton)

        topOptions = QtWidgets.QHBoxLayout()

        self.label.setText(self.json.get("label", initLabel))
        topOptions.addWidget(self.label)

        if self.ahkHandle != "Default":
            removeButton = QtWidgets.QPushButton("Remove")
            removeButton.clicked.connect(partial(recursiveDeleteLater, self))
            topOptions.addWidget(removeButton)

        self.layout.addLayout(topOptions)

    def createMenu(self):  # TODO: Unfilled parameter warning on save.
        """Adds every layout to the node, finally (visually) creating the actual menu."""

        # Change attribute options
        for inputObject in self.attributes.values():
            self.layout.insertLayout(0, inputObject)

        # Add children options
        types = {NodeType.PIEMENU: self.pieMenuBoxLayout, NodeType.HOTKEY: self.hotkeyBoxLayout}
        for childType, layout in types.items():
            parentLayout = self.pieMenuBoxLayout if childType is NodeType.PIEMENU else self.hotkeyBoxLayout
            options = self.createChildOptions(childType, parentLayout)

            layout.addLayout(options)

            self.layout.addLayout(layout)


def getParent(obj: QtCore.QObject):
    """Goes up the 'line of parents' until it finds a parent of the custom created types."""

    while True:
        obj = obj.parent()
        for widgetType in [SettingsMenu, SettingsNode, ProfileNode]:
            if isinstance(obj, widgetType):
                return obj


def offsetWrap(obj: QtCore.QObject, spacing: int = None) -> QtWidgets.QLayout:
    """Creates a layout to offset the given widget."""

    hOffsetBox = QtWidgets.QHBoxLayout()
    hOffsetBox.addSpacing(15)
    hOffsetBox.addLayout(obj)

    if spacing:
        vOffsetBox = QtWidgets.QVBoxLayout()
        vOffsetBox.addLayout(hOffsetBox)
        vOffsetBox.addSpacing(spacing)

        return vOffsetBox
    return hOffsetBox


def removeFromParent(obj: QtCore.QObject):
    """Removes the given object from the parents layout and corresponding list (i.e. children, params,
    or attributes)."""

    for widgetType in [SettingsMenu, SettingsNode, ProfileNode, InputObject]:
        if not isinstance(obj, widgetType):
            continue

        parent = getParent(obj)

        if isinstance(parent, SettingsMenu):
            parent.removeTab(parent.indexOf(obj.scrollWidgetParent))
            parent.children.remove(obj)

            return

        if params := getattr(parent, "params", None):
            if obj in params:
                parent.params.remove(obj)
                return

        for label, child in parent.attributes.items():
            if child is obj:
                del parent.attributes[label]
                return
        parent.children.remove(obj)


def recursiveDeleteLater(obj: QtCore.QObject):
    """Removes self and all widgets contained in self."""

    removeFromParent(obj)

    if isinstance(obj, QtWidgets.QSpacerItem):
        return

    if isinstance(obj, QtWidgets.QWidgetItem):
        obj.wid.deleteLater()
        return

    if isinstance(obj, ProfileNode):
        return  # TODO: This fix doesn't remove the profile, if I understand it correctly. Results in useless object
        #         in memory (garbage collection?) . Fix this.

    for i in range(obj.count()):
        recursiveDeleteLater(obj.itemAt(i))
    obj.deleteLater()


def recursiveSendKeyEvents(obj: QtCore.QObject, event):
    # print(f'Sending keys to (children of) {type(obj)}.')

    if isinstance(obj, InputObject):
        if obj.inputType == InputType.KEYINPUT and obj.valueWidget.recording:
            print('\tSending keys to KeyInputField.')
            obj.valueWidget.keyPressEvent(event)
        return

    # children
    for child in getattr(obj, 'children', []):
        # print(f'\tSending keys to child: {type(child)}.')
        recursiveSendKeyEvents(child, event)

    for attribute in getattr(obj, 'attributes', {}).values():
        # print(f'\tSending keys to attr: {type(attribute)}.')
        recursiveSendKeyEvents(attribute, event)
