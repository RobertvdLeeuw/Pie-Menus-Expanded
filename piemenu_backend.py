import pieFunctions
from settings.pie_themes import pie_themes, tray_theme, pie_selection_theme

from ctypes import windll
from functools import partial
from math import sin, cos, ceil, sqrt
import os
from queue import Queue
# from random import choice, randint
import sys
from time import sleep
from threading import Thread, Timer

from dotmap import DotMap
import iconify
import keyboard
# import mouse
from pympler import muppy, summary
from PySide2.QtCore import QSize, QTimer, QVariantAnimation, Qt
from PySide2.QtGui import QColor, QCursor, QIcon, QPainter
from PySide2.QtWidgets import QWidget
from PySide2 import QtGui, QtWidgets, QtCore
import win32gui


script_dir = os.path.dirname(__file__)
icons_dir = os.path.join(script_dir, "resources/icons/")
transparent = QtGui.QColor(255, 255, 255, 0)


def getWidgetCenterPos(widget):
    # if widget.rect().x() > 0:
    #     print(f"{widget.rect().x() = }")
    # if widget.rect().y() > 0:
    #     print(f"{widget.rect().y() = }")
    # x() and y() are always, always zero. 🤷‍♂️🤷‍♂️ check with above if's.
    # so I am now commenting following line and will be removed after some time.
    # return QtCore.QPoint((widget.rect().width() - widget.rect().x())/2, (widget.rect().height() - widget.rect().y(
    # ))/2)

    if not widget:
        return

    return QtCore.QPoint(widget.rect().width() / 2, widget.rect().height() / 2)


def isChild(button, parent) -> bool:
    if not parent or not button:
        return False

    return button in getButtons(parent)


def getTargetingLine(l: QtCore.QLineF, p: QtCore.QPoint) -> QtCore.QLineF:
    if not l.length():
        line = QtCore.QLineF(l.p1(), p)
        return line

    u = (((p.x() - l.p1().x()) * (l.p2().x() - l.p1().x())) +
         ((p.y() - l.p1().y()) * (l.p2().y() - l.p1().y()))) / (l.length() ** 2)

    if u < 0:  # TODO: Fix wrong lineCast.
        point = l.p1()
    elif u > 1:
        point = l.p2()
    else:
        point = QtCore.QPoint(l.p1().x() + u * (l.p2().x() - l.p1().x()),
                              l.p1().y() + u * (l.p2().y() - l.p1().y()))

    line = QtCore.QLineF(p, point)
    return line


def getButtons(button, checkIfChildrenActive=False):
    if not isinstance(button, Button):
        return list()

    if not button.subMenu:
        return list()

    if checkIfChildrenActive and button.btnList and not button.btnList[0].isVisible():
        return list()

    return button.btnList


class Window(QtWidgets.QWidget):
    def __init__(self, settings, globalSettings):
        super().__init__()
        self._menu = None

        self.settings = settings
        self.globalSettings = globalSettings

        # following line for window less app
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)

        # following line for transparent background
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.showMaximized()

    def showMenu(self, openPieMenu, summonPosition):
        if self._menu:
            self._menu.kill()
            return

        self._menu = RadialMenu(self, summonPosition, openPieMenu, self.settings, self.globalSettings)
        self._menu.show()

        all_objects = muppy.get_objects()
        # print(all_objects)
        # print(len(all_objects))
        # Prints out a summary of the large objects
        # sum1 = summary.summarize(all_objects)
        # summary.print_(sum1)

    def killMenu(self):
        if self._menu:
            self._menu.kill()
            return

    def mousePressEvent(self, event):
        # this is automatically called when a mouse key press event occurs
        # this acts as right click to cancel pie menu
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            if self._menu:
                self._menu.kill()
                return

    def launchByTrigger(self, counter):
        if self._menu is None:
            return
        self._menu.launchByTrigger(counter)
        self.killMenu()

    def releasedHeldKey(self):
        if self._menu is None:
            return
        self._menu.launchByGesture()
        self.killMenu()

    def ll_wheel_event(self, event):
        if self._menu is None:
            return
        self._menu.ll_wheel_event(event)

    def isMenuOpen(self):
        return self._menu


