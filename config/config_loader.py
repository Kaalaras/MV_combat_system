import yaml
import os

class ConfigLoader:
    def __init__(self, config_file="settings.yaml"):
        self.config = {}
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)

    def get(self, *keys, default=None):
        """
        Récupère une valeur dans la configuration.
        Si un chemin de clé n'existe pas :
          - lève une KeyError si aucun default n'est fourni
          - retourne le default sinon
        """
        ref = self.config
        for key in keys:
            if key in ref:
                ref = ref[key]
            else:
                if default is not None:
                    return default
                raise KeyError(f"Configuration key {' -> '.join(keys)} not found and no default provided.")
        return ref
