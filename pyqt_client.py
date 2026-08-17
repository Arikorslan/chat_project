import base64
import platform
import sys
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
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

from Backend_logic.network import ChatClient


class ClientEvents(QObject):
    event_received = pyqtSignal(object)


class ChatClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Encrypted CK Chat Client")
        self.resize(980, 720)

        self.client = ChatClient()
        self.events = ClientEvents()
        self.events.event_received.connect(self.on_network_event)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setPlaceholderText("Server messages appear here...")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Shared password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setPlaceholderText("Server host")

        self.port_input = QLineEdit("1050")
        self.port_input.setPlaceholderText("Server port")

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type a message and press Enter or Send")
        self.message_input.returnPressed.connect(self.send_message)

        self.status_label = QLabel("Disconnected")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #7dd3fc; font-weight: bold;")

        self.user_list = QListWidget()
        self.user_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search users")
        self.search_input.textChanged.connect(self.filter_user_list)

        self.all_users: list = []
        self.user_colors: dict[str, str] = {}
        self.current_room: str = ""
        self.current_username: str = ""

        self.room_name_input = QLineEdit()
        self.room_name_input.setPlaceholderText("Room name")

        self.create_room_button = QPushButton("Create Room")
        self.create_room_button.clicked.connect(self.create_room)

        self.join_room_button = QPushButton("Join Room")
        self.join_room_button.clicked.connect(self.join_room)

        self.leave_room_button = QPushButton("Leave Room")
        self.leave_room_button.clicked.connect(self.leave_room)
        self.leave_room_button.setEnabled(False)

        self.current_room_label = QLabel("No active room")
        self.current_room_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_room_label.setStyleSheet("color: #facc15; font-weight: bold;")

        self.general_chat_log = QTextEdit()
        self.general_chat_log.setReadOnly(True)
        self.general_chat_log.setPlaceholderText("General chat and room messages")

        self.direct_chat_log = QTextEdit()
        self.direct_chat_log.setReadOnly(True)
        self.direct_chat_log.setPlaceholderText("Direct messages")

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_to_server)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect_from_server)
        self.disconnect_button.setEnabled(False)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setEnabled(False)

        self.direct_button = QPushButton("Send Direct")
        self.direct_button.clicked.connect(self.send_direct_message)
        self.direct_button.setEnabled(False)

        self.send_room_button = QPushButton("Send Room")
        self.send_room_button.clicked.connect(self.send_room_message)
        self.send_room_button.setEnabled(False)

        self.file_button = QPushButton("Send File")
        self.file_button.clicked.connect(self.send_file)
        self.file_button.setEnabled(False)

        self.build_ui()
        self.apply_styles()

    def build_ui(self) -> None:
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Host:"))
        control_layout.addWidget(self.host_input)
        control_layout.addWidget(QLabel("Port:"))
        control_layout.addWidget(self.port_input)
        control_layout.addWidget(QLabel("Username:"))
        control_layout.addWidget(self.username_input)
        control_layout.addWidget(QLabel("Password:"))
        control_layout.addWidget(self.password_input)
        control_layout.addWidget(self.connect_button)
        control_layout.addWidget(self.disconnect_button)

        message_layout = QHBoxLayout()
        message_layout.addWidget(self.message_input, stretch=4)
        message_layout.addWidget(self.send_button)
        message_layout.addWidget(self.send_room_button)
        message_layout.addWidget(self.direct_button)
        message_layout.addWidget(self.file_button)

        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("Online Users"))
        list_layout.addWidget(self.search_input)
        list_layout.addWidget(self.user_list)

        room_layout = QHBoxLayout()
        room_layout.addWidget(self.room_name_input)
        room_layout.addWidget(self.create_room_button)
        room_layout.addWidget(self.join_room_button)
        room_layout.addWidget(self.leave_room_button)

        chat_split_layout = QHBoxLayout()
        chat_split_layout.addWidget(self.general_chat_log, stretch=3)
        chat_split_layout.addWidget(self.direct_chat_log, stretch=2)

        main_layout = QVBoxLayout()
        main_layout.addLayout(control_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(room_layout)
        main_layout.addWidget(self.current_room_label)
        main_layout.addLayout(chat_split_layout)
        main_layout.addLayout(message_layout)
        main_layout.addLayout(list_layout)

        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #111827; color: #e5e7eb; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #9ca3af; font-size: 13px; }
            QTextEdit, QListWidget, QLineEdit { background: #1f2937; border: 1px solid #374151; border-radius: 10px; color: #e5e7eb; }
            QTextEdit { padding: 10px; }
            QLineEdit { min-height: 34px; }
            QPushButton { background: #2563eb; color: #ffffff; border: none; border-radius: 10px; min-height: 36px; padding: 0 16px; }
            QPushButton:hover { background: #3b82f6; }
            QPushButton:disabled { background: #374151; color: #6b7280; }
            """
        )
        self.chat_log.setStyleSheet("background: #111827; border: 1px solid #334155; border-radius: 10px;")
        self.user_list.setStyleSheet("background: #0f172a; border: 1px solid #334155; border-radius: 10px;")

    def connect_to_server(self) -> None:
        if self.client.is_connected():
            return

        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        host = self.host_input.text().strip() or "127.0.0.1"
        port_text = self.port_input.text().strip() or "1050"

        if len(username) < 3:
            QMessageBox.warning(self, "Invalid Username", "Username must be at least 3 characters.")
            return

        if not password:
            QMessageBox.warning(self, "Password Required", "Please enter the shared password.")
            return

        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Port", "Port must be a number.")
            return

        device_name = platform.node() or "Unknown Device"

        try:
            self.client.connect(host, port, username, password, self.events.event_received.emit, device_name=device_name)
            self.current_username = username
            self.set_connected_state(True)
            self.append_log(f"<span style='color:#7dd3fc;'>Connected to {host}:{port} as {username} ({device_name})</span>")
        except RuntimeError as exc:
            QMessageBox.critical(self, "Connection Failed", str(exc))
            self.set_connected_state(False)
        except Exception as exc:
            QMessageBox.critical(self, "Connection Failed", str(exc))
            self.set_connected_state(False)

    def disconnect_from_server(self) -> None:
        if self.client.is_connected():
            self.client.disconnect()
        self.current_username = ""
        self.set_connected_state(False)
        self.append_log("<span style='color:#f97316;'>Disconnected.</span>")

    def send_message(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return

        message = self.message_input.text().strip()
        if not message:
            return

        self.client.send_message(message)
        self.append_log(f"<strong style='color:#ffffff;'>You:</strong> {message}")
        self.message_input.clear()

    def send_direct_message(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return

        selected = self.user_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "No Recipient", "Select a user from the online list first.")
            return

        message = self.message_input.text().strip()
        if not message:
            return

        target = selected.data(Qt.ItemDataRole.UserRole) or selected.text()
        self.client.send_message(message, direct_target=target)
        self.append_direct_log(f"<strong style='color:#ffffff;'>You -> {target}:</strong> {message}")
        self.message_input.clear()

    def send_room_message(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return

        if not self.current_room:
            QMessageBox.warning(self, "No Room Selected", "Create or join a room before sending room messages.")
            return

        message = self.message_input.text().strip()
        if not message:
            return

        self.client.send_message(message, room_name=self.current_room)
        self.append_general_log(f"<strong style='color:#ffffff;'>You [{self.current_room}]:</strong> {message}")
        self.message_input.clear()

    def send_file(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Select a file to send", "", "All Files (*.*)")
        if not file_path:
            return

        try:
            self.client.send_file(file_path)
            file_name = file_path.split("/")[-1].split("\\")[-1]
            self.append_log(f"<strong style='color:#ffffff;'>You sent file:</strong> {file_name}")
        except Exception as exc:
            QMessageBox.critical(self, "File Send Failed", str(exc))

    def on_network_event(self, event: object) -> None:
        if not isinstance(event, dict):
            return
        event_type = event.get("type")
        if event_type == "log":
            self.append_log(f"<span style='color:#93c5fd;'>{event.get('message', '')}</span>")
        elif event_type == "chat":
            sender = event.get('sender')
            if sender == self.current_username:
                return
            color = self.get_user_color(sender)
            self.append_general_log(f"<strong style='color:{color};'>{sender}</strong>: {event.get('message')}")
        elif event_type == "direct":
            sender = event.get('sender')
            if sender == self.current_username:
                return
            target = event.get('target')
            sender_color = self.get_user_color(sender)
            target_color = self.get_user_color(target)
            self.append_direct_log(
                f"<strong style='color:{sender_color};'>{sender}</strong> -> "
                f"<strong style='color:{target_color};'>{target}</strong>: {event.get('message')}"
            )
        elif event_type == "room":
            room_name = event.get('room_name', '')
            sender = event.get('sender')
            if sender == self.current_username:
                return
            self.append_general_log(f"<strong style='color:#60a5fa;'>[{room_name}] {sender}:</strong> {event.get('message')}")
        elif event_type == "room_system":
            room_name = event.get('room_name', '')
            message = event.get('message', '')
            self.append_general_log(f"<span style='color:#f59e0b;'>[ROOM {room_name}] {message}</span>")
            if "created and joined" in message or "joined" in message:
                self.set_current_room(room_name)
            elif message.startswith("You left room") or message.endswith(f"left {room_name}."):
                if self.current_room == room_name:
                    self.set_current_room("")
        elif event_type == "system":
            self.append_general_log(f"<strong>[SYSTEM]</strong> {event.get('message')}")
        elif event_type == "file":
            sender = event.get("sender")
            filename = event.get("filename", "unknown")
            self.append_log(f"<strong style='color:#ffffff;'>{sender}</strong> sent file: {filename}")
            self.save_received_file(filename, event.get("content", ""))
        elif event_type == "user_list":
            self.update_user_list(event.get('users', []))
        elif event_type == "error":
            self.append_log(f"<span style='color:#fb7185;'>[ERROR]</span> {event.get('message')}")
        elif event_type == "status" and event.get("status") == "disconnected":
            self.set_connected_state(False)
            self.append_log("<span style='color:#f97316;'>Server disconnected.</span>")

    def append_general_log(self, message: str) -> None:
        self.general_chat_log.append(message)
        self.general_chat_log.ensureCursorVisible()

    def append_direct_log(self, message: str) -> None:
        self.direct_chat_log.append(message)
        self.direct_chat_log.ensureCursorVisible()

    def append_log(self, message: str) -> None:
        self.general_chat_log.append(message)
        self.general_chat_log.ensureCursorVisible()

    def set_current_room(self, room_name: str) -> None:
        self.current_room = room_name or ""
        self.current_room_label.setText(f"Active room: {self.current_room}" if self.current_room else "No active room")
        self.leave_room_button.setEnabled(bool(self.current_room))
        self.send_room_button.setEnabled(bool(self.current_room))

    def create_room(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return
        room_name = self.room_name_input.text().strip()
        if not room_name:
            QMessageBox.warning(self, "Invalid Room", "Enter a room name to create.")
            return
        self.client.send_packet({"type": "create_room", "room_name": room_name})

    def join_room(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return
        room_name = self.room_name_input.text().strip()
        if not room_name:
            QMessageBox.warning(self, "Invalid Room", "Enter a room name to join.")
            return
        self.client.send_packet({"type": "join_room", "room_name": room_name})

    def leave_room(self) -> None:
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to the server first.")
            return
        if not self.current_room:
            QMessageBox.warning(self, "No Room Selected", "No room is currently active.")
            return
        self.client.send_packet({"type": "leave_room", "room_name": self.current_room})
        self.set_current_room("")

    def update_user_list(self, users: list) -> None:
        self.all_users = users
        self.filter_user_list()

    def filter_user_list(self) -> None:
        search_text = self.search_input.text().strip().lower()
        self.user_list.clear()
        for entry in self.all_users:
            if isinstance(entry, dict):
                username = entry.get("username", "")
                device_name = entry.get("device_name", "")
                display_text = f"{username} ({device_name})" if device_name else username
                if search_text and search_text not in username.lower() and search_text not in device_name.lower() and search_text not in display_text.lower():
                    continue
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, username)
                self.user_list.addItem(item)
            else:
                display_text = str(entry)
                if search_text and search_text not in display_text.lower():
                    continue
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, display_text)
                self.user_list.addItem(item)

    def get_user_color(self, username: str) -> str:
        if username == self.username_input.text().strip():
            return "#ffffff"
        if username not in self.user_colors:
            palette = ["#38bdf8", "#fbbf24", "#a3e635", "#f472b6", "#60a5fa", "#f97316", "#8b5cf6", "#22c55e"]
            self.user_colors[username] = palette[len(self.user_colors) % len(palette)]
        return self.user_colors[username]

    def save_received_file(self, filename: str, content_b64: str) -> None:
        if not content_b64:
            return
        try:
            file_bytes = base64.b64decode(content_b64)
        except Exception:
            self.append_log(f"<span style='color:#fb7185;'>[ERROR]</span> Failed to decode received file {filename}")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save received file", filename)
        if not save_path:
            self.append_log(f"<span style='color:#fb7185;'>[ERROR]</span> File save canceled for {filename}")
            return
        try:
            with open(save_path, "wb") as f:
                f.write(file_bytes)
            self.append_log(f"<span style='color:#22c55e;'>File saved:</span> {save_path}")
        except Exception as exc:
            self.append_log(f"<span style='color:#fb7185;'>[ERROR]</span> Could not save file: {exc}")

    def set_connected_state(self, connected: bool) -> None:
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.send_button.setEnabled(connected)
        self.direct_button.setEnabled(connected)
        self.file_button.setEnabled(connected)
        self.status_label.setText("Connected" if connected else "Disconnected")

    def closeEvent(self, event) -> None:
        self.disconnect_from_server()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = ChatClientWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
