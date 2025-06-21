import socket
import time
import os
from threading import Thread

class NetworkHandler:
    def __init__(self, config):
        self.config = config
        self.running = True
        self.image_transfer_info = {} # {(ip, port): (groesse, handle)}
        self.handle = self.config['user']['handle']
        self.port = self.config['user']['port']
        self.broadcast_port = self.config['user']['whoisport']
        self.broadcast_address = '255.255.255.255'
        
        self.groups = ['default']  # Alle beigetretenen Gruppen
        self.active_group = 'default'  # Gruppe zum Senden von Nachrichten
        self.users_by_group = {'default': {}}  # {gruppe: {handle: (ip, port)}}

        # Socket für Unicast-Nachrichten (Senden und Empfangen)
        self.unicast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.unicast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.unicast_socket.bind(('0.0.0.0', self.port))

        # Socket für Broadcast-Nachrichten (Senden und Empfangen)
        self.broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.broadcast_socket.bind(('0.0.0.0', self.broadcast_port))

        # Listener-Threads starten
        self.unicast_listener = Thread(target=self._listen_unicast)
        self.unicast_listener.daemon = True
        self.unicast_listener.start()

        self.broadcast_listener = Thread(target=self._listen_broadcast)
        self.broadcast_listener.daemon = True
        self.broadcast_listener.start()

        # Periodische Ankündigungen und Bereinigung der Benutzerliste starten
        self.periodic_thread = Thread(target=self._periodic_tasks)
        self.periodic_thread.daemon = True
        self.periodic_thread.start()

        # Anwesenheit beim Start ankündigen
        self.announce_presence()

    def _listen_unicast(self):
        """Listens for direct messages."""
        while self.running:
            try:
                # Einen größeren Puffer für potenzielle Bilddaten verwenden
                data, addr = self.unicast_socket.recvfrom(65535) 
                
                # Prüfen, ob wir ein Bild von dieser Adresse erwarten
                if addr in self.image_transfer_info:
                    size, handle = self.image_transfer_info.pop(addr)
                    if len(data) == size:
                        self._save_image(data, handle)
                    else:
                        print(f"\nBildempfang von {handle} fehlgeschlagen: Größen stimmen nicht überein (erwartet: {size}, erhalten: {len(data)}).")
                        print("> ", end="", flush=True)
                else:
                    # Es ist ein normaler Textbefehl
                    message = data.decode('utf-8').strip()
                    self._handle_unicast_message(message, addr)
            except OSError:
                if self.running:
                    break
            except Exception as e:
                if self.running:
                    print(f"\nUnicast-Fehler: {e}")

    def _listen_broadcast(self):
        """Listens for discovery and group messages."""
        while self.running:
            try:
                data, addr = self.broadcast_socket.recvfrom(1024)
                message = data.decode('utf-8').strip()
                self._handle_broadcast_message(message, addr)
            except OSError:
                if self.running:
                    break
            except Exception as e:
                if self.running:
                    print(f"\nBroadcast-Fehler: {e}")

    def _handle_unicast_message(self, message, addr):
        """Handles direct messages like MSG and REPLY."""
        parts = message.split(' ', 1)
        command = parts[0]
        args_str = parts[1] if len(parts) > 1 else ""

        if command == "MSG":
            # MSG <Absender> <Text>
            try:
                sender, text = args_str.split(' ', 1)
                print(f"\n[{sender} -> mir]: {text}\n> ", end="", flush=True)

                # Auto-Antwort-Logik
                autoreply_msg = self.config['user'].get('autoreply')
                if autoreply_msg:
                    sender_info = None
                    for group in self.users_by_group.values():
                        if sender in group:
                            sender_info = group[sender]
                            break
                    
                    if sender_info:
                        ip, port, _ = sender_info
                        # Einen spezifischen Auto-Antwort-Befehl senden, um Schleifen zu vermeiden
                        reply_text = f"MSG-AUTOREPLY {self.handle} {autoreply_msg}"
                        self.unicast_socket.sendto(reply_text.encode('utf-8'), (ip, port))
            except (ValueError, IndexError):
                pass # Ignoriere fehlerhafte MSG
        
        elif command == "MSG-AUTOREPLY":
            # MSG-AUTOREPLY <Absender> <Text>
            try:
                sender, text = args_str.split(' ', 1)
                print(f"\n[Auto-Reply von {sender}]: {text}\n> ", end="", flush=True)
            except (ValueError, IndexError):
                pass # Ignoriere fehlerhafte Auto-Antwort

        elif command == "IMG":
            # IMG <Absender_Handle> <Größe>
            try:
                sender, size_str = args_str.rsplit(' ', 1)
                size = int(size_str)
                self.image_transfer_info[addr] = (size, sender)
                print(f"\nEingehendes Bild von {sender} ({size} bytes). Warte auf Daten...")
                print("> ", end="", flush=True)
            except (ValueError, IndexError):
                print(f"\nUngültige IMG-Nachricht empfangen: {args_str}")
                print("> ", end="", flush=True)

        elif command == "REPLY":
            # ANTWORT <Gruppe> <Handle> <Port>
            try:
                # Sicher parsen: Gruppe ist das erste Wort, Port ist das letzte, Handle ist in der Mitte
                parts = args_str.split(' ', 1)
                group = parts[0]
                handle_and_port = parts[1]
                
                handle, port_str = handle_and_port.rsplit(' ', 1)
                port = int(port_str)

                if not (handle == self.handle and port == self.port):
                    if group in self.users_by_group and handle not in self.users_by_group[group]:
                        self.users_by_group[group][handle] = (addr[0], port, time.time())
                        print(f"\nNutzer '{handle}' in Gruppe '{group}' gefunden.")
                        print("> ", end="", flush=True)
            except (ValueError, IndexError):
                pass # Ignoriere fehlerhafte REPLY

    def _handle_broadcast_message(self, message, addr):
        """Handles discovery messages like ALIVE, JOIN, LEAVE and GMSG."""
        parts = message.split(' ', 1)
        command = parts[0]
        args_str = parts[1] if len(parts) > 1 else ""
        ip = addr[0]

        if command not in ["ALIVE", "JOIN", "LEAVE", "GMSG"]:
            return

        # Gruppe extrahieren, die bei diesen Befehlen immer das erste Argument ist
        group_parts = args_str.split(' ', 1)
        group = group_parts[0]
        
        if not group or group not in self.groups:
            return

        remaining_args_str = group_parts[1] if len(group_parts) > 1 else ""

        if command == "ALIVE":
            # LEBENSZEICHEN <Gruppe> <Handle> <Port> -> verbleibend: <Handle> <Port>
            args = remaining_args_str.rsplit(' ', 1)
            if len(args) != 2:
                return
            handle, port_str = args
            try:
                port = int(port_str)
                if not (handle == self.handle and port == self.port):
                    if group in self.users_by_group:
                        self.users_by_group[group][handle] = (ip, port, time.time())
            except ValueError:
                pass

        elif command == "JOIN":
            # BEITRETEN <Gruppe> <Handle> <Port> -> verbleibend: <Handle> <Port>
            args = remaining_args_str.rsplit(' ', 1)
            if len(args) != 2:
                return
            handle, port_str = args
            try:
                port = int(port_str)
                if not (handle == self.handle and port == self.port):
                    if group in self.users_by_group and handle not in self.users_by_group[group]:
                        self.users_by_group[group][handle] = (ip, port, time.time())
                        print(f"\n{handle} ist Gruppe '{group}' beigetreten.")
                        reply_msg = f"REPLY {group} {self.handle} {self.port}"
                        self.unicast_socket.sendto(reply_msg.encode('utf-8'), (ip, port))
                        print("> ", end="", flush=True)
            except ValueError:
                pass

        elif command == "LEAVE":
            # VERLASSEN <Gruppe> <Handle> -> verbleibend: <Handle>
            handle = remaining_args_str
            if not handle: return
            if group in self.users_by_group and handle in self.users_by_group[group]:
                del self.users_by_group[group][handle]
                print(f"\n{handle} hat Gruppe '{group}' verlassen.\n> ", end="", flush=True)
        
        elif command == "GMSG":
            # GMSG <Gruppe> <Handle> <Text> -> verbleibend: <Handle> <Text>
            args = remaining_args_str.split(' ', 1)
            if len(args) < 2: return
            sender, text = args
            if sender != self.handle:
                print(f"\n[{group}] {sender}: {text}\n> ", end="", flush=True)


    def discover_users(self, group_name=None):
        """Prints the list of known users in a group."""
        group_to_scan = group_name if group_name is not None else self.active_group
        if not group_to_scan:
            print("\nKeine aktive Gruppe zum Anzeigen.")
            print("> ", end="", flush=True)
            return

        print(f"\nBekannte Nutzer in Gruppe '{group_to_scan}':")
        
        known_users = self.users_by_group.get(group_to_scan, {})
        
        if not known_users:
            print(f"Keine anderen Nutzer in '{group_to_scan}' gefunden.")
        else:
            print(f"Aktive Nutzer in '{group_to_scan}':")
            for handle in known_users:
                print(f"- {handle}")
        print("> ", end="", flush=True)


    def announce_presence(self, group_name=None):
        """Broadcasts a JOIN message to one or all currently joined groups."""
        groups_to_announce = [group_name] if group_name else self.groups
        for group in groups_to_announce:
            join_msg = f"JOIN {group} {self.handle} {self.port}"
            self.broadcast_socket.sendto(join_msg.encode('utf-8'), (self.broadcast_address, self.broadcast_port))

    def send_message(self, handle, text):
        """Sends a message to a specific user, searching across all groups."""
        user_info = None
        for group in self.users_by_group:
            if handle in self.users_by_group[group]:
                user_info = self.users_by_group[group][handle]
                break
        
        if user_info:
            ip, port, _ = user_info
            msg = f"MSG {self.handle} {text}"
            self.unicast_socket.sendto(msg.encode('utf-8'), (ip, port))
        else:
            print(f"\nNutzer '{handle}' nicht gefunden. 'who' in der jeweiligen Gruppe ausführen.")
        print("> ", end="", flush=True)

    def send_group_message(self, text):
        """Broadcasts a message to the active group."""
        if not self.active_group:
            print("\nKeine aktive Gruppe ausgewählt. Mit /switch <gruppe> wechseln.")
            print("> ", end="", flush=True)
            return
        msg = f"GMSG {self.active_group} {self.handle} {text}"
        self.broadcast_socket.sendto(msg.encode('utf-8'), (self.broadcast_address, self.broadcast_port))
        print("> ", end="", flush=True)

    def _send_leave_broadcast(self, group_name):
        leave_msg = f"LEAVE {group_name} {self.handle}"
        try:
            self.broadcast_socket.sendto(leave_msg.encode('utf-8'), (self.broadcast_address, self.broadcast_port))
        except Exception as e:
            print(f"Error sending leave broadcast for group {group_name}: {e}")

    def leave_group(self, group_name):
        """Leaves a specific group."""
        if group_name not in self.groups:
            print(f"\nDu bist nicht in Gruppe '{group_name}'.")
            print("> ", end="", flush=True)
            return

        print(f"\nVerlasse Gruppe '{group_name}'...")
        self._send_leave_broadcast(group_name)

        self.groups.remove(group_name)
        if group_name in self.users_by_group:
            del self.users_by_group[group_name]
        
        print(f"Gruppe '{group_name}' verlassen.")

        if self.active_group == group_name:
            if self.groups:
                self.active_group = self.groups[0]
                print(f"Aktive Gruppe ist jetzt '{self.active_group}'.")
            else:
                self.active_group = None
                print("Du bist in keiner Gruppe mehr. Trete einer mit /join bei.")
        print("> ", end="", flush=True)

    def join_group(self, group_name):
        """Joins a new group and sets it as active."""
        if group_name in self.groups:
            self.active_group = group_name
            print(f"\nDu bist bereits in Gruppe '{group_name}'. Sie ist jetzt aktiv.")
            print("> ", end="", flush=True)
            return

        print(f"\nTrete Gruppe '{group_name}' bei...")
        self.groups.append(group_name)
        self.users_by_group[group_name] = {}
        self.active_group = group_name
        
        self.announce_presence(group_name)
        time.sleep(0.5)
        self.discover_users(group_name)

    def shutdown(self):
        """Announces departure from all groups and closes sockets."""
        self.running = False
        for group in self.groups[:]:
             self._send_leave_broadcast(group)
        
        try:
            self.unicast_socket.close()
            self.broadcast_socket.close()
        except Exception:
            pass

    def _periodic_tasks(self):
        """Periodically sends presence announcements and purges stale users."""
        while self.running:
            time.sleep(15) # Alle 15 Sekunden ankündigen/prüfen
            
            # Anwesenheit in allen beigetretenen Gruppen ankündigen
            for group in self.groups:
                alive_msg = f"ALIVE {group} {self.handle} {self.port}"
                try:
                    self.broadcast_socket.sendto(alive_msg.encode('utf-8'), (self.broadcast_address, self.broadcast_port))
                except Exception:
                    # Socket könnte während des Herunterfahrens geschlossen werden
                    if self.running:
                        print(f"Konnte keine ALIVE-Nachricht für Gruppe {group} senden")

            # Benutzer entfernen, die eine Weile nicht gesehen wurden (z.B. 35 Sekunden)
            now = time.time()
            # Eine Kopie der Elemente verwenden, um Änderungen während der Iteration zu ermöglichen
            for group, users in list(self.users_by_group.items()):
                for handle, user_info in list(users.items()):
                    # user_info kann (ip, port) aus altem Code oder (ip, port, zeitstempel) sein
                    if len(user_info) == 3:
                        last_seen = user_info[2]
                        # Zeitüberschreitung etwas mehr als 2x das Ankündigungsintervall
                        if now - last_seen > 35:
                            print(f"\nVerbindung zu '{handle}' in Gruppe '{group}' verloren (Timeout).")
                            print("> ", end="", flush=True)
                            del self.users_by_group[group][handle]

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def switch_active_group(self, group_name):
        if group_name in self.groups:
            self.active_group = group_name
            print(f"\nAktive Gruppe ist jetzt '{self.active_group}'.")
        else:
            print(f"\nDu bist nicht in Gruppe '{group_name}'.")
        print("> ", end="", flush=True)

    def list_groups(self):
        print("\nBeigetretene Gruppen:")
        if not self.groups:
            print("- Keine")
        else:
            for group in self.groups:
                active_marker = " (aktiv)" if group == self.active_group else ""
                print(f"- {group}{active_marker}")
        print("> ", end="", flush=True)

    def send_image(self, handle, size_str):
        """Sends a block of random binary data to a specific user."""
        user_info = None
        for group in self.users_by_group:
            if handle in self.users_by_group[group]:
                user_info = self.users_by_group[group][handle]
                break
        
        if not user_info:
            print(f"\nNutzer '{handle}' nicht gefunden. 'who' in der jeweiligen Gruppe ausführen.")
            print("> ", end="", flush=True)
            return

        try:
            size = int(size_str)
            if size <= 0:
                print("\nGröße muss positiv sein.")
                print("> ", end="", flush=True)
                return
        except ValueError:
            print(f"\nUngültige Größe: {size_str}")
            print("> ", end="", flush=True)
            return

        try:
            # Zufällige Binärdaten generieren
            binary_data = os.urandom(size)
            
            ip, port, _ = user_info

            # 1. Befehl senden
            img_command = f"IMG {self.handle} {size}"
            self.unicast_socket.sendto(img_command.encode('utf-8'), (ip, port))
            
            # 2. Binärdaten senden
            time.sleep(0.1) # Kleine Verzögerung, um zu verhindern, dass Pakete in falscher Reihenfolge ankommen
            self.unicast_socket.sendto(binary_data, (ip, port))

            print(f"\nBinärdaten an {handle} gesendet ({size} bytes).")

        except Exception as e:
            print(f"\nFehler beim Senden der Binärdaten: {e}")
        
        print("> ", end="", flush=True)

    def _save_image(self, data, sender):
        """Saves received image data to a file."""
        try:
            # Ein Verzeichnis für empfangene Bilder erstellen, falls es nicht existiert
            if not os.path.exists('received_images'):
                os.makedirs('received_images')

            # Einen eindeutigen Dateinamen erstellen
            timestamp = int(time.time())
            # Einen eindeutigen Dateinamen für die Binärdaten erstellen
            filename = f"received_images/from_{sender}_{timestamp}.bin"
            
            with open(filename, 'wb') as f:
                f.write(data)
            
            print(f"\nBinärdaten von {sender} empfangen und als '{filename}' gespeichert.")
            print("> ", end="", flush=True)
        except Exception as e:
            print(f"\nFehler beim Speichern des Bildes: {e}")
            print("> ", end="", flush=True)