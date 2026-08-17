import sys
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from Backend_logic.network import ChatServer


class ServerEvents(QObject):
    event_received = pyqtSignal(object)


class ChatServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Encrypted CK Chat Server")
        self.resize(980, 720)

        self.server = None
        self.events = ServerEvents()
        self.events.event_received.connect(self.on_network_event)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Server activity log")

        self.host_input = QLineEdit("0.0.0.0")
        self.host_input.setPlaceholderText("Host")

        self.port_input = QLineEdit("1050")
        self.port_input.setPlaceholderText("Port")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Shared password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.start_button = QPushButton("Start Server")
        self.start_button.clicked.connect(self.start_server)

        self.broadcast_input = QLineEdit()
        self.broadcast_input.setPlaceholderText("Broadcast message...")
        self.broadcast_input.returnPressed.connect(self.broadcast_message)

        self.broadcast_button = QPushButton("Broadcast")
        self.broadcast_button.clicked.connect(self.broadcast_message)
        self.broadcast_button.setEnabled(False)

        self.user_list = QListWidget()
        self.user_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self.disconnect_button = QPushButton("Disconnect User")
        self.disconnect_button.clicked.connect(self.disconnect_user)
        self.disconnect_button.setEnabled(False)

        self.suspend_button = QPushButton("Suspend User")
        self.suspend_button.clicked.connect(self.suspend_user)
        self.suspend_button.setEnabled(False)

        self.shutdown_button = QPushButton("Shutdown Server")
        self.shutdown_button.clicked.connect(self.shutdown_server)
        self.shutdown_button.setEnabled(False)

        self.status_label = QLabel("Stopped")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #fb7185; font-weight: bold;")

        self.build_ui()
        self.apply_styles()

    def build_ui(self) -> None:
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("Host:"))
        config_layout.addWidget(self.host_input)
        config_layout.addWidget(QLabel("Port:"))
        config_layout.addWidget(self.port_input)
        config_layout.addWidget(QLabel("Password:"))
        config_layout.addWidget(self.password_input)
        config_layout.addWidget(self.start_button)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.broadcast_input)
        action_layout.addWidget(self.broadcast_button)
        action_layout.addWidget(self.disconnect_button)
        action_layout.addWidget(self.suspend_button)
        action_layout.addWidget(self.shutdown_button)

        user_layout = QVBoxLayout()
        user_layout.addWidget(QLabel("Connected Users"))
        user_layout.addWidget(self.user_list)

        main_layout = QVBoxLayout()
        main_layout.addLayout(config_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.log_view, stretch=3)
        main_layout.addLayout(action_layout)
        main_layout.addLayout(user_layout)

        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #0f172a; color: #e2e8f0; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #94a3b8; }
            QTextEdit, QListWidget, QLineEdit { background: #111827; border: 1px solid #334155; border-radius: 10px; color: #e2e8f0; }
            QTextEdit { padding: 10px; }
            QLineEdit { min-height: 34px; }
            QPushButton { background: #2563eb; color: #ffffff; border: none; border-radius: 10px; min-height: 36px; padding: 0 16px; }
            QPushButton:hover { background: #3b82f6; }
            QPushButton:disabled { background: #334155; color: #64748b; }
            """
        )
        self.log_view.setStyleSheet("background: #0b1220; border: 1px solid #334155; border-radius: 10px;")
        self.user_list.setStyleSheet("background: #0f172a; border: 1px solid #334155; border-radius: 10px;")

    def start_server(self) -> None:
        if self.server and self.server.running:
            return

        host = self.host_input.text().strip() or "0.0.0.0"
        port_text = self.port_input.text().strip() or "1050"
        password = self.password_input.text().strip() or "chat-secret"

        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Port", "Port must be a number.")
            return

        self.server = ChatServer(password=password, host=host, port=port, event_callback=self.events.event_received.emit)
        self.server.start()
        self.set_running_state(True)
        self.append_log(f"<span style='color:#7dd3fc;'>Server started at {host}:{port}</span>")

    def broadcast_message(self) -> None:
        if not self.server or not self.server.running:
            QMessageBox.warning(self, "Server Offline", "Start the server before broadcasting.")
            return

        message = self.broadcast_input.text().strip()
        if not message:
            return

        self.server.broadcast_chat("ADMIN", message)
        self.append_log(f"<span style='color:#a3e635;'>ADMIN:</span> {message}")
        self.broadcast_input.clear()

    def disconnect_user(self) -> None:
        if not self.server or not self.server.running:
            return

        selected = self.user_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "No User Selected", "Select a user to disconnect.")
            return

        username = selected.data(Qt.ItemDataRole.UserRole) or selected.text()
        self.server.disconnect_user(username)
        self.append_log(f"<span style='color:#fda4af;'>Disconnected {username}</span>")

    def suspend_user(self) -> None:
        if not self.server or not self.server.running:
            return

        selected = self.user_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "No User Selected", "Select a user to suspend.")
            return

        username = selected.data(Qt.ItemDataRole.UserRole) or selected.text()
        self.server.suspend_user(username)
        self.append_log(f"<span style='color:#fda4af;'>Suspended {username}</span>")

    def shutdown_server(self) -> None:
        if self.server:
            self.server.shutdown()
        self.set_running_state(False)
        self.append_log("<span style='color:#f97316;'>Server shutdown.</span>")

    def on_network_event(self, event: object) -> None:
        if not isinstance(event, dict):
            return
        event_type = event.get("type")
        if event_type == "log":
            self.append_log(f"<span style='color:#93c5fd;'>{event.get('message', '')}</span>")
        elif event_type == "user_list":
            self.update_user_list(event.get("users", []))

    def append_log(self, message: str) -> None:
        self.log_view.append(message)
        self.log_view.ensureCursorVisible()

    def update_user_list(self, users: list) -> None:
        self.user_list.clear()
        for entry in users:
            if isinstance(entry, dict):
                username = entry.get("username", "")
                device_name = entry.get("device_name", "")
                text = f"{username} ({device_name})" if device_name else username
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, username)
                self.user_list.addItem(item)
            else:
                item = QListWidgetItem(str(entry))
                item.setData(Qt.ItemDataRole.UserRole, str(entry))
                self.user_list.addItem(item)
        self.disconnect_button.setEnabled(bool(users))
        self.suspend_button.setEnabled(bool(users))

    def set_running_state(self, running: bool) -> None:
        self.status_label.setText("Running" if running else "Stopped")
        self.status_label.setStyleSheet(
            "color: #22c55e; font-weight: bold;" if running else "color: #fb7185; font-weight: bold;"
        )
        self.start_button.setEnabled(not running)
        self.shutdown_button.setEnabled(running)
        self.broadcast_button.setEnabled(running)
        self.disconnect_button.setEnabled(running and self.user_list.count() > 0)

    def closeEvent(self, event) -> None:
        self.shutdown_server()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = ChatServerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
