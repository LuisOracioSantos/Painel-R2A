import json
from pathlib import Path


class JsonStorage:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def save(self, identifier, payload):
        path = self.folder / f"{identifier}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, identifier):
        path = self.folder / f"{identifier}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, identifier):
        path = self.folder / f"{identifier}.json"
        if not path.exists():
            return False
        path.unlink()
        return True
