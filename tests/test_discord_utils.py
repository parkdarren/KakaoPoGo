from app.discord_utils import cp_command_text, split_discord_messages


def test_split_discord_messages_keeps_chunks_under_limit() -> None:
    chunks = split_discord_messages("가" * 4500, limit=1900)

    assert len(chunks) == 3
    assert all(len(chunk) <= 1900 for chunk in chunks)
    assert "".join(chunks) == "가" * 4500


def test_split_discord_messages_prefers_newline_boundaries() -> None:
    text = "첫 줄\n둘째 줄\n\n셋째 줄"

    chunks = split_discord_messages(text, limit=10)

    assert chunks == ["첫 줄\n둘째 줄", "셋째 줄"]


def test_cp_command_text_formats_level_without_trailing_zero() -> None:
    assert cp_command_text("피카츄", 40.0, 15, 14, 13) == "/cp 피카츄 40 15/14/13"
    assert cp_command_text("피카츄", 40.5, 15, 15, 15) == "/cp 피카츄 40.5 15/15/15"
