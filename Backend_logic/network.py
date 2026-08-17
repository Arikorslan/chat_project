from __future__ import annotations

import base64
import json
import os
import socket
import struct
import threading
import time
from typing import Callable, Dict, Optional

from .payload import get_salt
from .secure_traffic import SecureTraffic

MAX_PACKET = 8192
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
HISTORY_LIMIT = 200


def _recv_exact(sock: socket.socket, size: int) -> Optional[bytes]:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class ChatServer:
    def __init__(self, password: str, host: str = "0.0.0.0", port: int = 1050, event_callback: Optional[Callable] = None):
        self.host = host
        self.port = int(port)
        self.password = password or "chat-secret"
        self.event_callback = event_callback
        self.encryptor = SecureTraffic.from_password(self.password.encode("utf-8"), get_salt())
        self.clients: Dict[str, Dict] = {}
        self.rooms: Dict[str, set[str]] = {}
        self.public_history: list[Dict] = []
        self.room_history: Dict[str, list[Dict]] = {}
        self.suspended_users: set[str] = set()
        self.lock = threading.RLock()
        self.running = False
        self.server_socket: Optional[socket.socket] = None

    def log(self, message: str) -> None:
        if self.event_callback:
            self.event_callback({"type": "log", "message": message})

    def user_list_changed(self) -> None:
        if self.event_callback:
            self.event_callback({"type": "user_list", "users": self.build_user_list()})

    def start(self) -> None:
        if self.running:
            return
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.running = True
        threading.Thread(target=self.accept_loop, daemon=True).start()
        self.log(f"Server started on {self.host}:{self.port}")

    def accept_loop(self) -> None:
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                self.log(f"Incoming connection from {client_address}")
                threading.Thread(target=self.handle_client, args=(client_socket, client_address), daemon=True).start()
            except OSError:
                break
            except Exception as exc:
                self.log(f"Accept failed: {exc}")

    def handle_client(self, client_socket: socket.socket, client_address) -> None:
        username = None
        try:
            packet = self.receive_packet(client_socket)
            if not packet or packet.get("type") != "auth" or not packet.get("username"):
                self.log(f"Invalid auth packet from {client_address}")
                client_socket.close()
                return

            username = packet["username"]
            device_name = packet.get("device_name", "Unknown Device")

            if username in self.suspended_users:
                self.send_packet(client_socket, {"type": "error", "message": "account_suspended"})
                client_socket.close()
                return

            with self.lock:
                if username in self.clients:
                    self.send_packet(client_socket, {"type": "error", "message": "username_taken"})
                    client_socket.close()
                    return
                self.clients[username] = {
                    "socket": client_socket,
                    "address": client_address,
                    "device_name": device_name,
                    "connected_at": time.time(),
                    "status": STATUS_ONLINE,
                    "last_seen": time.time(),
                }

            self.log(f"{username} ({device_name}) joined the chat")
            self.broadcast_system(f"{username} joined the chat")
            self.broadcast_user_list()
            self.send_packet(client_socket, {"type": "system", "message": "connected"})
            # send recent public history so the client can catch up
            try:
                self.send_history_to_client(username)
            except Exception:
                pass
            self.client_loop(username)
        except Exception as exc:
            self.log(f"Client error [{client_address}]: {exc}")
        finally:
            if username:
                self.remove_client(username)
            else:
                try:
                    client_socket.close()
                except Exception:
                    pass

    def client_loop(self, username: str) -> None:
        client_socket = self.clients[username]["socket"]
        while self.running:
            packet = self.receive_packet(client_socket)
            if packet is None:
                break
            if packet.get("type") == "disconnect":
                break
            self.process_message(username, packet)

    def process_message(self, sender: str, packet: Dict) -> None:
        packet_type = packet.get("type")
        timestamp = time.time()
        message_id = packet.get("message_id", "")
        if packet_type == "chat":
            self.broadcast_chat(sender, packet.get("message", ""), message_id=message_id, timestamp=timestamp)
        elif packet_type == "direct":
            target = packet.get("target", "")
            self.send_direct(sender, target, packet.get("message", ""), message_id=message_id, timestamp=timestamp)
        elif packet_type == "room":
            room_name = packet.get("room_name", "").strip()
            if not room_name or sender not in self.rooms.get(room_name, set()):
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": "not_in_room"})
                return
            self.save_room_message(room_name, sender, packet.get("message", ""), timestamp, message_id)
            self.broadcast_room(room_name, {
                "type": "room",
                "room_name": room_name,
                "sender": sender,
                "message": packet.get("message", ""),
                "timestamp": timestamp,
                "message_id": message_id,
            })
        elif packet_type == "create_room":
            room_name = packet.get("room_name", "").strip()
            if not room_name:
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": "invalid_room_name"})
                return
            if room_name in self.rooms:
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": "room_exists"})
                return
            self.rooms[room_name] = {sender}
            self.send_packet(self.clients[sender]["socket"], {"type": "room_system", "room_name": room_name, "message": f"Room '{room_name}' created and joined."})
            # initialize room history
            self.room_history.setdefault(room_name, [])
        elif packet_type == "join_room":
            room_name = packet.get("room_name", "").strip()
            if not room_name or room_name not in self.rooms:
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": "room_not_found"})
                return
            self.rooms[room_name].add(sender)
            self.broadcast_room(room_name, {"type": "room_system", "room_name": room_name, "message": f"{sender} joined {room_name}."})
            # send recent room history to the joining user
            try:
                self.send_room_history_to_client(sender, room_name)
            except Exception:
                pass
        elif packet_type == "leave_room":
            room_name = packet.get("room_name", "").strip()
            if not room_name or room_name not in self.rooms or sender not in self.rooms[room_name]:
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": "not_in_room"})
                return
            self.rooms[room_name].remove(sender)
            self.send_packet(self.clients[sender]["socket"], {"type": "room_system", "room_name": room_name, "message": f"You left room {room_name}."})
            if self.rooms[room_name]:
                self.broadcast_room(room_name, {"type": "room_system", "room_name": room_name, "message": f"{sender} left {room_name}."})
            else:
                del self.rooms[room_name]
        elif packet_type == "file":
            file_name = packet.get("filename", "unknown")
            content_b64 = packet.get("content", "")
            try:
                base64.b64decode(content_b64)
            except Exception:
                self.log(f"Invalid file content from {sender}")
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": "invalid_file_content"})
                return

            self.broadcast_file(sender, file_name, content_b64)
        else:
            self.log(f"Unhandled packet type from {sender}: {packet_type}")

    def broadcast_chat(self, sender: str, message: str, message_id: str = "", timestamp: Optional[float] = None) -> None:
        if timestamp is None:
            timestamp = time.time()
        # save to public history and broadcast
        self.save_public_message(sender, message, timestamp, message_id)
        self.broadcast({"type": "chat", "sender": sender, "message": message, "timestamp": timestamp, "message_id": message_id})

    def broadcast_system(self, message: str) -> None:
        self.broadcast({"type": "system", "message": message, "timestamp": time.time()})

    def broadcast(self, packet: Dict) -> None:
        with self.lock:
            for user, client in list(self.clients.items()):
                try:
                    self.send_packet(client["socket"], packet)
                except Exception as exc:
                    self.log(f"Failed to send to {user}: {exc}")
                    self.remove_client(user)

    def broadcast_file(self, sender: str, filename: str, content_b64: str) -> None:
        packet = {"type": "file", "sender": sender, "filename": filename, "content": content_b64, "timestamp": time.time()}
        self.broadcast(packet)

    def broadcast_user_list(self) -> None:
        self.user_list_changed()
        self.broadcast({"type": "user_list", "users": self.build_user_list(), "timestamp": time.time()})

    def build_user_list(self) -> list[Dict[str, str]]:
        return [
            {
                "username": user,
                "device_name": client.get("device_name", "Unknown Device"),
                "status": client.get("status", STATUS_ONLINE),
                "last_seen": client.get("last_seen", 0),
            }
            for user, client in self.clients.items()
        ]

    def send_direct(self, sender: str, target: str, message: str, message_id: str, timestamp: float) -> None:
        with self.lock:
            target_client = self.clients.get(target)
            packet = {"type": "direct", "sender": sender, "target": target, "message": message, "timestamp": timestamp, "message_id": message_id}
            if target_client:
                self.send_packet(target_client["socket"], packet)
                self.send_packet(self.clients[sender]["socket"], packet)
            else:
                self.send_packet(self.clients[sender]["socket"], {"type": "error", "message": f"Target {target} is not online"})

    def broadcast_room(self, room_name: str, packet: Dict) -> None:
        members = self.rooms.get(room_name, set())
        with self.lock:
            for username in list(members):
                client = self.clients.get(username)
                if client:
                    try:
                        self.send_packet(client["socket"], packet)
                    except Exception as exc:
                        self.log(f"Failed to send room message to {username}: {exc}")
                        self.remove_client(username)

    def save_room_message(self, room_name: str, sender: str, message: str, timestamp: float, message_id: str) -> None:
        if room_name not in self.room_history:
            self.room_history[room_name] = []
        entry = {"sender": sender, "message": message, "timestamp": timestamp, "message_id": message_id}
        self.room_history[room_name].append(entry)
        # cap history
        if len(self.room_history[room_name]) > HISTORY_LIMIT:
            self.room_history[room_name] = self.room_history[room_name][-HISTORY_LIMIT:]

    def save_public_message(self, sender: str, message: str, timestamp: float, message_id: str) -> None:
        entry = {"sender": sender, "message": message, "timestamp": timestamp, "message_id": message_id}
        self.public_history.append(entry)
        if len(self.public_history) > HISTORY_LIMIT:
            self.public_history = self.public_history[-HISTORY_LIMIT:]

    def send_history_to_client(self, username: str) -> None:
        # send recent public chat history to a newly connected client
        client = self.clients.get(username)
        if not client:
            return
        try:
            self.send_packet(client["socket"], {"type": "history", "scope": "public", "messages": list(self.public_history)})
        except Exception as exc:
            self.log(f"Failed to send public history to {username}: {exc}")

    def send_room_history_to_client(self, username: str, room_name: str) -> None:
        client = self.clients.get(username)
        if not client:
            return
        messages = self.room_history.get(room_name, [])
        try:
            self.send_packet(client["socket"], {"type": "history", "scope": "room", "room_name": room_name, "messages": list(messages)})
        except Exception as exc:
            self.log(f"Failed to send room history to {username} for {room_name}: {exc}")

    def send_packet(self, client_socket: socket.socket, packet: Dict) -> None:
        payload = json.dumps(packet, separators=("," ,":"), ensure_ascii=False).encode("utf-8")
        ciphertext = self.encryptor.encrypt(payload)
        header = struct.pack("!I", len(ciphertext))
        client_socket.sendall(header + ciphertext)

    def receive_packet(self, client_socket: socket.socket) -> Optional[Dict]:
        header = _recv_exact(client_socket, 4)
        if not header:
            return None
        length = struct.unpack("!I", header)[0]
        raw = _recv_exact(client_socket, length)
        if not raw:
            return None
        try:
            plaintext = self.encryptor.decrypt(raw)
            return json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            self.log(f"Receive packet failed: {exc}")
            return None

    def remove_client(self, username: str) -> None:
        with self.lock:
            client = self.clients.pop(username, None)
            for room_name, members in list(self.rooms.items()):
                if username in members:
                    members.remove(username)
                    if members:
                        self.broadcast_room(room_name, {"type": "room_system", "room_name": room_name, "message": f"{username} left {room_name}."})
                    else:
                        del self.rooms[room_name]
        if client:
            try:
                client["socket"].close()
            except Exception:
                pass
            self.log(f"{username} left the chat")
            self.broadcast_system(f"{username} left the chat")
            self.broadcast_user_list()

    def disconnect_user(self, username: str) -> None:
        with self.lock:
            client = self.clients.get(username)
            if not client:
                return
            try:
                self.send_packet(client["socket"], {"type": "system", "message": "Disconnected by administrator."})
                client["socket"].close()
            except Exception as exc:
                self.log(f"Could not disconnect {username}: {exc}")
            finally:
                self.remove_client(username)

    def suspend_user(self, username: str) -> None:
        with self.lock:
            self.suspended_users.add(username)
            client = self.clients.get(username)
            if client:
                try:
                    self.send_packet(client["socket"], {"type": "system", "message": "Your account has been suspended."})
                    client["socket"].close()
                except Exception as exc:
                    self.log(f"Could not suspend {username}: {exc}")
                finally:
                    self.remove_client(username)

    def shutdown(self) -> None:
        self.running = False
        with self.lock:
            for client in list(self.clients.values()):
                try:
                    client["socket"].close()
                except Exception:
                    pass
            self.clients.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        self.log("Server shutdown complete")


