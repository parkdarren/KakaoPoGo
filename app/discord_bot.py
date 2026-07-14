from __future__ import annotations

import logging
import os

import discord
from discord import app_commands

from app.bot import PokemonGoBot
from app.discord_utils import cp_command_text, split_discord_messages


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("kakaopogo.discord")

core_bot = PokemonGoBot()
prefix_enabled = os.getenv("DISCORD_ENABLE_PREFIX", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

intents = discord.Intents.default()
if prefix_enabled:
    intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
_commands_synced = False


def _interaction_room(interaction: discord.Interaction) -> str:
    if interaction.guild_id and interaction.channel_id:
        return f"discord:guild:{interaction.guild_id}:channel:{interaction.channel_id}"
    return f"discord:dm:{interaction.user.id}"


def _message_room(message: discord.Message) -> str:
    if message.guild and message.channel:
        return f"discord:guild:{message.guild.id}:channel:{message.channel.id}"
    return f"discord:dm:{message.author.id}"


def _display_name(user: discord.abc.User) -> str:
    return getattr(user, "display_name", None) or user.name


def _user_key(user: discord.abc.User) -> str:
    return f"discord:{user.id}"


async def _send_interaction_reply(
    interaction: discord.Interaction,
    reply: str,
) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True)

    for chunk in split_discord_messages(reply):
        await interaction.followup.send(chunk)


async def _run_core_command(interaction: discord.Interaction, command_text: str) -> None:
    response = await core_bot.handle(
        command_text,
        room=_interaction_room(interaction),
        sender=_display_name(interaction.user),
        user_key=_user_key(interaction.user),
    )
    # 슬래시 명령은 응답이 필수라 침묵 대신 안내를 보낸다.
    reply = response.reply if not response.silent else "등록되지 않은 명령어입니다."
    await _send_interaction_reply(interaction, reply)


@client.event
async def on_ready() -> None:
    global _commands_synced
    if _commands_synced:
        return

    guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        logger.info("Synced %s Discord commands to guild %s", len(synced), guild_id)
    else:
        synced = await tree.sync()
        logger.info("Synced %s global Discord commands", len(synced))

    _commands_synced = True
    logger.info("Discord bot logged in as %s", client.user)


@client.event
async def on_message(message: discord.Message) -> None:
    if not prefix_enabled or message.author.bot:
        return

    content = message.content.strip()
    if not content.startswith("/"):
        return

    response = await core_bot.handle(
        content,
        room=_message_room(message),
        sender=_display_name(message.author),
        user_key=_user_key(message.author),
    )
    if response.silent:
        return
    for chunk in split_discord_messages(response.reply):
        await message.channel.send(chunk)