class RadialMenu(QtWidgets.QWidget):
    def __init__(self, parent, summonPosition, openPieMenu, settings, globalSettings):
        super().__init__(parent=parent)
        self.setMouseTracking(True)
        self.settings = settings
        self.globalSettings = globalSettings
        self.setGeometry(self.parent().rect())
        self._inRadius, self._outRadius = list(map(float, openPieMenu["in_out_radius"].split("_")))
        self._btnList = []
        self._selectedBtn = None
        self._selectedBtnParent = None
        self._selectedBtnParentInitPos = None
        self._selectedBtnInitPos = None
        self._prevSelectedBtn = None
        self._mousePressed = False
        self._animFinished = False
        self._debugDraw = False

        self.openPieMenu = openPieMenu

        self._summonPosition = self.parent().mapFromGlobal(summonPosition)
        self._currentMousePos = QtCore.QPoint(self._summonPosition)

        self.global_mouse_timer = QTimer()
        self.global_mouse_timer.timeout.connect(self.globalMouseMoveEvent)
        self.global_mouse_timer.start(5)

        slices = openPieMenu["slices"]
        slices = slices[: int(openPieMenu["numSlices"])]
        if openPieMenu.get("offset_slices"):
            slices = slices[-1 * openPieMenu.get("offset_slices"):] + slices[: -1 * openPieMenu.get("offset_slices")]

        for slice in slices:
            self.addButton(slice)

    def addButton(self, slice):
        btn = Button(self.openPieMenu, slice, self.globalSettings, parent=self)
        self._btnList.append(btn)

        if btn.subMenu:
            btn.createSubMenu()

        return btn

    def kill(self):
        self.animGroup.setDirection(QtCore.QAbstractAnimation.Backward)
        self.animGroup.finished.connect(self.hide)
        self.animGroup.start()
        self.parent()._menu = None
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
            # for anim in anims:
            #     self.animGroup.addAnimation(anim)
            self.animGroup.addAnimation(anims[1])

        self.animGroup.finished.connect(self.animFinished)
        self.animGroup.start()

    def animFinished(self):
        self._animFinished = True

    def setButtonPositions(self):
        offset_angle = -self.openPieMenu["offset_angle"]
        angle = 360 / len(self._btnList)
        line = QtCore.QLineF(self._summonPosition, self._summonPosition - QtCore.QPoint(0, self._outRadius))

        for counter, btn in enumerate(self._btnList):
            if counter == 0:
                line.setAngle(line.angle() + offset_angle)
            else:
                line.setAngle(line.angle() + angle + offset_angle)

            pos = getWidgetCenterPos(btn)
            if abs(line.p2().x() - self._summonPosition.x()) < 3:
                pass
            elif line.p2().x() < self._summonPosition.x():
                pos.setX(btn.rect().width())
            else:
                pos.setX(btn.rect().x())

            if abs(line.p2().y() - self._summonPosition.y()) < 3:
                pass
            elif line.p2().y() < self._summonPosition.y():
                if round(line.angle() % 90) == 0:
                    pos.setY(btn.rect().height())
            else:
                if round(line.angle() % 90) == 0:
                    pos.setY(btn.rect().y())

            btn.move(line.p2().toPoint() - pos)
            btn.targetPos = line.p2().toPoint()

    def fixSummonPosition(self, pos):
        savepadding = int(self.globalSettings["savePadding"])
        minSpaceToBorder = savepadding + self._outRadius
        maxX = self.rect().width() - minSpaceToBorder
        maxY = self.rect().height() - minSpaceToBorder

        angle = 360 / len(self._btnList)
        line = QtCore.QLineF(self._summonPosition, self._summonPosition - QtCore.QPoint(0, self._outRadius))
        counter = 0
        offset_angle = -1 * self.openPieMenu["offset_angle"]

        _minX = _minY = _maxX = _maxY = self._btnList[0]

        # self.setButtonsPositions() # uncomment this if you can't live with few pixels off in right side padding
        # Guess the button position
        for btn in self._btnList:
            if counter == 0:
                line.setAngle(line.angle() + offset_angle)
            else:
                line.setAngle(line.angle() + angle + offset_angle)

            if line.angle() < 89 or line.angle() > 271:
                if _maxX.pos().x() + _maxX.width() < btn.pos().x() + btn.width():
                    _maxX = btn
            elif 91 < line.angle() < 269:
                if _minX.width() < btn.width():
                    _minX = btn

            counter += 1

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
        self._currentMousePos = self.parent().mapFromGlobal(QCursor.pos())
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

    def GetSelectedButton(self):
        return self._selectedBtn

    def getPosition(self):
        return self._summonPosition

    def findSelectedButton(self):
        targetBtn = self._btnList[0]
        # targetBtnInitDist = None if not self._selectedBtn else QtCore.QLineF(self._currentMousePos,
        #                                                                      self._selectedBtnInitPos).length()

        targetBtnDist = QtCore.QLineF(self._currentMousePos, targetBtn.pos()).length()

        for btn in self._btnList + getButtons(self._selectedBtn, True) + getButtons(self._selectedBtnParent):
            btnHoverLine = QtCore.QLineF(btn.pos() + getWidgetCenterPos(btn),
                                         self.getHoverPosition(btn) + getWidgetCenterPos(btn))
            # print(btnHoverLine, self._currentMousePos)
            btnDist = getTargetingLine(btnHoverLine, self._currentMousePos).length()

            if btnDist < targetBtnDist:
                targetBtn = btn
                targetBtnDist = btnDist
        return targetBtn

    def getHoverPosition(self, btn, lineFirstPoint=None):
        if btn.isHovered():  # If already hovered out, return the buttons initial position.
            initPos = self._selectedBtnParentInitPos if btn is self._selectedBtnParent else self._selectedBtnInitPos

            return initPos
        else:
            initPos = btn.pos()

        selectionMovement = 1.75 if btn.subMenu else 1.5

        line = QtCore.QLineF(lineFirstPoint if lineFirstPoint else self._summonPosition,
                             initPos + getWidgetCenterPos(btn))
        line.setLength(line.length() * selectionMovement)

        newPos = line.p2() - getWidgetCenterPos(btn)
        return QtCore.QPoint(newPos.x(), newPos.y())

    def updateSelectedButton(self, targetBtn):
        if self._selectedBtn != targetBtn:
            mouseInCircle = (self._currentMousePos.x() - self._summonPosition.x()) ** 2 + (
                    self._currentMousePos.y() - self._summonPosition.y()) ** 2 < self._inRadius ** 2

            if targetBtn and not mouseInCircle:
                if self._selectedBtn:
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

                self._prevSelectedBtn, self._selectedBtn = self._selectedBtn, targetBtn
                self._selectedBtnInitPos = self._selectedBtn.pos()

                # Move button to hover position.
                if not isChild(self._prevSelectedBtn, self._selectedBtn) and not self._selectedBtn.isHovered():
                    # Different direction for subButtons
                    newPos = self.getHoverPosition(self._selectedBtn, None if not self._selectedBtnParent else
                    self._selectedBtnParent.pos() + getWidgetCenterPos(self._selectedBtnParent))

                    self._selectedBtn.move(newPos)

                self._selectedBtn.setHover(True)

                if self._mousePressed:
                    self._selectedBtn.setPress(True)

                # Unhover all other
                for btn in self._btnList + getButtons(self._selectedBtn) + getButtons(
                        self._selectedBtnParent) + getButtons(self._selectedBtn):
                    if isChild(self._selectedBtn, btn):  # Except parent
                        continue

                    if btn != self._selectedBtn:
                        btn.setHover(False)

    def paintEvent(self, event):
        angle = None
        circleRect = QtCore.QRect(self._summonPosition.x() - self._inRadius, self._summonPosition.y() - self._inRadius,
                                  self._inRadius * 2, self._inRadius * 2)  # The rect of the center circle
        arcSize = 36
        # self._selectedBtn = None
        mouseInCircle = (self._currentMousePos.x() - self._summonPosition.x()) ** 2 + (
                self._currentMousePos.y() - self._summonPosition.y()) ** 2 < self._inRadius ** 2

        if "theme" in self.openPieMenu.keys() and self.openPieMenu["theme"].lower() not in ("", "none", "null"):
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
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, on=True)
        # highqualityantialising is obsolete value now and is ignored
        # refer to this -> https://doc.qt.io/qtforpython-5/PySide2/QtGui/QPainter.html
        # painter.setRenderHint(QtGui.QPainter.HighQualityAntialiasing, on= True)
        refLine = QtCore.QLineF(self._summonPosition, self._currentMousePos)

        # guess the target button
        targetBtn = self._btnList[0]  # TODO: Migrate
        targetLine = QtCore.QLineF(self._summonPosition, targetBtn.pos() + getWidgetCenterPos(targetBtn))
        minAngle = 360

        for btn in self._btnList:
            btn.setPress(False)

            btnLine = QtCore.QLineF(self._summonPosition, btn.pos() + getWidgetCenterPos(btn))
            angle = btnLine.angleTo(refLine)
            if angle > 180:
                angle = refLine.angleTo(btnLine)

            if angle < minAngle:
                targetBtn = btn
                targetLine = btnLine  # Used for the debug lines
                minAngle = angle  # Used for the comparison

        if not mouseInCircle:
            normLine = refLine.unitVector()  # Create a line with the same origine and direction but with a length of 1
            finalPointF = normLine.p1() + (normLine.p2() - normLine.p1()) * self._inRadius
            finalPoint = QtCore.QPoint(int(finalPointF.x()), int(finalPointF.y()))
            angle = QtCore.QLineF(self._summonPosition,
                                  self._summonPosition + QtCore.QPoint(self._inRadius, 0)).angleTo(normLine)

        # Draw Background circle
        painter.setPen(bgCirclePen)
        painter.drawEllipse(circleRect)

        # Draw Foreground circle
        if angle and not mouseInCircle:
            painter.setPen(fgCirclePen)
            if self.globalSettings["useArcOnHover"]:
                painter.drawArc(circleRect, int(angle - arcSize / 2) * 16, arcSize * 16)
            if self.globalSettings["useLineOnHover"]:
                # tracking line
                fgCirclePen.setCapStyle(Qt.RoundCap)
                painter.setPen(fgCirclePen)
                painter.drawLine(self._summonPosition, self._currentMousePos)

        # Debug draw
        if self._debugDraw:
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

    def launchByGesture(self):
        if not self._selectedBtn:
            return

        self._selectedBtn.animateClick()
        self._selectedBtn.toDelete = True

    def ll_wheel_event(self, event):
        for btn in self._btnList:
            if btn.isHovered():
                if btn.slice.get("w_up") or btn.slice.get("w_down"):
                    if not btn.is_actually_hovered():
                        btn.optional_wheelEvent(custom_event=event)
                    elif btn.is_actually_hovered() and btn.slice.get("onPie_w_up") is None and btn.slice.get(
                            "onPie_w_down") is None:
                        btn.optional_wheelEvent(custom_event=event)
                break

    def launchByTrigger(self, counter):
        self._btnList[counter].animateClick()


