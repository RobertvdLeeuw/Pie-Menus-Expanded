import pieFunctions
from settings.menuScripts.menuScript import MenuOption
from settings.pie_themes import pie_themes, pie_selection_theme

import os
from queue import Queue
from time import sleep
from threading import Thread

import iconify
from PySide2 import QtGui, QtWidgets, QtCore


script_dir = os.path.dirname(__file__)
icons_dir = os.path.join(script_dir, "resources/icons/")
transparent = QtGui.QColor(255, 255, 255, 0)


def getWidgetCenterPos(widget):
    if not widget:
        return None

    return QtCore.QPoint(widget.rect().width() / 2, widget.rect().height() / 2)


def isChild(button, parent) -> bool:
    if not parent or not button:
        return False

    return button in getButtons(parent)


def getTargetingLine(line: QtCore.QLineF, point: QtCore.QPoint) -> QtCore.QLineF:
    if not line.length():
        line = QtCore.QLineF(line.p1(), point)
        return line

    # What?
    diff = (((point.x() - line.p1().x()) * (line.p2().x() - line.p1().x())) +
            ((point.y() - line.p1().y()) * (line.p2().y() - line.p1().y()))) / (line.length() ** 2)

    if diff < 0:
        newPoint = line.p1()
    elif diff > 1:
        newPoint = line.p2()
    else:
        newPoint = QtCore.QPoint(line.p1().x() + diff * (line.p2().x() - line.p1().x()),
                                 line.p1().y() + diff * (line.p2().y() - line.p1().y()))

    line = QtCore.QLineF(point, newPoint)
    return line


def getButtons(button, checkIfChildrenActive=False):
    if not isinstance(button, Button) or not button.subMenu or not button.subMenu.buttons:
        return []

    if checkIfChildrenActive and not button.subMenu.buttons[0].isVisible():
        return []

    return button.subMenu.buttons