@tree.command(name="도움말", description="사용 가능한 포켓몬GO 봇 명령어를 봅니다.")
async def help_command(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/도움말")


@tree.command(name="명령어목록", description="이 채널에서 사용할 수 있는 명령어를 봅니다.")
async def command_list(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/명령어목록")


@tree.command(name="도감", description="포켓몬 타입, 약점, 100% CP를 조회합니다.")
@app_commands.rename(pokemon="포켓몬")
@app_commands.describe(pokemon="예: 디아루가, 화이트큐레무, 자시안 검왕")
async def dex(interaction: discord.Interaction, pokemon: str) -> None:
    await _run_core_command(interaction, f"/도감 {pokemon}")


@tree.command(name="스킬", description="포켓몬GO 기술을 한글명으로 조회합니다.")
@app_commands.rename(pokemon="포켓몬")
@app_commands.describe(pokemon="예: 피카츄, 블랙큐레무")
async def moves(interaction: discord.Interaction, pokemon: str) -> None:
    await _run_core_command(interaction, f"/스킬 {pokemon}")


@tree.command(name="100", description="100% 개체값 CP를 빠르게 조회합니다.")
@app_commands.rename(pokemon="포켓몬")
@app_commands.describe(pokemon="예: 자시안 검왕, 기라티나 오리진")
async def perfect(interaction: discord.Interaction, pokemon: str) -> None:
    await _run_core_command(interaction, f"/100 {pokemon}")


@tree.command(name="약점", description="포켓몬 타입, 약점, 저항을 조회합니다.")
@app_commands.rename(pokemon="포켓몬")
@app_commands.describe(pokemon="예: 뮤츠, 기라티나 오리진")
async def weakness(interaction: discord.Interaction, pokemon: str) -> None:
    await _run_core_command(interaction, f"/약점 {pokemon}")


@tree.command(name="카운터", description="레이드 카운터 포켓몬을 추천합니다.")
@app_commands.rename(pokemon="포켓몬")
@app_commands.describe(pokemon="예: 뮤츠, 메가레쿠쟈")
async def counter(interaction: discord.Interaction, pokemon: str) -> None:
    await _run_core_command(interaction, f"/카운터 {pokemon}")


@tree.command(name="cp", description="원하는 레벨과 IV 기준 CP를 계산합니다.")
@app_commands.rename(
    pokemon="포켓몬",
    level="레벨",
    attack="공격",
    defense="방어",
    stamina="체력",
)
@app_commands.describe(
    pokemon="예: 피카츄",
    level="1~51 사이, 0.5 단위",
    attack="공격 IV, 0~15",
    defense="방어 IV, 0~15",
    stamina="체력 IV, 0~15",
)
async def cp(
    interaction: discord.Interaction,
    pokemon: str,
    level: float,
    attack: int,
    defense: int,
    stamina: int,
) -> None:
    await _run_core_command(
        interaction,
        cp_command_text(pokemon, level, attack, defense, stamina),
    )


@tree.command(name="리그", description="슈퍼/하이퍼리그 랭크1 개체값을 조회합니다.")
@app_commands.rename(pokemon="포켓몬")
@app_commands.describe(pokemon="예: 마릴리, 기라티나 어나더")
async def league(interaction: discord.Interaction, pokemon: str) -> None:
    await _run_core_command(interaction, f"/리그 {pokemon}")


@tree.command(name="포켓몬고이벤트", description="진행 중인 이벤트와 7일간의 예정 이벤트를 봅니다.")
async def pokemon_go_events(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/포켓몬고이벤트")


@tree.command(name="날씨", description="오늘 전국 대표 지역의 오전/오후 날씨를 봅니다.")
async def weather(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/날씨")


@tree.command(name="오늘의포켓몬", description="오늘의 파트너 포켓몬과 출석을 확인합니다.")
async def daily(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/오늘의포켓몬")


@tree.command(name="출석랭킹", description="이 채널의 출석 랭킹을 봅니다.")
async def attendance_ranking(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/출석랭킹")


@tree.command(name="오너등록", description="이 디스코드 채널의 봇 owner를 등록합니다.")
@app_commands.rename(code="코드")
@app_commands.describe(code="서버에 설정한 OWNER_SETUP_CODE")
async def owner_setup(interaction: discord.Interaction, code: str) -> None:
    await _run_core_command(interaction, f"/오너등록 {code}")


@tree.command(name="관리자요청", description="owner에게 관리자 권한을 요청합니다.")
async def admin_request(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/관리자요청")


@tree.command(name="권한확인", description="현재 채널에서 내 봇 권한을 확인합니다.")
async def role_check(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/권한확인")


@tree.command(name="관리자요청목록", description="대기 중인 관리자 요청을 봅니다.")
async def admin_request_list(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/관리자요청목록")


@tree.command(name="관리자승인", description="관리자 요청을 승인합니다.")
@app_commands.rename(number="번호")
async def admin_approve(interaction: discord.Interaction, number: int) -> None:
    await _run_core_command(interaction, f"/관리자승인 {number}")


@tree.command(name="관리자거절", description="관리자 요청을 거절합니다.")
@app_commands.rename(number="번호")
async def admin_reject(interaction: discord.Interaction, number: int) -> None:
    await _run_core_command(interaction, f"/관리자거절 {number}")


@tree.command(name="관리자목록", description="이 채널의 owner/admin 목록을 봅니다.")
async def admin_list(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/관리자목록")


@tree.command(name="관리자삭제", description="관리자 권한을 삭제합니다.")
@app_commands.rename(number="번호")
async def admin_remove(interaction: discord.Interaction, number: int) -> None:
    await _run_core_command(interaction, f"/관리자삭제 {number}")


@tree.command(name="명령어등록", description="이 채널에 커스텀 명령어를 등록합니다.")
@app_commands.rename(command="명령어", response="답변")
@app_commands.describe(command="예: 공지", response="명령어 실행 시 보낼 답변")
async def custom_upsert(
    interaction: discord.Interaction,
    command: str,
    response: str,
) -> None:
    clean_command = command.strip().removeprefix("/").removeprefix("!")
    await _run_core_command(interaction, f"/명령어등록 {clean_command} {response}")


@tree.command(name="명령어수정", description="이 채널의 커스텀 명령어를 수정합니다.")
@app_commands.rename(command="명령어", response="답변")
async def custom_update(
    interaction: discord.Interaction,
    command: str,
    response: str,
) -> None:
    clean_command = command.strip().removeprefix("/").removeprefix("!")
    await _run_core_command(interaction, f"/명령어수정 {clean_command} {response}")


@tree.command(name="명령어삭제", description="이 채널의 커스텀 명령어를 삭제합니다.")
@app_commands.rename(command="명령어")
async def custom_delete(interaction: discord.Interaction, command: str) -> None:
    clean_command = command.strip().removeprefix("/").removeprefix("!")
    await _run_core_command(interaction, f"/명령어삭제 {clean_command}")


@tree.command(name="명령어실행", description="등록된 커스텀 명령어를 실행합니다.")
@app_commands.rename(command="명령어")
@app_commands.describe(command="예: 공지")
async def custom_run(interaction: discord.Interaction, command: str) -> None:
    clean_command = command.strip().removeprefix("/").removeprefix("!")
    await _run_core_command(interaction, f"/{clean_command}")


@tree.command(name="대상방설정", description="관리 대상 채널 이름을 설정합니다.")
@app_commands.rename(room="방이름")
async def target_set(interaction: discord.Interaction, room: str) -> None:
    await _run_core_command(interaction, f"/대상방설정 {room}")


@tree.command(name="대상방확인", description="현재 대상방 설정을 확인합니다.")
async def target_show(interaction: discord.Interaction) -> None:
    await _run_core_command(interaction, "/대상방확인")


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN 환경변수를 설정해 주세요.")

    client.run(token)


if __name__ == "__main__":
    main()
