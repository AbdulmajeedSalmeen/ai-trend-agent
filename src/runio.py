import json
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel

RUNS_DIR = Path("fixtures/runs")


def new_run_id() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("run_%Y%m%dT%H%M%SZ")

def run_dir(run_id: str) -> Path:
    run_path = RUNS_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / "raw").mkdir(exist_ok=True)
    return run_path

def save_artifact(run_path: Path, name: str, items: list[BaseModel]) -> None:
    # 1. نحول كل الاوبجكت اللي في القائمة إلى قاموس
    data = []
    for obj in items:
        data.append(obj.model_dump(mode="json"))
    # 2. نحول قائمة القواميس إلى نص JSON
    text = json.dumps(data, indent=2)
    # 3. نركّب مسار الملف من run_path و name
    path = run_path / f"{name}.json"
    # 4. نكتب النص في الملف
    path.write_text(text, encoding="utf-8")

def load_artifact(run_path: Path, name: str, model: type[BaseModel]) -> list[BaseModel]:
    # 1. نركّب مسار الملف من run_path و name
    path = run_path / f"{name}.json"
    # 2. نقرأ النص من الملف
    text = path.read_text(encoding="utf-8")
    # 3. نحول النص إلى قائمة قواميس
    data = json.loads(text)
    # 4. نحول كل قاموس إلى object من model
    objects = []
    for item in data:
        objects.append(model.model_validate(item))
    # 5. نرجّع قائمة الـ objects
    return objects
    