class Window(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.menu = None

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.showMaximized()

    def showMenu(self, openPieMenu, summonPosition, globalSettings):
        if self.menu:
            self.menu.kill()
            return

        self.menu = RadialMenu(self, summonPosition, openPieMenu, globalSettings)
        self.menu.show()

    def killMenu(self):
        if self.menu:
            self.menu.kill()
            return

    def mousePressEvent(self, event):
        # this is automatically called when a mouse key press event occurs
        # this acts as right click to cancel pie menu
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            if self.menu:
                self.menu.kill()
                return

    def launchByTrigger(self, counter):
        if self.menu is None:
            return
        getButtons(self.menu)[counter].animateClick()
        self.killMenu()

    def releasedHeldKey(self):
        if self.menu is None:
            return
        self.menu.ioHandler.launchByKeyRelease()
        self.killMenu()

    def llWheelEvent(self, event):
        if self.menu is None:
            return
        self.menu.llWheelEvent(event)


class SubMenu:
    def __init__(self, parentButton):
        self.parentButton = parentButton
        self.radialMenu = parentButton.parent()

        self.buttons = []
        self.open = False

        self.createSubMenu()

    def createSubMenu(self):
        for subSlice in self.parentButton.slice.get("subslices"):
            if "menuScript" in subSlice and subSlice["menuScript"]:
                continue

            button = self.radialMenu.menuBuilder.buildButton(subSlice)
            button.hide()

            self.buttons.append(button)

    def updateSubMenuButtons(self, parentAngle: float):
        for index, button in enumerate(self.buttons):
            maxAngle = 180  # TODO: Fix this (try other values).

            offsetAngle = ((maxAngle / (len(self.buttons) + 1)) * (index + 1)) + (maxAngle / 2)
            buttonAngle = (offsetAngle + parentAngle) % 360

            distance = 160

            try:
                line = QtCore.QLineF(self.parentButton.pos(),
                                     self.parentButton.pos() + QtCore.QPoint(0, distance))
                line.setAngle(buttonAngle)
            except RuntimeError:
                return  # Occurs when menu is closed before timer is done.

            button.show()
            button.move(line.p2().toPoint().x(), line.p2().toPoint().y())

    def checkButtonHoverHeld(self, parentAngle: float):
        initialButton = self.radialMenu.selectedButton

        otherSelected = False
        for _ in range(5):
            sleep(0.05)

            try:
                if self.radialMenu.selectedButton != initialButton:
                    otherSelected = True
            except RuntimeError:
                return  # Occurs when menu is closed before timer is done.

        if not otherSelected:
            self.open = True

            self.updateSubMenuButtons(parentAngle)

    def showSubMenu(self, parentAngle: float):
        Thread(target=self.checkButtonHoverHeld, args=(parentAngle,)).start()

    def hideSubMenu(self):
        self.open = False

        [button.hide() for button in self.buttons]


class Button(QtWidgets.QPushButton):
    def __init__(self, openPieMenu: dict, slice: dict, globalSettings: dict, parent=None):
        pie_label = slice["label"]
        # if globalSettings["showTKeyHint"] and slice["triggerKey"] != "None":
        if slice.get("triggerKey"):
            pie_label += ' ' * 2 + f'( {slice["triggerKey"]} )'

        super().__init__(pie_label, parent=parent)

        self.slice: dict = slice
        self.subMenu = SubMenu(self) if slice.get('subslices') else None

        self.setMouseTracking(True)
        self.isHovered = False
        self.isPressed = False
        self.actuallyHovered = False
        self.targetPos = self.pos()
        self.icon = None
        self.svg_changes_color = False

        if slice.get("icon"):
            self.findIcon(globalSettings, openPieMenu)

        self.setStyleSheet(pie_themes.get(openPieMenu.get("theme"), pie_themes.dhalu_theme))

        if self.slice.get("onPie_w_up") or self.slice.get("onPie_w_down"):
            self.wheelEvent = self.optionalWheelEvent

        self.pressed.connect(self.runPieFunction)

        self.opacityEffect = QtWidgets.QGraphicsOpacityEffect(self, opacity=1.0)
        self.setGraphicsEffect(self.opacityEffect)

        self.parallelAnim = None
        self.posAnim = None
        self.opacityAnim = None

    def findIcon(self, globalSettings, openPieMenu):
        icon = os.path.join(icons_dir, self.slice.get("icon").strip())
        if not os.path.exists(icon):
            icon = os.path.join(icons_dir, "default.svg")

        self.setText(globalSettings.get("icon-padding-right") + self.text())
        if self.slice.get("icon").strip()[-4:] == ".svg":
            try:  # TODO: See if this can be transformed into if statement, else check error type.
                svg_nohover_hover = pie_selection_theme.get(openPieMenu.get("theme")).get("svg_nohover_hover")
                nohover_col, hover_col = svg_nohover_hover.strip().split("_")
                self.nohover_icon = iconify.Icon(icon, color=QtGui.QColor(nohover_col))
                self.hover_icon = iconify.Icon(icon, color=QtGui.QColor(hover_col))
                self.svg_changes_color = True
                icon = self.nohover_icon
            except:
                icon = iconify.Icon(icon)

        self.icon = icon
        self.setIcon(QtGui.QIcon(icon))

    def setHover(self, newHoverState):
        if self.svg_changes_color:
            self.setIcon(self.nohover_icon if newHoverState else self.hover_icon)

        if self.isHovered == newHoverState:
            return

        self.isHovered = newHoverState
        self.setProperty("hover", newHoverState)

        self.style().unpolish(self)
        self.style().polish(self)

        if not self.subMenu:  # TODO: Left off here. SubMenu doesn't always get registered.
            return

        if newHoverState and not self.subMenu.open:
            line = QtCore.QLineF(self.targetPos, self.parent().summonPos)

            queue = Queue()
            thread = Thread(target=lambda f, a: queue.put(f(a)),
                            args=(self.subMenu.showSubMenu, line.angle()))
            thread.start()
            thread.join()
        elif not newHoverState and self.subMenu.open:
            self.subMenu.hideSubMenu()

    def setPress(self, value):
        if self.isPressed != value:
            self.isPressed = value
            self.setProperty("pressed", value)
            self.style().unpolish(self)
            self.style().polish(self)

    def animate(self, startPos, endPos, start=True, duration=200):
        self.parallelAnim = QtCore.QParallelAnimationGroup()

        self.posAnim = QtCore.QPropertyAnimation(self, b"pos")
        self.posAnim.setStartValue(startPos)
        self.posAnim.setEndValue(endPos)
        self.posAnim.setDuration(duration)
        self.posAnim.setEasingCurve(QtCore.QEasingCurve.InSine)
        self.posAnim.setEasingCurve(QtCore.QEasingCurve.OutQuad)

        self.opacityAnim = QtCore.QPropertyAnimation(self.opacityEffect, b"opacity")
        self.opacityAnim.setStartValue(0)
        self.opacityAnim.setEndValue(1)
        self.opacityAnim.setDuration(duration)

        self.parallelAnim.addAnimation(self.posAnim)
        self.parallelAnim.addAnimation(self.opacityAnim)
        if start:
            self.parallelAnim.start()

        return [self.posAnim, self.opacityAnim]

    def enterEvent(self, event) -> None:
        self.actuallyHovered = True

    def leaveEvent(self, event) -> None:
        self.actuallyHovered = False

    def isActuallyHovered(self):  # Mouse on button.
        return self.actuallyHovered

    def optionalWheelEvent(self, event=False, custom_event=None):
        if custom_event:
            event = custom_event
            # Custom wheel events here.
            if event.scan_code == 7864320 and self.slice.get("w_up"):
                # Scroll up(7864320), away from the user
                self.runPieFunction(wheel=self.slice.get("w_up"))
            elif event.scan_code == 4287102976 and self.slice.get("w_down"):
                # Scroll down(4287102976), towards user
                self.runPieFunction(wheel=self.slice.get("w_down"))
            return None

        # Default wheel event
        if event.angleDelta().y() > 0 and self.slice.get("onPie_w_up"):
            # Scroll up, away from the user
            self.runPieFunction(wheel=self.slice.get("onPie_w_up"))

        elif event.angleDelta().y() < 0 and self.slice.get("onPie_w_down"):
            # Scroll down, towards user
            self.runPieFunction(wheel=self.slice.get("onPie_w_down"))

        return super().wheelEvent(event)

    def runPieFunction(self, wheel=False):
        pie_func, params = wheel if wheel else self.slice["function"], self.slice["params"]

        if pie_func.lower() == "none" or not pie_func:
            return

        if pie_func not in pieFunctions.FUNCTIONS:
            print(f"Invalid button function: {pie_func}")

        pieFunctions.FUNCTIONS[pie_func](params)


class MenuBuilder:
    def __init__(self, radialMenu):
        self.radialMenu = radialMenu

    def buildMenu(self) -> list[Button]:
        slices = self.radialMenu.openPieMenu.get("slices")

        if not slices:
            print("No slices created for pie menu.")  # TODO: Fancify.
            return []

        if self.radialMenu.openPieMenu.get("offset_slices"):
            slices = slices[-1 * self.radialMenu.openPieMenu.get("offset_slices", 0):] \
                     + slices[: -1 * self.radialMenu.openPieMenu.get("offset_slices")]

        buttons = []

        for slice in slices:
            if slice.get("function") == 'scriptedMenu':
                buttons.extend(self.generateSSGButtons(slice))
            else:
                buttons.append(self.buildButton(slice))

        return buttons

    def generateSSGButtons(self, ssgData: dict) -> list[Button]:
        menuOptions = pieFunctions.scriptedMenu(ssgData['params'])

        if not menuOptions:
            pass  # TODO: Pop-up if empty.

        return [self.buildButton(menuOption.toDict()) for menuOption in menuOptions]

    def buildButton(self, data: dict) -> Button:
        """Creates the buttons, one for each slice of the pieMenu, and their potential children."""

        button = Button(self.radialMenu.openPieMenu,
                        data,
                        self.radialMenu.globalSettings,
                        parent=self.radialMenu)

        return button


class MenuPresenter:
    def __init__(self, radialMenu):
        self.radialMenu = radialMenu

        self._inRadius, self._outRadius = 15, 115

        self._selectedBtnParent = None
        self._selectedBtnParentInitPos = None
        self._selectedBtnInitPos = None
        self._prevSelectedBtn = None
        self.animGroup = None

    def setButtonPositions(self):
        offset_angle = -self.radialMenu.openPieMenu.get("offset_angle", 0)
        angle = 360 / len(self.radialMenu.buttons)
        line = QtCore.QLineF(self.radialMenu.summonPos,
                             self.radialMenu.summonPos - QtCore.QPoint(0, self._outRadius))

        for counter, button in enumerate(self.radialMenu.buttons):
            line.setAngle(line.angle() + (angle if counter else 0) + offset_angle)

            diff = line.p2() - self.radialMenu.summonPos
            pos = getWidgetCenterPos(button)
            if abs(diff.x()) < 3:
                pass
            elif line.p2().x() < self.radialMenu.summonPos.x():
                pos.setX(button.rect().width())
            else:
                pos.setX(button.rect().x())

            if abs(diff.y()) < 3:
                pass
            elif line.p2().y() < self.radialMenu.summonPos.y():
                if round(line.angle() % 90) == 0:
                    pos.setY(button.rect().height())
            else:
                if round(line.angle() % 90) == 0:
                    pos.setY(button.rect().y())

            button.move(line.p2().toPoint() - pos)
            button.targetPos = line.p2().toPoint()

    def fixSummonPosition(self, pos):  # TODO: What does this do?
        minSpaceToBorder = int(self.radialMenu.globalSettings["savePadding"]) + self._outRadius
        maxX = self.radialMenu.rect().width() - minSpaceToBorder
        maxY = self.radialMenu.rect().height() - minSpaceToBorder

        angle = 360 / len(self.radialMenu.buttons)
        line = QtCore.QLineF(self.radialMenu.summonPos,
                             self.radialMenu.summonPos - QtCore.QPoint(0, self._outRadius))
        offset_angle = -self.radialMenu.openPieMenu.get("offset_angle", 0)

        _minX = _minY = _maxX = _maxY = self.radialMenu.buttons[0]

        # Guess the button position
        for i, button in enumerate(self.radialMenu.buttons):
            line.setAngle(line.angle() + (angle if i else 0) + offset_angle)

            if not 89 < line.angle() < 271:
                if _maxX.pos().x() + _maxX.width() < button.pos().x() + button.width():
                    _maxX = button
            elif 91 < line.angle() < 269:
                if _minX.width() < button.width():
                    _minX = button

            if _minY.pos().y() > button.pos().y():
                _minY = button
            if _maxY.pos().y() + _maxY.height() < button.pos().y() + button.height():
                _maxY = button

        minX = minSpaceToBorder + _minX.width()
        minY = minSpaceToBorder + _minY.height()
        maxX = maxX - _maxX.width()
        maxY = maxY - _maxY.height()

        pos.setX(min(max(pos.x(), minX), maxX))
        pos.setY(min(max(pos.y(), minY), maxY))

        return pos

    def getHoverPosition(self, button, lineFirstPoint=None):
        if button.isHovered:  # If already actuallyHovered out, return the buttons initial position.
            initPos = self._selectedBtnParentInitPos if button is self._selectedBtnParent else self._selectedBtnInitPos

            return initPos
        initPos = button.pos()

        selectionMovement = 1.75 if button.subMenu else 1.5

        line = QtCore.QLineF(lineFirstPoint if lineFirstPoint else self.radialMenu.summonPos,
                             initPos + getWidgetCenterPos(button))
        line.setLength(line.length() * selectionMovement)

        newPos = line.p2() - getWidgetCenterPos(button)
        return QtCore.QPoint(newPos.x(), newPos.y())

    def checkMouseInCircle(self):
        return (self.radialMenu.currentMousePos.x() - self.radialMenu.summonPos.x()) ** 2 + (
                self.radialMenu.currentMousePos.y() - self.radialMenu.summonPos.y()) ** 2 < self._inRadius ** 2

    def resetPrevSelectedButtonPos(self, targetBtn):
        if not self.radialMenu.selectedButton:
            return

        # Unless the previous selected button is the parent of new the target button...
        if not self._selectedBtnParent and isChild(targetBtn, self.radialMenu.selectedButton):
            self._selectedBtnParent = self.radialMenu.selectedButton
            self._selectedBtnParentInitPos = self._selectedBtnInitPos
            # ...or new selection out of subMenu...
        elif self._selectedBtnParent and self._selectedBtnParent != targetBtn \
                and not isChild(targetBtn, self._selectedBtnParent):
            self._selectedBtnParent.move(self._selectedBtnParentInitPos)
            self._selectedBtnParent = None
            self._selectedBtnParentInitPos = None
            # ...move back old button.
        else:
            self.radialMenu.selectedButton.move(self._selectedBtnInitPos.x(),
                                                self._selectedBtnInitPos.y())

    def updateSelectedButton(self, targetButton):
        if self.radialMenu.selectedButton is targetButton or self.checkMouseInCircle():
            return

        self.resetPrevSelectedButtonPos(targetButton)

        self._prevSelectedBtn, self.radialMenu.selectedButton = self.radialMenu.selectedButton, targetButton
        self._selectedBtnInitPos = self.radialMenu.selectedButton.pos()

        # Move button to hover position.
        if not isChild(self._prevSelectedBtn,
                       self.radialMenu.selectedButton) and not self.radialMenu.selectedButton.isHovered:
            # Different direction for subButtons
            newPos = self.getHoverPosition(self.radialMenu.selectedButton, None if not self._selectedBtnParent else
            self._selectedBtnParent.pos() + getWidgetCenterPos(self._selectedBtnParent))

            self.radialMenu.selectedButton.move(newPos)

        self.radialMenu.selectedButton.setHover(True)
        self.radialMenu.selectedButton.setPress(self.radialMenu.ioHandler.mousePressed)

        # Unhover all other
        for button in self.radialMenu.buttons + getButtons(self.radialMenu.selectedButton) + getButtons(
                self._selectedBtnParent):
            if isChild(self.radialMenu.selectedButton, button):  # Except parent
                continue

            button.setHover(button is self.radialMenu.selectedButton)

    def getTheme(self) -> tuple[QtGui.QPen, QtGui.QPen]:
        if "theme" in self.radialMenu.openPieMenu and self.radialMenu.openPieMenu["theme"].lower() not in (
                "", "none", "null"):
            theme = pie_selection_theme[self.radialMenu.openPieMenu["theme"]]
            bgCirclePen = QtGui.QPen(QtGui.QColor(theme["bg_circle"]),
                                     theme["thickness"])
            fgCirclePen = QtGui.QPen(QtGui.QColor(theme["fg_circle"]),
                                     theme["thickness"])
        else:
            bgCirclePen = QtGui.QPen(QtGui.QColor(pie_selection_theme.default["bg_circle"]),
                                     pie_selection_theme.default["thickness"])
            fgCirclePen = QtGui.QPen(QtGui.QColor(pie_selection_theme.default["fg_circle"]),
                                     pie_selection_theme.default["thickness"])

        return bgCirclePen, fgCirclePen

    def debugDraw(self, painter: QtGui.QPainter):
        painter.setBrush(transparent)
        painter.setPen(QtCore.Qt.blue)

        painter.drawEllipse(self.radialMenu.summonPos, self._outRadius, self._outRadius)
        painter.drawLine(self.radialMenu.summonPos, self.radialMenu.currentMousePos)

        for button in self.radialMenu.buttons:
            painter.drawLine(self.radialMenu.summonPos, button.pos() + getWidgetCenterPos(button))

        painter.setPen(QtGui.QPen(QtCore.Qt.yellow, 5))
        for button in self.radialMenu.buttons + getButtons(self.radialMenu.selectedButton) + getButtons(
                self._selectedBtnParent):
            hoverLine = QtCore.QLineF(button.pos() + getWidgetCenterPos(button),
                                      self.getHoverPosition(button) + getWidgetCenterPos(button))
            painter.drawLine(hoverLine)

    def paintEvent(self):
        angle = 1  # TODO: Figure out what this should be.
        circleRect = QtCore.QRect(self.radialMenu.summonPos.x() - self._inRadius,
                                  self.radialMenu.summonPos.y() - self._inRadius,
                                  self._inRadius * 2, self._inRadius * 2)  # The rect of the center circle
        arcSize = 36

        bgCirclePen, fgCirclePen = self.getTheme()

        painter = QtGui.QPainter(self.radialMenu)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, on=True)
        # highqualityantialising is obsolete value now and is ignored
        # refer to this -> https://doc.qt.io/qtforpython-5/PySide2/QtGui/QPainter.html

        for button in self.radialMenu.buttons:
            button.setPress(False)

        # Draw Background circle
        painter.setPen(bgCirclePen)
        painter.drawEllipse(circleRect)

        # Draw Foreground circle
        if angle and not self.checkMouseInCircle():
            painter.setPen(fgCirclePen)
            if self.radialMenu.globalSettings["useArcOnHover"]:
                painter.drawArc(circleRect, int(angle - arcSize / 2) * 16, arcSize * 16)
            if self.radialMenu.globalSettings["useLineOnHover"]:
                # tracking line
                fgCirclePen.setCapStyle(QtGui.Qt.RoundCap)
                painter.setPen(fgCirclePen)
                painter.drawLine(self.radialMenu.summonPos, self.radialMenu.currentMousePos)
                print(self.radialMenu.summonPos, self.radialMenu.currentMousePos)

        self.debugDraw(painter)

    def findSelectedButton(self):
        targetBtn = self.radialMenu.buttons[0]
        targetBtnDist = QtCore.QLineF(self.radialMenu.currentMousePos, targetBtn.pos()).length()

        for button in self.radialMenu.buttons + getButtons(self.radialMenu.selectedButton, True) + getButtons(
                self._selectedBtnParent):
            buttonHoverLine = QtCore.QLineF(button.pos() + getWidgetCenterPos(button),
                                            self.getHoverPosition(button) + getWidgetCenterPos(button))
            buttonDist = getTargetingLine(buttonHoverLine, self.radialMenu.currentMousePos).length()

            if buttonDist < targetBtnDist:
                targetBtn = button
                targetBtnDist = buttonDist

        return targetBtn


