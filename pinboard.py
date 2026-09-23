# -*- coding: utf-8 -*-
"""贴图钉板（Snipaste 风格）：把图片钉在屏幕最上层。

操作
====
- 左键拖拽：移动
- 滚轮：调整透明度
- Ctrl + 滚轮：缩放
- 双击 / Esc：关闭
- 右键：菜单（复制图片 / 重置 / 关闭）
"""
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget
from i18n import tr


class PinWindow(QWidget):
    closed = Signal(object)  # 参数为自身，便于宿主从列表移除

    def __init__(self, pixmap: QPixmap, pos: QPoint | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._pix = QPixmap(pixmap)
        # 保留 dpr：按逻辑尺寸布局，绘制时铺满控件 → 100% 时 1:1 物理像素，不发虚
        self._dpr = float(self._pix.devicePixelRatio() or 1.0)
        self._scale = 1.0
        self._drag_pos: QPoint | None = None
        self.setWindowOpacity(1.0)
        self._apply_size()
        if pos is not None:
            self.move(pos)
        self.setCursor(Qt.SizeAllCursor)

    # ---------- 外观 ----------
    def _apply_size(self):
        w = max(24, round(self._pix.width() / self._dpr * self._scale))
        h = max(24, round(self._pix.height() / self._dpr * self._scale))
        self.setFixedSize(w, h)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        # 缩小时平滑滤波，放大时保持像素锐利
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._scale < 1.0)
        p.drawPixmap(self.rect(), self._pix)   # 目标矩形重载：按逻辑尺寸 1:1 铺满
        p.setPen(QPen(QColor(30, 136, 229), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # ---------- 交互 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self._show_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e):
        self.close()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120
        if e.modifiers() & Qt.ControlModifier:
            self._scale = min(4.0, max(0.1, self._scale * (1.1 ** steps)))
            self._apply_size()
        else:
            self.setWindowOpacity(min(1.0, max(0.15, self.windowOpacity() + steps * 0.08)))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

    # ---------- 菜单 ----------
    def _show_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        act_copy = QAction(tr("复制图片"), self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setPixmap(self._pix))
        menu.addAction(act_copy)
        act_reset = QAction(tr("重置大小 / 透明度"), self)
        act_reset.triggered.connect(self._reset)
        menu.addAction(act_reset)
        menu.addSeparator()
        act_close = QAction(tr("关闭 (Esc)"), self)
        act_close.triggered.connect(self.close)
        menu.addAction(act_close)
        menu.exec(global_pos)

    def _reset(self):
        self._scale = 1.0
        self.setWindowOpacity(1.0)
        self._apply_size()

    def closeEvent(self, e):
        self.closed.emit(self)
        super().closeEvent(e)
