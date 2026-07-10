from __future__ import annotations


DISCORD_MESSAGE_LIMIT = 1900


def split_discord_messages(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    remaining = text.strip() or "응답할 내용이 없습니다."
    chunks: list[str] = []
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def cp_command_text(
    pokemon: str,
    level: float,
    attack: int,
    defense: int,
    stamina: int,
) -> str:
    level_text = f"{level:g}"
    return f"/cp {pokemon} {level_text} {attack}/{defense}/{stamina}"
