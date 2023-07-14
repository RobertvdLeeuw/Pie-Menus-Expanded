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
    if not isinstance(button, Button) or not button.subMenu or not button.btnList:
        return []

    if checkIfChildrenActive and not button.btnList[0].isVisible():
        return []

    return button.btnList


class Window(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.menu = None

        # following line for window less app
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)

        # following line for transparent background
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
        self.menu.launchByKeyRelease()
        self.killMenu()

    def llWheelEvent(self, event):
        if self.menu is None:
            return
        self.menu.llWheelEvent(event)

    def isMenuOpen(self):
        return self.menu


class RadialMenu(QtWidgets.QWidget):
    def __init__(self, parent, summonPosition, openPieMenu, globalSettings):
        super().__init__(parent=parent)
        self.setMouseTracking(True)
        self.globalSettings = globalSettings
        self.setGeometry(self.parent().rect())
        self._inRadius, self._outRadius = 15, 115
        self._btnList = []
        self._selectedBtn = None
        self._selectedBtnParent = None
        self._selectedBtnParentInitPos = None
        self._selectedBtnInitPos = None
        self._prevSelectedBtn = None
        self._mousePressed = False
        self.animGroup = None

        self.openPieMenu = openPieMenu

        self._summonPosition = self.parent().mapFromGlobal(summonPosition)
        self._currentMousePos = QtCore.QPoint(self._summonPosition)

        self.globalMouseTimer = QtCore.QTimer()
        self.globalMouseTimer.timeout.connect(self.globalMouseMoveEvent)
        self.globalMouseTimer.start(5)

        slices = openPieMenu.get("slices")

        if not slices:
            print("No slices created for pie menu.")  # TODO: Fancify.
            return

        slices = slices[: int(len(slices))]
        if openPieMenu.get("offset_slices"):
            slices = slices[-1 * openPieMenu.get("offset_slices", 0):] + slices[: -1 * openPieMenu.get("offset_slices")]

        for slice in slices:
            self.generateSSGButtons(slice) if slice.get("function") == 'scriptedMenu' else self.addButton(slice)

    def generateSSGButtons(self, ssgData: dict):
        menuOptions = pieFunctions.scriptedMenu(ssgData['params'])

        for menuOption in menuOptions:  # TODO: Pop-up if empty.
            print(f'\tMO: {menuOption.toDict()}')
            self.addButton(menuOption.toDict())

    def addButton(self, slice: dict):
        """Creates the buttons, one for each slice of the pieMenu, and their potential children."""

        btn = Button(self.openPieMenu,
                     slice,
                     self.globalSettings,
                     parent=self)
        self._btnList.append(btn)

        if btn.subMenu:
            btn.createSubMenu(self.globalSettings, self.openPieMenu)

    def kill(self):
        self.animGroup.setDirection(QtCore.QAbstractAnimation.Backward)
        self.animGroup.finished.connect(self.hide)
        self.animGroup.start()
        self.parent().menu = None
        for btn in self._btnList:
            btn.deleteLater()

        self.deleteLater()
        del self

    def show(self):
        super().show()

        self._summonPosition = self.fixSummonPosition(self._summonPosition)
        self._currentMousePos = QtCore.QPoint(self._summonPosition)
        self.setButtonPositions()

        self.animGroup = QtCore.QParallelAnimationGroup()
        for btn in self._btnList:
            anims = btn.animate(self._summonPosition - getWidgetCenterPos(btn), btn.pos(), False, 70)
            self.animGroup.addAnimation(anims[1])

        self.animGroup.start()

    def setButtonPositions(self):
        offset_angle = -self.openPieMenu.get("offset_angle", 0)
        angle = 360 / len(self._btnList)
        line = QtCore.QLineF(self._summonPosition, self._summonPosition - QtCore.QPoint(0, self._outRadius))

        for counter, btn in enumerate(self._btnList):
            line.setAngle(line.angle() + (angle if counter else 0) + offset_angle)

            diff = line.p2() - self._summonPosition
            pos = getWidgetCenterPos(btn)
            if abs(diff.x()) < 3:
                pass
            elif line.p2().x() < self._summonPosition.x():
                pos.setX(btn.rect().width())
            else:
                pos.setX(btn.rect().x())

            if abs(diff.y()) < 3:
                pass
            elif line.p2().y() < self._summonPosition.y():
                if round(line.angle() % 90) == 0:
                    pos.setY(btn.rect().height())
            else:
                if round(line.angle() % 90) == 0:
                    pos.setY(btn.rect().y())

            btn.move(line.p2().toPoint() - pos)
            btn.targetPos = line.p2().toPoint()

    def fixSummonPosition(self, pos):  # What does this do?
        minSpaceToBorder = int(self.globalSettings["savePadding"]) + self._outRadius
        maxX = self.rect().width() - minSpaceToBorder
        maxY = self.rect().height() - minSpaceToBorder

        angle = 360 / len(self._btnList)
        line = QtCore.QLineF(self._summonPosition, self._summonPosition - QtCore.QPoint(0, self._outRadius))
        offset_angle = -self.openPieMenu.get("offset_angle", 0)

        _minX = _minY = _maxX = _maxY = self._btnList[0]

        # Guess the button position
        for i, btn in enumerate(self._btnList):
            line.setAngle(line.angle() + (angle if i else 0) + offset_angle)

            if not 89 < line.angle() < 271:
                if _maxX.pos().x() + _maxX.width() < btn.pos().x() + btn.width():
                    _maxX = btn
            elif 91 < line.angle() < 269:
                if _minX.width() < btn.width():
                    _minX = btn

            if _minY.pos().y() > btn.pos().y():
                _minY = btn
            if _maxY.pos().y() + _maxY.height() < btn.pos().y() + btn.height():
                _maxY = btn

        minX = minSpaceToBorder + _minX.width()
        minY = minSpaceToBorder + _minY.height()
        maxX = maxX - _maxX.width()
        maxY = maxY - _maxY.height()

        pos.setX(min(max(pos.x(), minX), maxX))
        pos.setY(min(max(pos.y(), minY), maxY))

        return pos

    def globalMouseMoveEvent(self):
        last_pos = self._currentMousePos
        self._currentMousePos = self.parent().mapFromGlobal(QtGui.QCursor.pos())
        if last_pos == self._currentMousePos:
            return

        self.updateSelectedButton(self.findSelectedButton())
        self.update()

    # Keep the following enabled, although no mouse events will happen
    # as there is not any window shown, but just in case, if something fails,
    # and window receives some event, these will trigger up and do the same functionality
    # instead to blocking program or crashing, or missing user action. makes it less error prone.
    # covering all grounds just to be safe.
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._selectedBtn:
            self._mousePressed = True

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._selectedBtn:
            self._selectedBtn.click()
        self.kill()

    def getSelectedButton(self):
        return self._selectedBtn

    def getPosition(self):
        return self._summonPosition

    def findSelectedButton(self):
        targetBtn = self._btnList[0]

        targetBtnDist = QtCore.QLineF(self._currentMousePos, targetBtn.pos()).length()

        for btn in self._btnList + getButtons(self._selectedBtn, True) + getButtons(self._selectedBtnParent):
            btnHoverLine = QtCore.QLineF(btn.pos() + getWidgetCenterPos(btn),
                                         self.getHoverPosition(btn) + getWidgetCenterPos(btn))
            btnDist = getTargetingLine(btnHoverLine, self._currentMousePos).length()

            if btnDist < targetBtnDist:
                targetBtn = btn
                targetBtnDist = btnDist
        return targetBtn

    def getHoverPosition(self, btn, lineFirstPoint=None):
        if btn.isHovered():  # If already hovered out, return the buttons initial position.
            initPos = self._selectedBtnParentInitPos if btn is self._selectedBtnParent else self._selectedBtnInitPos

            return initPos
        initPos = btn.pos()

        selectionMovement = 1.75 if btn.subMenu else 1.5

        line = QtCore.QLineF(lineFirstPoint if lineFirstPoint else self._summonPosition,
                             initPos + getWidgetCenterPos(btn))
        line.setLength(line.length() * selectionMovement)

        newPos = line.p2() - getWidgetCenterPos(btn)
        return QtCore.QPoint(newPos.x(), newPos.y())

    def checkMouseInCircle(self):
        return (self._currentMousePos.x() - self._summonPosition.x()) ** 2 + \
               (self._currentMousePos.y() - self._summonPosition.y()) ** 2 < self._inRadius ** 2

    def resetPrevSelectedButtonPos(self, targetBtn):
        if not self._selectedBtn:
            return

        # Unless the previous selected button is the parent of new the target button...
        if not self._selectedBtnParent and isChild(targetBtn, self._selectedBtn):
            self._selectedBtnParent = self._selectedBtn
            self._selectedBtnParentInitPos = self._selectedBtnInitPos
            # ...or new selection out of subMenu...
        elif self._selectedBtnParent and self._selectedBtnParent != targetBtn \
                and not isChild(targetBtn, self._selectedBtnParent):
            self._selectedBtnParent.move(self._selectedBtnParentInitPos)
            self._selectedBtnParent = None
            self._selectedBtnParentInitPos = None
            # ...move back old button.
        else:
            self._selectedBtn.move(self._selectedBtnInitPos.x(),
                                   self._selectedBtnInitPos.y())

    def updateSelectedButton(self, targetBtn):
        if self._selectedBtn is targetBtn or self.checkMouseInCircle():
            return

        self.resetPrevSelectedButtonPos(targetBtn)

        self._prevSelectedBtn, self._selectedBtn = self._selectedBtn, targetBtn
        self._selectedBtnInitPos = self._selectedBtn.pos()

        # Move button to hover position.
        if not isChild(self._prevSelectedBtn, self._selectedBtn) and not self._selectedBtn.isHovered():
            # Different direction for subButtons
            newPos = self.getHoverPosition(self._selectedBtn, None if not self._selectedBtnParent else
            self._selectedBtnParent.pos() + getWidgetCenterPos(self._selectedBtnParent))

            self._selectedBtn.move(newPos)

        self._selectedBtn.setHover(True)
        self._selectedBtn.setPress(self._mousePressed)

        # Unhover all other
        for btn in self._btnList + getButtons(self._selectedBtn) + getButtons(
                self._selectedBtnParent):
            if isChild(self._selectedBtn, btn):  # Except parent
                continue

            btn.setHover(btn is self._selectedBtn)

    def getTheme(self) -> tuple[QtGui.QPen, QtGui.QPen]:
        if "theme" in self.openPieMenu and self.openPieMenu["theme"].lower() not in ("", "none", "null"):
            theme = pie_selection_theme[self.openPieMenu["theme"]]
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

        painter.drawEllipse(self._summonPosition, self._outRadius, self._outRadius)
        painter.drawLine(self._summonPosition, self._currentMousePos)

        for btn in self._btnList:
            painter.drawLine(self._summonPosition, btn.pos() + getWidgetCenterPos(btn))

        painter.setPen(QtGui.QPen(QtCore.Qt.yellow, 5))
        for btn in self._btnList + getButtons(self._selectedBtn) + getButtons(self._selectedBtnParent):
            hoverLine = QtCore.QLineF(btn.pos() + getWidgetCenterPos(btn),
                                      self.getHoverPosition(btn) + getWidgetCenterPos(btn))
            painter.drawLine(hoverLine)

    def paintEvent(self, event):
        angle = None
        circleRect = QtCore.QRect(self._summonPosition.x() - self._inRadius, self._summonPosition.y() - self._inRadius,
                                  self._inRadius * 2, self._inRadius * 2)  # The rect of the center circle
        arcSize = 36

        bgCirclePen, fgCirclePen = self.getTheme()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, on=True)
        # highqualityantialising is obsolete value now and is ignored
        # refer to this -> https://doc.qt.io/qtforpython-5/PySide2/QtGui/QPainter.html

        for btn in self._btnList:
            btn.setPress(False)

        # Draw Background circle
        painter.setPen(bgCirclePen)
        painter.drawEllipse(circleRect)

        # Draw Foreground circle
        if angle and not self.checkMouseInCircle():
            painter.setPen(fgCirclePen)
            if self.globalSettings["useArcOnHover"]:
                painter.drawArc(circleRect, int(angle - arcSize / 2) * 16, arcSize * 16)
            if self.globalSettings["useLineOnHover"]:
                # tracking line
                fgCirclePen.setCapStyle(QtGui.Qt.RoundCap)
                painter.setPen(fgCirclePen)
                painter.drawLine(self._summonPosition, self._currentMousePos)

        # self.debugDraw(painter)

    def launchByKeyRelease(self):
        if not self._selectedBtn:
            return

        self._selectedBtn.animateClick()

    def llWheelEvent(self, event):
        for btn in self._btnList:
            if btn.isHovered():
                if btn.slice.get("w_up") or btn.slice.get("w_down"):
                    if not btn.isActuallyHovered():
                        btn.optionalWheelEvent(custom_event=event)
                    elif btn.isActuallyHovered() and btn.slice.get("onPie_w_up") is None and btn.slice.get(
                            "onPie_w_down") is None:
                        btn.optionalWheelEvent(custom_event=event)
                break


