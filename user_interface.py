import threading
from network.network_handler import NetworkHandler

class UserInterface:
    def __init__(self, config):
        self.config = config
        self.running = True
        
        print(f"Angemeldet als: {self.config['user']['handle']}")
        print(f"Mein Port: {self.config['user']['port']}")
        
        # Netzwerkkomponenten initialisieren
        self.network = NetworkHandler(self.config)
        
        # Eingabeloop starten
        self._start_input_thread()

    def _start_input_thread(self):
        self.input_thread = threading.Thread(target=self._input_loop)
        self.input_thread.daemon = True
        self.input_thread.start()

    def _input_loop(self):
        while self.running:
            try:
                prompt_group = self.network.active_group if self.network.active_group else "Keine"
                user_input = input(f"[{prompt_group}] {self.config['user']['handle']}> ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() == 'exit':
                    self._shutdown()
                    break
                
                elif user_input.lower() == 'who':
                    self.network.discover_users()
                
                elif user_input.lower() == '/help':
                    self._print_help()

                elif user_input.startswith('/create '):
                    parts = user_input.split(' ', 1)
                    if len(parts) == 2 and parts[1]:
                        self.network.join_group(parts[1]) # join_group kümmert sich um die Erstellung
                    else:
                        print("Fehler: /create <Gruppenname>")

                elif user_input.startswith('/join '):
                    parts = user_input.split(' ', 1)
                    if len(parts) == 2 and parts[1]:
                        self.network.join_group(parts[1])
                    else:
                        print("Fehler: /join <Gruppenname>")

                elif user_input.startswith('/leave '):
                    parts = user_input.split(' ', 1)
                    if len(parts) == 2 and parts[1]:
                        self.network.leave_group(parts[1])
                    else:
                        print("Fehler: /leave <Gruppenname>")
                
                elif user_input.startswith('/switch '):
                    parts = user_input.split(' ', 1)
                    if len(parts) == 2 and parts[1]:
                        self.network.switch_active_group(parts[1])
                    else:
                        print("Fehler: /switch <Gruppenname>")

                elif user_input.lower() == '/groups':
                    self.network.list_groups()

                elif user_input.startswith('msg '):
                    text_part = user_input[4:]
                    
                    # Alle bekannten Benutzernamen aus allen Gruppen holen
                    all_known_handles = {
                        handle
                        for group_users in self.network.users_by_group.values()
                        for handle in group_users.keys()
                    }

                    # Nach Länge absteigend sortieren, um längere Namen zuerst zu finden (z.B. "User Two" vor "User")
                    sorted_handles = sorted(list(all_known_handles), key=len, reverse=True)

                    recipient = None
                    message = ""

                    for handle in sorted_handles:
                        # Prüfen, ob der Textteil mit einem bekannten Handle und einem Leerzeichen beginnt
                        if text_part.startswith(handle + ' '):
                            recipient = handle
                            # Die Nachricht ist alles nach dem Handle und dem Leerzeichen
                            message = text_part[len(handle) + 1:].strip()
                            break
                    
                    if recipient and message:
                        self.network.send_message(recipient, message)
                    else:
                        print("\nFehler: msg <Nutzer> <Text>")
                        print("Mögliche Gründe: Nutzer nicht gefunden, keine Nachricht eingegeben oder der Nutzer ist offline.")
                        print("Nutze 'who', um online Nutzer zu sehen.")
                    continue

                elif user_input.startswith('/img ') or user_input.startswith('/ img '):
                    parts = user_input.strip().split(' ', 2)
                    if len(parts) == 3:
                        self.network.send_image(parts[1], parts[2])
                    else:
                        print("Fehler: /img <Nutzer> <Größe_in_Bytes>")
                
                else:
                    # Alles andere wird als Gruppennachricht gesendet
                    self.network.send_group_message(user_input)
                        
            except KeyboardInterrupt:
                self._shutdown()
                break
            except Exception as e:
                print(f"Eingabefehler: {e}")

    def _print_help(self):
        print("\n--- Befehlsübersicht ---")
        print("msg <nutzer> <text> - Sendet eine private Nachricht.")
        print("/img <nutzer> <size> - Sendet <size> Bytes an Zufallsdaten an einen Nutzer.")
        print("who                 - Zeigt Nutzer in der aktiven Gruppe an.")
        print("/create <gruppe>    - Erstellt eine neue Gruppe und tritt ihr bei.")
        print("/join <gruppe>      - Tritt einer bestehenden Gruppe bei.")
        print("/leave <gruppe>     - Verlässt eine bestimmte Gruppe.")
        print("/switch <gruppe>    - Wechselt die aktive Gruppe zum Senden.")
        print("/groups             - Listet alle beigetretenen Gruppen auf.")
        print("exit                - Beendet das Programm.")
        print("------------------------\n> ", end="", flush=True)

    def _shutdown(self):
        print("\nBeende Verbindungen...")
        self.running = False
        self.network.shutdown()