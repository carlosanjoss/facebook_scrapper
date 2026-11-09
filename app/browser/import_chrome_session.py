import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import USER_DATA_DIR


def _chrome_user_data_dir():
    local_app_data = os.getenv("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA nao esta definido")
    return Path(local_app_data) / "Google/Chrome/User Data"


def _copy_facebook_cookies(source, destination):
    source_connection = sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30
    )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".importing")
        temporary.unlink(missing_ok=True)
        destination_connection = sqlite3.connect(str(temporary))
        try:
            source_connection.backup(destination_connection)
            destination_connection.execute(
                "DELETE FROM cookies WHERE NOT "
                "(host_key = 'facebook.com' OR host_key LIKE '%.facebook.com')"
            )
            destination_connection.commit()
            count = destination_connection.execute(
                "SELECT COUNT(*) FROM cookies WHERE name = 'c_user'"
            ).fetchone()[0]
        finally:
            destination_connection.close()
        if not count:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("O Chrome nao possui uma sessao autenticada do Facebook")
        os.replace(temporary, destination)
        return count
    finally:
        source_connection.close()


def _merge_encryption_settings(source, destination):
    source_data = json.loads(source.read_text(encoding="utf-8"))
    if "os_crypt" not in source_data:
        raise RuntimeError("O Chrome nao forneceu as chaves de criptografia da sessao")
    destination_data = {}
    if destination.exists():
        destination_data = json.loads(destination.read_text(encoding="utf-8"))
    destination_data["os_crypt"] = source_data["os_crypt"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(destination_data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def import_default_chrome_session():
    chrome_data = _chrome_user_data_dir()
    source_cookies = chrome_data / "Default/Network/Cookies"
    source_local_state = chrome_data / "Local State"
    if not source_cookies.is_file() or not source_local_state.is_file():
        raise RuntimeError("Perfil Default do Chrome nao foi encontrado")

    target_cookies = USER_DATA_DIR / "Default/Network/Cookies"
    target_local_state = USER_DATA_DIR / "Local State"
    backup_dir = (
        USER_DATA_DIR.parent
        / "session_backups"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    if target_cookies.exists():
        shutil.copy2(target_cookies, backup_dir / "Cookies")
    if target_local_state.exists():
        shutil.copy2(target_local_state, backup_dir / "Local State")

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target_cookies) + suffix)
        if sidecar.exists():
            shutil.move(str(sidecar), str(backup_dir / sidecar.name))

    _merge_encryption_settings(source_local_state, target_local_state)
    count = _copy_facebook_cookies(source_cookies, target_cookies)
    return count, backup_dir


def main():
    count, backup_dir = import_default_chrome_session()
    print("Sessao do Facebook importada com sucesso.")
    print(f"Cookies de autenticacao encontrados: {count}")
    print(f"Backup do perfil anterior: {backup_dir}")


if __name__ == "__main__":
    main()