class Button(QtWidgets.QPushButton):
    def __init__(self, openPieMenu, slice, globalSettings, parent=None):
        pie_label = slice["label"]
        # if globalSettings["showTKeyHint"] and slice["triggerKey"] != "None":
        if slice.get("triggerKey"):
            pie_label += ' ' * 2 + f'( {slice["triggerKey"]} )'

        super().__init__(pie_label, parent=parent)

        self.subMenu = slice.get("subslices")
        if self.subMenu:
            self.subMenuOpen = False
            self.btnList = []

        self.slice = slice

        self.setMouseTracking(True)
        self._hoverEnabled = False
        self._pressEnabled = False
        self._actual_hover = False
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

    def setHover(self, value):
        if self.svg_changes_color:
            self.setIcon(self.nohover_icon if value else self.hover_icon)

        if self.isHovered() != value:
            self._hoverEnabled = value
            self.setProperty("hover", value)
            self.style().unpolish(self)
            self.style().polish(self)

            if not self.subMenu:  # TODO: Left off here. SubMenu doesn't always get registered.
                return

            if value and not self.subMenuOpen:
                line = QtCore.QLineF(self.targetPos, self.parent().getPosition())

                queue = Queue()
                thread = Thread(target=lambda f, a: queue.put(f(a)),
                                args=(self.showSubMenu, line.angle()))
                thread.start()
                thread.join()
            elif not value and self.subMenuOpen:
                self.hideSubMenu()

    def isHovered(self):  # Button is selectedButton.
        return self._hoverEnabled

    def setPress(self, value):
        if self.isPressed() != value:
            self._pressEnabled = value
            self.setProperty("pressed", value)
            self.style().unpolish(self)
            self.style().polish(self)

    def isPressed(self):
        return self._pressEnabled

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
        self._actual_hover = True

    def leaveEvent(self, event) -> None:
        self._actual_hover = False

    def isActuallyHovered(self):  # Mouse on button.
        return self._actual_hover

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

    def createSubMenu(self, globalSettings, openPieMenu):  # TODO: Take menuScript into account.
        for subSlice in self.subMenu:
            if "menuScript" in subSlice and subSlice["menuScript"]:
                continue

            btn = Button(openPieMenu,
                         subSlice,
                         globalSettings,
                         parent=self.parent())
            btn.hide()

            self.btnList.append(btn)

    def updateSubMenuButtons(self, parentAngle: float):
        for index, btn in enumerate(self.btnList):
            maxAngle = 180  # TODO: Fix this (try other values).

            offsetAngle = ((maxAngle / (len(self.subMenu) + 1)) * (index + 1)) + (maxAngle / 2)

            btnAngle = (offsetAngle + parentAngle) % 360

            distance = 160

            try:
                line = QtCore.QLineF(self.pos(), self.pos() + QtCore.QPoint(0, distance))
                line.setAngle(btnAngle)
            except RuntimeError:
                return  # Occurs when menu is closed before timer is done.

            btn.show()
            btn.move(line.p2().toPoint().x(), line.p2().toPoint().y())

    def checkButtonHoverHeld(self, parentAngle: float):
        initBtn = self.parent().getSelectedButton()

        otherSelected = False
        for _ in range(5):
            sleep(0.05)

            try:
                if self.parent().getSelectedButton() != initBtn:
                    otherSelected = True
            except RuntimeError:
                return  # Occurs when menu is closed before timer is done.

        if not otherSelected:
            self.subMenuOpen = True

            self.updateSubMenuButtons(parentAngle)

    def showSubMenu(self, parentAngle: float):
        Thread(target=self.checkButtonHoverHeld, args=(parentAngle,)).start()

    def hideSubMenu(self):
        self.subMenuOpen = False

        for btn in self.btnList:
            btn.hide()
