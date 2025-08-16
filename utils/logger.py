import os
import functools
import datetime
import uuid

# Crée le dossier de logs s'il n'existe pas
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Niveau de log
LOG_LEVELS = {"NONE": 0, "BASIC": 1, "DETAILED": 2}
LOG_LEVEL = LOG_LEVELS["DETAILED"]  # Peut être changé dynamiquement

# ID unique pour chaque session
SESSION_ID = uuid.uuid4().hex[:8]

# Chemin du fichier log pour cette session
now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE_PATH = os.path.join(LOGS_DIR, f"combat_log_{now}_{SESSION_ID}.txt")

# Entête du fichier de log
with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
    f.write(f"# Log de session - ID: {SESSION_ID}\n")
    f.write(f"# Niveau de log: {LOG_LEVEL}\n")
    f.write(f"# Début: {now}\n\n")


def log_calls(func):
    """Décorateur pour logger les appels de fonctions et mesurer leur temps d'exécution."""
    import time as _time
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if LOG_LEVEL == 0:
            return func(*args, **kwargs)

        timestamp = datetime.datetime.now().isoformat(timespec='seconds')
        entry = f"[{timestamp}] Appel {func.__qualname__} args={args} kwargs={kwargs}\n"

        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(entry)

        start_time = _time.perf_counter()
        result = func(*args, **kwargs)
        end_time = _time.perf_counter()
        elapsed = end_time - start_time

        if LOG_LEVEL >= 2:
            with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] Retour {func.__qualname__}: {result}\n")
                f.write(f"[{timestamp}] Temps d'exécution {func.__qualname__}: {elapsed:.6f} s\n")

        return result

    return wrapper
