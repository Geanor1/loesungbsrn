import toml
from pathlib import Path

def load_config(config_filename="config.toml"):
    try:
        config_path = Path(__file__).parent.parent / config_filename
        if not config_path.exists():
            print(f"Fehler: Konfigurationsdatei '{config_filename}' nicht gefunden.")
            return None
        with open(config_path, "r") as config_file:
            return toml.load(config_file)
    except Exception as e:
        print(f"Config error: {e}")
        return None