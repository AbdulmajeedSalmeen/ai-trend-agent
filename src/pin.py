import argparse
import json
from pathlib import Path

CURRICULUM_PATH = Path("fixtures/curriculum.json")


def set_pin(data: dict, chapter_id: str, package: str, version: str | None) -> dict:
    for chapter in data["chapters"]:
        if chapter["chapter_id"] != chapter_id:
            continue

        pins = chapter.setdefault("pins", {})

        if version is None:
            pins.pop(package, None)
        else:
            pins[package] = version

        return chapter

    raise SystemExit(f"no chapter {chapter_id} in the curriculum")


def show(data: dict) -> None:
    for chapter in data["chapters"]:
        for package, version in chapter.get("pins", {}).items():
            print(f"{chapter['chapter_id']:<4} {package:<24} {version or 'not recorded'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the package version a chapter's notebooks install.")
    parser.add_argument("chapter_id", nargs="?")
    parser.add_argument("package", nargs="?")
    parser.add_argument("version", nargs="?")
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    data = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))

    if args.chapter_id is None:
        show(data)
        return

    if args.package is None:
        raise SystemExit("name the package, for example: python -m src.pin C8 langchain 0.1.16")

    chapter = set_pin(data, args.chapter_id, args.package, None if args.clear else args.version)
    CURRICULUM_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{chapter['chapter_id']} now runs: " + ", ".join(
        f"{name} {value or 'not recorded'}" for name, value in chapter["pins"].items()) or "nothing")


if __name__ == "__main__":
    main()