class ChatClient:
    def __init__(self) -> None:
        self.socket: Optional[socket.socket] = None
        self.encryptor: Optional[SecureTraffic] = None
        self.username: str = ""
        self.running = False
        self.receiver_thread: Optional[threading.Thread] = None
        self.event_callback: Optional[Callable] = None

    def connect(self, host: str, port: int, username: str, shared_password: str, event_callback: Callable, device_name: str = "Unknown Device") -> None:
        if self.running:
            raise RuntimeError("Already connected")
        self.username = username
        self.encryptor = SecureTraffic.from_password(shared_password.encode("utf-8"), get_salt())
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, int(port)))
        self.socket.settimeout(5.0)
        try:
            auth_payload = {
                "type": "auth",
                "username": username,
                "device_name": device_name,
            }
            self.send_packet(auth_payload)
            packet = self.receive_packet(self.socket)
        finally:
            self.socket.settimeout(None)

        if packet is None:
            raise RuntimeError("Server closed the connection")

        if packet.get("type") == "error":
            raise RuntimeError(packet.get("message", "Authentication failed"))

        self.running = True
        self.event_callback = event_callback
        self.receiver_thread = threading.Thread(target=self.receive_loop, daemon=True)
        self.receiver_thread.start()
        if self.event_callback:
            self.event_callback(packet)

    def receive_loop(self) -> None:
        while self.running and self.socket:
            packet = self.receive_packet(self.socket)
            if packet is None:
                break
            if self.event_callback:
                self.event_callback(packet)
        self.running = False
        if self.event_callback:
            self.event_callback({"type": "status", "status": "disconnected"})

    def send_packet(self, packet: Dict) -> None:
        if not self.socket or not self.encryptor:
            raise RuntimeError("Client is not connected")
        payload = json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ciphertext = self.encryptor.encrypt(payload)
        header = struct.pack("!I", len(ciphertext))
        self.socket.sendall(header + ciphertext)

    def receive_packet(self, client_socket: socket.socket) -> Optional[Dict]:
        header = _recv_exact(client_socket, 4)
        if not header:
            return None
        length = struct.unpack("!I", header)[0]
        raw = _recv_exact(client_socket, length)
        if not raw:
            return None
        plaintext = self.encryptor.decrypt(raw)
        return json.loads(plaintext.decode("utf-8"))

    def send_message(self, message: str, direct_target: str = "", room_name: str = "") -> None:
        if room_name:
            packet = {"type": "room", "room_name": room_name, "message": message}
        elif direct_target:
            packet = {"type": "direct", "target": direct_target, "message": message}
        else:
            packet = {"type": "chat", "message": message}
        self.send_packet(packet)

    def send_file(self, file_path: str) -> None:
        if not os.path.isfile(file_path):
            raise RuntimeError("File not found.")
        file_size = os.path.getsize(file_path)
        if file_size > 2 * 1024 * 1024:
            raise RuntimeError("File must be smaller than 2 MB.")
        with open(file_path, "rb") as file_handle:
            content_b64 = base64.b64encode(file_handle.read()).decode("utf-8")
        packet = {
            "type": "file",
            "filename": os.path.basename(file_path),
            "content": content_b64,
        }
        self.send_packet(packet)

    def disconnect(self) -> None:
        if self.running:
            try:
                self.send_packet({"type": "disconnect"})
            except Exception:
                pass
            self.running = False
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None

    def is_connected(self) -> bool:
        return self.running and self.socket is not None