class IOHandler:
    def __init__(self, radialMenu):
        self.radialMenu = radialMenu

        self.mousePressed = False

        self.globalMouseTimer = QtCore.QTimer()
        self.globalMouseTimer.timeout.connect(self.globalMouseMoveEvent)
        self.globalMouseTimer.start(5)

    def globalMouseMoveEvent(self):
        last_pos = self.radialMenu.currentMousePos
        self.radialMenu.currentMousePos = self.radialMenu.parent().mapFromGlobal(QtGui.QCursor.pos())

        if last_pos == self.radialMenu.currentMousePos:
            return

        self.radialMenu.menuPresenter.updateSelectedButton(self.radialMenu.menuPresenter.findSelectedButton())
        self.radialMenu.update()

    # Keep the following enabled, although no mouse events will happen
    # as there is not any window shown, but just in case, if something fails,
    # and window receives some event, these will trigger up and do the same functionality
    # instead to blocking program or crashing, or missing user action. makes it less error prone.
    # covering all grounds just to be safe.
    def mousePressEvent(self, event):
        self.radialMenu.super().mousePressEvent(event)
        if self.radialMenu.selectedButton:
            self.mousePressed = True

    def mouseReleaseEvent(self, event):
        self.radialMenu.super().mouseReleaseEvent(event)
        if self.radialMenu.selectedButton:
            self.radialMenu.selectedButton.click()
        self.radialMenu.menuPresenter.kill()

    def llWheelEvent(self, event):
        for button in self.radialMenu.buttons:
            if button.isHovered:
                if button.slice.get("w_up") or button.slice.get("w_down"):
                    if not button.isActuallyHovered():
                        button.optionalWheelEvent(custom_event=event)
                    elif button.isActuallyHovered() and button.slice.get("onPie_w_up") is None and button.slice.get(
                            "onPie_w_down") is None:
                        button.optionalWheelEvent(custom_event=event)
                break

    def launchByKeyRelease(self):
        if not self.radialMenu.selectedButton:
            return

        self.radialMenu.selectedButton.animateClick()


