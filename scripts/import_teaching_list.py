from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.admin_store import AdminStore
from app.bot import PokemonGoBot


ENTRY_RE = re.compile(r"(?m)^(\d+)\.\s+/(.+?)\s*$")
TEACHER_RE = re.compile(r"^└ 가르친사람\s*:\s*(.+)$", re.MULTILINE)
TAUGHT_AT_RE = re.compile(r"^└ 가르친일자\s*:\s*(.+)$", re.MULTILINE)
COMMAND_RE = re.compile(r"^└ 명령어\s*:\s*/(.+)$", re.MULTILINE)
ANSWER_MARKER = "《답변1》"


def parse_teaching_list(text: str) -> list[dict[str, object]]:
    starts = list(ENTRY_RE.finditer(text))
    entries: list[dict[str, object]] = []
    for index, match in enumerate(starts):
        block_start = match.start()
        block_end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[block_start:block_end].strip()

        teacher = _required_match(TEACHER_RE, block, "가르친사람")
        taught_at = _required_match(TAUGHT_AT_RE, block, "가르친일자")
        display_command = _required_match(COMMAND_RE, block, "명령어").strip()
        if ANSWER_MARKER in block:
            response = block.split(ANSWER_MARKER, maxsplit=1)[1].strip()
        else:
            response = ""
        command = PokemonGoBot._normalize_custom_command(display_command)
        entries.append(
            {
                "help_order": int(match.group(1)),
                "command": command,
                "display_command": display_command,
                "response": response,
                "taught_by": teacher.strip(),
                "taught_at": taught_at.strip(),
            }
        )
    return entries


def _required_match(pattern: re.Pattern[str], text: str, label: str) -> str:
    match = pattern.search(text)
    if not match:
        raise ValueError(f"{label} 항목을 찾지 못했습니다.")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--room", required=True)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    text = args.file.read_text(encoding="utf-8")
    entries = parse_teaching_list(text)
    store = AdminStore(args.db) if args.db else AdminStore()
    for entry in entries:
        store.import_custom_command(room=args.room, **entry)

    print(f"Imported {len(entries)} teaching entries into {args.room}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
