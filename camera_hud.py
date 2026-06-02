from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

# Tokens de color globales (Gold Theme)
C_PRI = "#f59e0b"
C_TEXT = "#fde68a"

try:
    import qtawesome as qta
    HAS_QTA = True
except ImportError:
    HAS_QTA = False

class CameraPreviewWindow(QWidget):
    """
    Ventana flotante, sin bordes y semi-transparente que muestra el feed de la cámara.
    """
    def __init__(self, shared_thread=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(370, 320)

        self.shared_thread = shared_thread
        self.drag_position = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        container = QFrame(self)
        container.setObjectName("CameraContainer")
        container.setStyleSheet(f"""
            QFrame#CameraContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(12, 10, 5, 0.60), stop:1 rgba(2, 2, 2, 0.85));
                border: 1.8px solid {C_PRI};
                border-radius: 16px;
            }}
            QLabel {{
                color: {C_TEXT};
                font-family: 'Century Gothic', sans-serif;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 6)
        container.setGraphicsEffect(shadow)

        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(10, 10, 10, 10)
        c_layout.setSpacing(6)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(6)
        
        self.lbl_title_icon = QLabel(self)
        if HAS_QTA:
            self.lbl_title_icon.setPixmap(qta.icon('fa5s.video', color=C_PRI).pixmap(11, 11))
        
        title_label = QLabel("PILOTO GESTUAL  ·  HUD", self)
        title_label.setStyleSheet(f"font-weight: bold; font-size: 9px; letter-spacing: 1.8px; color: {C_PRI}; background: transparent; border: none;")

        self.btn_min = QPushButton("–", self)
        self.btn_min.setFixedSize(22, 22)
        self.btn_min.setStyleSheet(f"QPushButton {{ background: transparent; color: {C_PRI}; border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 11px; font-weight: bold; }} QPushButton:hover {{ background-color: rgba(245,158,11,0.25); border-color: {C_PRI}; }}")
        self.btn_min.clicked.connect(self.hide)

        self.btn_close = QPushButton("×", self)
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setStyleSheet(f"QPushButton {{ background: transparent; color: {C_PRI}; border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 11px; font-weight: bold; }} QPushButton:hover {{ background-color: #ff3b30; color: white; border-color: #ff3b30; }}")
        self.btn_close.clicked.connect(self.hide)

        title_layout.addWidget(self.lbl_title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_min)
        title_layout.addWidget(self.btn_close)
        c_layout.addLayout(title_layout)

        self.lbl_feed = QLabel(self)
        self.lbl_feed.setFixedSize(346, 226)
        self.lbl_feed.setStyleSheet(f"background-color: rgba(0, 0, 0, 0.45); border-radius: 10px; border: 1.2px dashed rgba(245, 158, 11, 0.40);")
        self.lbl_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(self.lbl_feed)

        footer = QHBoxLayout()
        self.lbl_status = QLabel("Buscando mano...", self)
        self.lbl_status.setStyleSheet(f"font-size: 9px; color: {C_TEXT}; font-style: italic; background: transparent; border: none;")
        
        self.lbl_bg_indicator = QLabel("Activo en 2do plano", self)
        self.lbl_bg_indicator.setStyleSheet("font-size: 8px; color: #00ff88; font-weight: bold; background: transparent; border: none;")
        
        footer.addWidget(self.lbl_status)
        footer.addStretch()
        footer.addWidget(self.lbl_bg_indicator)
        c_layout.addLayout(footer)
        layout.addWidget(container)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def on_frame_received(self, q_img, status):
        from PyQt6.QtGui import QPixmap
        if not self.isVisible(): return
        pixmap = QPixmap.fromImage(q_img).scaled(self.lbl_feed.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        self.lbl_feed.setPixmap(pixmap)
        self.lbl_status.setText(f"Piloto: {status}")

    def on_active_changed(self, active):
        if not active:
            self.lbl_status.setText("Cámara Desconectada")
            self.lbl_feed.clear()

    def attach_thread(self, thread):
        self.shared_thread = thread
        thread.frame_signal.connect(self.on_frame_received)
        thread.active_signal.connect(self.on_active_changed)

    def closeEvent(self, event):
        event.ignore()
        self.hide()