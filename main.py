#!/usr/bin/env python3
from user_interface import UserInterface
from utils.config_loader import load_config
import sys

def show_welcome_banner():
    print("\n=== Peer-to-Peer Chat ===")
    print("Befehle: '/join <Gruppe>', 'msg <Nutzer> <Text>', 'who', 'exit'")
    print("Standardnachrichten werden an die aktuelle Gruppe gesendet.\n")

def main():
    show_welcome_banner()
    
    # Konfiguration laden
    # Konfiguration laden, optional via Kommandozeile
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.toml"
    config = load_config(config_file)
    if not config:
        print("Fehler: Konfiguration konnte nicht geladen werden")
        sys.exit(1)
    
    try:
        # Benutzeroberfläche starten
        ui = UserInterface(config)
        # Warten auf das Ende des Input-Threads
        while ui.running:
            pass
    except KeyboardInterrupt:
        print("\nProgramm wird beendet...")
        sys.exit(0)
    except Exception as e:
        print(f"Fehler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()