class Button(QtWidgets.QPushButton):
    def __init__(self, openPieMenu, slice, globalSettings, parent=None):
        pie_label = f'{slice["label"]}'
        if globalSettings["showTKeyHint"] and not (slice["triggerKey"] == "None"):
            pie_label += ' ' * 2 + f'( {slice["triggerKey"]} )'

        super().__init__(pie_label,
                         parent=parent)

        hasSubMenu = "hasSubMenu" in slice.keys() and slice["hasSubMenu"]
        self.subMenu = None if not hasSubMenu else slice["subSlices"]

        if self.subMenu:
            self.subMenuOpening = False
            self.subMenuOpen = False
            self.btnList = list()

        # if not isinstance(parent, Button):
        #     self.move(self.pos().x() + 100, self.pos().y() + 100)

        self.globalSettings = globalSettings
        self.openPieMenu = openPieMenu
        self.slice = slice

        self.setMouseTracking(True)
        self._hoverEnabled = False
        self._pressEnabled = False
        self._actual_hover = False  # this determines whether mouse is actually on button or not.
        self.targetPos = self.pos()
        self.icon = None
        self.svg_changes_color = False

        if slice.get("icon"):
            self.SetIcon()

        self.setStyleSheet(pie_themes[openPieMenu["theme"]] if openPieMenu["theme"] else pie_themes.dhalu_theme)

        if self.slice.get("onPie_w_up") or self.slice.get("onPie_w_down"):
            self.wheelEvent = self.optional_wheelEvent

        self.pressed.connect(self.run_pie_function)
        # self.pressed.connect(self.parent().kill)

        self.opacityEffect = QtWidgets.QGraphicsOpacityEffect(self, opacity=1.0)
        self.setGraphicsEffect(self.opacityEffect)

        self.toDelete = False
        # keep the buttons always enabled even before the animation to speed up things
        # so don't uncomment the following line
        # self.setEnabled(False)

    def DeleteCheck(self):
        def wrapper(func, *args, **kwargs):
            if self.toDelete:
                return

            return func(*args, **kwargs)

        return wrapper

    def SetIcon(self):
        icon = os.path.join(icons_dir, self.slice.get("icon").strip())
        if not os.path.exists(icon):
            icon = os.path.join(icons_dir, "default.svg")

        self.setText(self.globalSettings.get("icon-padding-right") + self.text())
        if self.slice.get("icon").strip()[-4:] == ".svg":
            try:  # TODO: See if this can be transformed into if statement, else check error type.
                svg_nohover_hover = pie_selection_theme.get(self.openPieMenu.get("theme")).get("svg_nohover_hover")
                nohover_col, hover_col = svg_nohover_hover.strip().split("_")
                self.nohover_icon = iconify.Icon(icon, color=QtGui.QColor(nohover_col))
                self.hover_icon = iconify.Icon(icon, color=QtGui.QColor(hover_col))
                self.svg_changes_color = True
                icon = self.nohover_icon
            except:
                icon = iconify.Icon(icon)

        self.icon = icon
        self.setIcon(QIcon(icon))

    def setHover(self, value):
        if self.svg_changes_color:
            self.setIcon(self.nohover_icon if value else self.hover_icon)

        if self.isHovered() != value:
            self._hoverEnabled = value
            self.setProperty("hover", value)  # TODO: Test b"".
            self.style().unpolish(self)
            self.style().polish(self)

            if not self.subMenu:
                return

            if value and not self.subMenuOpening and not self.subMenuOpen:
                line = QtCore.QLineF(self.targetPos, self.parent().getPosition())

                queue = Queue()
                thread = Thread(target=lambda f, a: queue.put(f(a)),
                                args=(self.showSubMenu, line.angle()))
                thread.start()
                thread.join()

                return
            elif not value and self.subMenuOpen:
                self.hideSubMenu()

    def isHovered(self):
        return self._hoverEnabled

    def setPress(self, value):
        if self.isPressed() != value:
            self._pressEnabled = value
            self.setProperty("pressed", value)  # TODO: Test b"".
            self.style().unpolish(self)
            self.style().polish(self)

    def isPressed(self):
        return self._pressEnabled

    def gestureClick(self):
        super().animateClick()

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
        # return super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._actual_hover = False
        # return super().leaveEvent(event)

    def is_actually_hovered(self):
        return self._actual_hover

    def optional_wheelEvent(self, event=False, custom_event=None) -> None:
        if custom_event:
            event = custom_event
            # Custom wheel events here.
            if event.scan_code == 7864320 and self.slice.get("w_up"):
                # Scroll up(7864320), away from the user
                self.run_pie_function(wheel=self.slice.get("w_up"))
            elif event.scan_code == 4287102976 and self.slice.get("w_down"):
                # Scroll down(4287102976), towards user
                self.run_pie_function(wheel=self.slice.get("w_down"))
            return

        # Default wheel event
        if event.angleDelta().y() > 0 and self.slice.get("onPie_w_up"):
            # Scroll up, away from the user
            self.run_pie_function(wheel=self.slice.get("onPie_w_up"))

        elif event.angleDelta().y() < 0 and self.slice.get("onPie_w_down"):
            # Scroll down, towards user
            self.run_pie_function(wheel=self.slice.get("onPie_w_down"))

        return super().wheelEvent(event)

    def run_pie_function(self, wheel=False):
        pie_func, params = wheel if wheel \
                               else self.slice["function"], self.slice["params"]

        if pie_func.lower() == "none" or not pie_func:
            return

        if pie_func not in pieFunctions.FUNCTIONS.keys():
            print(f"Invalid button function: {pie_func}")

        if "brightness" in pie_func:
            pieFunctions.sendHotkey([pie_func, params[0]])

        pieFunctions.FUNCTIONS[pie_func](params)

    def createSubMenu(self):  # TODO: Take menuScript into account.
        for subSlice in self.subMenu:
            if "menuScript" in subSlice.keys() and subSlice["menuScript"]:
                continue

            # btn = Button(self.openPieMenu, subSlice, self.globalSettings, parent=self)
            btn = Button(self.openPieMenu,
                         subSlice,
                         self.globalSettings,
                         parent=self.parent())
            btn.hide()

            self.btnList.append(btn)

    def updateSubMenuButtons(self, parentAngle: float):
        for index, btn in enumerate(self.btnList):
            offsetAngle = ((180 / (len(self.subMenu) + 1)) * (index + 1)) + 90  # -90 <--> 90

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
        initBtn = self.parent().GetSelectedButton()

        otherSelected = False
        for i in range(5):
            sleep(0.05)

            try:
                if self.parent().GetSelectedButton() != initBtn:
                    otherSelected = True
            except RuntimeError:
                return  # Occurs when menu is closed before timer is done.

        self.subMenuOpening = False
        if not otherSelected:
            self.subMenuOpen = True

            self.updateSubMenuButtons(parentAngle)

    def showSubMenu(self, parentAngle: float):
        Thread(target=self.checkButtonHoverHeld, args=(parentAngle,)).start()

    def hideSubMenu(self):
        self.subMenuOpen = False

        for btn in self.btnList:
            btn.hide()
