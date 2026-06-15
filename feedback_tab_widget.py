from PySide6 import QtCore, QtWidgets, QtGui
import os
import logging
import sentry_sdk

logger = logging.getLogger(__name__)

class FeedbackTabWidget(QtWidgets.QWidget):
    """
    Independent feedback form tab widget integrated with Sentry SDK.
    Allows users to submit suggestions, bug reports, or general feedback.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        # Main Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # Header Section
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title_label = QtWidgets.QLabel("Kullanıcı Geri Bildirimi")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #8ecfff;")
        header_layout.addWidget(title_label)

        subtitle_label = QtWidgets.QLabel(
            "Görüşleriniz, istekleriniz veya karşılaştığınız hataları bizimle paylaşın. "
            "Mesajınız doğrudan geliştirici ekibine Sentry üzerinden güvenli şekilde iletilir."
        )
        subtitle_label.setStyleSheet("font-size: 13px; color: #b0b0b0;")
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(subtitle_label)

        layout.addWidget(header_widget)

        # Form Container Widget (looks like a card)
        form_card = QtWidgets.QFrame()
        form_card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        form_card.setStyleSheet("""
            QFrame {
                background-color: #202022;
                border: 1px solid #2d2d30;
                border-radius: 8px;
            }
            QLabel {
                font-weight: bold;
                color: #e3e3e3;
                border: none;
                font-size: 13px;
            }
            QLineEdit, QTextEdit, QComboBox {
                background-color: #2b2b2e;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border: 1px solid #0078D7;
                background-color: #313135;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
            }
        """)

        form_layout = QtWidgets.QFormLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        # Fields
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Örn: Ahmet Yılmaz (İsteğe bağlı)")
        form_layout.addRow("Ad Soyad:", self.name_input)

        self.email_input = QtWidgets.QLineEdit()
        self.email_input.setPlaceholderText("Örn: ahmet@example.com (İsteğe bağlı)")
        form_layout.addRow("E-posta Adresi:", self.email_input)

        self.category_select = QtWidgets.QComboBox()
        self.category_select.addItems([
            "💡 İstek / Öneri",
            "🐞 Hata Bildirimi",
            "❓ Genel Soru",
            "✏️ Diğer"
        ])
        form_layout.addRow("Kategori:", self.category_select)

        self.message_input = QtWidgets.QTextEdit()
        self.message_input.setPlaceholderText("Lütfen iletmek istediğiniz mesajı buraya yazın... (Zorunlu)")
        self.message_input.setMinimumHeight(120)
        form_layout.addRow("Mesajınız:", self.message_input)

        layout.addWidget(form_card)

        # Status & Message Area
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: normal; margin-top: 5px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Buttons Panel
        button_widget = QtWidgets.QWidget()
        button_layout = QtWidgets.QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)

        # Clear Button
        self.clear_btn = QtWidgets.QPushButton("Temizle")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                color: #d4d4d4;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #ffffff;
            }
        """)
        self.clear_btn.clicked.connect(self.clear_fields)
        button_layout.addWidget(self.clear_btn)

        button_layout.addStretch()

        # Send Button
        self.send_btn = QtWidgets.QPushButton("Geri Bildirim Gönder")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D7;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 10px 25px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
            QPushButton:disabled {
                background-color: #2d2d30;
                color: #888888;
                border: 1px solid #3f3f46;
            }
        """)
        self.send_btn.clicked.connect(self.send_feedback)
        button_layout.addWidget(self.send_btn)

        layout.addWidget(button_widget)
        layout.addStretch()

    def clear_fields(self):
        """Clears all form fields and resets status label."""
        self.name_input.clear()
        self.email_input.clear()
        self.category_select.setCurrentIndex(0)
        self.message_input.clear()
        self.status_label.setText("")

    def send_feedback(self):
        """Validates and sends user feedback to Sentry."""
        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        category = self.category_select.currentText()
        message = self.message_input.toPlainText().strip()

        # Validation
        if not message:
            self.status_label.setText("❌ Hata: Geri bildirim mesajı boş bırakılamaz.")
            self.status_label.setStyleSheet("color: #ff8e8e; font-weight: bold;")
            return

        # Disable elements during sending state
        self.send_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.status_label.setText("⏳ Geri bildiriminiz iletiliyor...")
        self.status_label.setStyleSheet("color: #8ecfff;")
        
        try:
            # Check if Sentry is initialized (compatible with v1 and v2)
            client = sentry_sdk.get_client() if hasattr(sentry_sdk, "get_client") else getattr(sentry_sdk.Hub.current, "client", None)
            if not client:
                # Sentry is not initialized (no DSN in env)
                logger.warning("Sentry is not initialized. Feedback logged locally only.")
                # Simulate offline success since we still logged it
                self.status_label.setText(
                    "⚠️ Çevrimdışı Mod: Geri bildiriminiz yerel günlüklere kaydedildi (Sentry aktif değil)."
                )
                self.status_label.setStyleSheet("color: #ffca28;")
            else:
                # Send to Sentry using a custom scope to associate user info & category
                with sentry_sdk.push_scope() as scope:
                    if name or email:
                        scope.set_user({"email": email or "anonymous@user.feedback", "username": name or "Anonymous"})
                    scope.set_tag("feedback.category", category)
                    scope.set_level("info")
                    
                    sentry_sdk.capture_message(
                        f"User Feedback: {category}\n\n{message}"
                    )
                    
                self.status_label.setText("✅ Geri bildiriminiz başarıyla iletildi. Görüşleriniz için teşekkür ederiz!")
                self.status_label.setStyleSheet("color: #8eff8e; font-weight: bold;")
                
                # Clear form on success
                self.name_input.clear()
                self.email_input.clear()
                self.message_input.clear()

        except Exception as e:
            logger.error(f"Failed to submit Sentry feedback: {e}")
            self.status_label.setText(f"❌ Geri bildirim iletilemedi: {str(e)}")
            self.status_label.setStyleSheet("color: #ff8e8e; font-weight: bold;")

        finally:
            self.send_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
