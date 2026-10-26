import sys
import logging
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen
import math

logger = logging.getLogger("jarvis.hud")


class JarvisHUD(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                           Qt.WindowType.WindowStaysOnTopHint | 
                           Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(100, 100, 150, 150)
        
        self.state = "idle"  # idle, listening, thinking, speaking
        self.pulse = 0
        self.angle = 0
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(50)
        
        # Make draggable
        self.dragging = False
        self.drag_position = QPoint()
        
    def update_animation(self):
        self.pulse += 0.1
        self.angle += 5
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        radius = 40
        
        # Draw outer glow
        for i in range(3):
            glow_radius = radius + 10 + i * 5 + int(5 * math.sin(self.pulse))
            alpha = 50 - i * 15
            painter.setPen(QPen(QColor(100, 200, 255, alpha), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center_x - glow_radius, center_y - glow_radius, 
                              glow_radius * 2, glow_radius * 2)
        
        # Draw core
        if self.state == "listening":
            color = QColor(100, 255, 100)
        elif self.state == "thinking":
            color = QColor(255, 200, 100)
        elif self.state == "speaking":
            color = QColor(100, 200, 255)
        else:
            color = QColor(150, 150, 150)
        
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        core_radius = radius - 5 + int(3 * math.sin(self.pulse))
        painter.drawEllipse(center_x - core_radius, center_y - core_radius, 
                          core_radius * 2, core_radius * 2)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
    
    def mouseReleaseEvent(self, event):
        self.dragging = False
    
    def set_state(self, state):
        self.state = state
        logger.info(f"HUD state: {state}")


def main():
    app = QApplication(sys.argv)
    hud = JarvisHUD()
    hud.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