class RadialMenu(QtWidgets.QWidget):
    def __init__(self, parent: Window, summonPosition, openPieMenu: dict, globalSettings: dict):
        super().__init__(parent=parent)

        self.summonPos = self.parent().mapFromGlobal(summonPosition)
        self.currentMousePos = QtCore.QPoint(self.summonPos)

        self.openPieMenu = openPieMenu
        self.globalSettings = globalSettings

        self.menuBuilder = MenuBuilder(self)
        self.menuPresenter = MenuPresenter(self)

        self.buttons = self.menuBuilder.buildMenu()
        self.selectedButton = None

        self.ioHandler = IOHandler(self)

        self.setMouseTracking(True)
        self.setGeometry(self.parent().rect())

    def kill(self):
        self.menuPresenter.animGroup.setDirection(QtCore.QAbstractAnimation.Backward)
        self.menuPresenter.animGroup.finished.connect(self.hide)
        self.menuPresenter.animGroup.start()

        self.parent().menu = None

        for button in self.buttons:
            button.deleteLater()

        self.deleteLater()

        del self.menuBuilder
        del self.menuPresenter
        del self.ioHandler

        del self

    def show(self):
        super().show()

        self.summonPos = self.menuPresenter.fixSummonPosition(self.summonPos)
        self.currentMousePos = QtCore.QPoint(self.summonPos)
        self.menuPresenter.setButtonPositions()

        self.menuPresenter.animGroup = QtCore.QParallelAnimationGroup()
        for button in self.buttons:
            anims = button.animate(self.summonPos - getWidgetCenterPos(button), button.pos(), False, 70)
            self.menuPresenter.animGroup.addAnimation(anims[1])

        self.menuPresenter.animGroup.start()
