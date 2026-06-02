from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt

# Tokens de color globales (Gold Theme)
C_PRI = "#f59e0b"
C_BG = "#0c0804"
C_TEXT = "#fde68a"

try:
    import qtawesome as qta
    HAS_QTA = True
except ImportError:
    HAS_QTA = False

class JarvisMessageBox(QDialog):
    def __init__(self, parent, title, text, is_error=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(380, 160)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.container = QWidget(self)
        self.container.setObjectName("msgContainer")
        self.container.setGeometry(0, 0, 380, 160)
        
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(20, 15, 20, 15)
        
        # Header (Icono y Título)
        header = QHBoxLayout()
        self.lbl_icon = QLabel()
        if HAS_QTA:
            icon_name = 'fa5s.exclamation-triangle' if is_error else 'fa5s.info-circle'
            icon_color = '#e11d48' if is_error else C_PRI
            self.lbl_icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(18, 18))
        else:
            self.lbl_icon.setText("⚠️" if is_error else "ℹ️")
        header.addWidget(self.lbl_icon)
        
        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet(f"color: {C_PRI}; font-size: 13px; font-weight: bold; letter-spacing: 1.5px; background: transparent;")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        # Texto del mensaje
        self.lbl_text = QLabel(text)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet("color: white; font-size: 12px; background: transparent; margin-top: 10px;")
        layout.addWidget(self.lbl_text)
        
        # Botón Aceptar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_ok = QPushButton("ACEPTAR")
        self.btn_ok.setFixedSize(90, 30)
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)
        
        # Estilos
        self.setStyleSheet(f"""
            QWidget#msgContainer {{
                background-color: {C_BG};
                border: 2px solid {C_PRI};
                border-radius: 12px;
            }}
            QPushButton {{
                background-color: rgba(10, 22, 32, 0.7);
                color: {C_PRI};
                border: 1.5px solid {C_PRI};
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {C_PRI};
                color: {C_BG};
            }}
        """)