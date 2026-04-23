import json
import re
from datetime import datetime, timedelta, timezone

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from .text_to_img import text_to_image, members_to_image
from .rsi_scraper import fetch_org_members
import time


# ======================
# 周期常量（毫秒）
# ======================
OPEN_DURATION = timedelta(milliseconds=3_900_362)
CLOSE_DURATION = timedelta(milliseconds=7_200_667)
CYCLE_DURATION = OPEN_DURATION + CLOSE_DURATION


# ======================
# 数据文件
# ======================
DATA_DIR = StarTools.get_data_dir("astrbot_plugin_the_homeward_sail")
HANGAR_TIME_FILE = DATA_DIR / "hangar_time.json"
FLEETS_FILE = DATA_DIR / "fleets.json"


@register(
    "astrbot_plugin_the_homeward_sail",
    "huangpixu",
    "查询星际公民行政机库时间。",
    "1.1.7",
    "https://github.com/huangpixu/astrbot_plugin_executive_hangar_time.git",
)
class TheHomewardSail(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        self.members_cache_by_symbol = {}
        self.last_fetch_time_by_symbol = {}
        self.fleets = {}

    async def initialize(self):
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)

        if not HANGAR_TIME_FILE.exists():
            now = datetime.now(timezone.utc).astimezone()
            HANGAR_TIME_FILE.write_text(
                json.dumps(
                    {"initial_open_time": now.isoformat()},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        if not FLEETS_FILE.exists():
            FLEETS_FILE.write_text(
                json.dumps({"鹿港": "GFHB"}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        self._sync_fleets_from_disk()

    # ======================
    # 文件读写
    # ======================
    def _load_initial_time(self) -> datetime:
        data = json.loads(HANGAR_TIME_FILE.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["initial_open_time"])

    def _save_initial_time(self, dt: datetime):
        HANGAR_TIME_FILE.write_text(
            json.dumps(
                {"initial_open_time": dt.isoformat()},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _sync_fleets_from_disk(self) -> dict:
        try:
            raw = json.loads(FLEETS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                fleets = {}
                for k, v in raw.items():
                    name = str(k).strip()
                    symbol = str(v).strip()
                    if name and symbol:
                        fleets[name] = symbol
                self.fleets = fleets
                return fleets
        except Exception as e:
            logger.exception(e)
        self.fleets = {}
        return {}

    def _save_fleets_to_disk(self):
        FLEETS_FILE.write_text(
            json.dumps(self.fleets, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _build_command_help_text(self, command_name: str = "") -> str:
        command_name = (command_name or "").strip()
        helps = {
            "行政机库时间": (
                "命令：行政机库时间\n"
                "作用：查询接下来 10 次行政机库开启/关闭时间。\n"
                "用法：行政机库时间"
            ),
            "同步行政机库时间": (
                "命令：同步行政机库时间\n"
                "作用：同步行政机库起始时间，支持手动指定时间。\n"
                "用法1：同步行政机库时间\n"
                "用法2：同步行政机库时间 2026/01/04 17:35:08"
            ),
            "添加舰队": (
                "命令：添加舰队\n"
                "作用：保存舰队名和 RSI 组织编号的映射到文件。\n"
                "用法1：添加舰队 鹿港-GFHB\n"
                "用法2：添加舰队 鹿港 GFHB"
            ),
            "同步舰队编号": (
                "命令：同步舰队编号\n"
                "作用：从文件重新加载全部舰队编号映射。\n"
                "用法：同步舰队编号"
            ),
            "查成员": (
                "命令：查成员\n"
                "作用：按舰队名或组织编号查询成员，成员多时自动分页出图。\n"
                "用法1：查成员 鹿港\n"
                "用法2：查成员 鹿港 2\n"
                "用法3：查成员 GFHB"
            ),
            "查xxx成员": (
                "命令：查xxx成员\n"
                "作用：自然语言方式查询成员。\n"
                "示例：查鹿港成员"
            ),
            "鹿港成员": (
                "命令：鹿港成员\n"
                "作用：兼容旧命令，等同于查成员 鹿港。\n"
                "用法：鹿港成员"
            ),
            "查命令": (
                "命令：查命令\n"
                "作用：查看全部命令说明，或查看单条命令的用法。\n"
                "用法1：查命令\n"
                "用法2：查命令 添加舰队\n"
                "用法3：查命令 查成员"
            ),
        }

        aliases = {
            "帮助": "查命令",
            "help": "查命令",
            "所有命令": "查命令",
            "成员": "查成员",
        }

        if command_name:
            normalized = aliases.get(command_name, command_name)
            if normalized in helps:
                return helps[normalized]
            return (
                f"❌ 未找到命令：{command_name}\n"
                "可用：查命令\n"
                "或：查命令 查成员"
            )

        ordered = [
            "查命令",
            "行政机库时间",
            "同步行政机库时间",
            "添加舰队",
            "同步舰队编号",
            "查成员",
            "查xxx成员",
            "鹿港成员",
        ]
        lines = ["可用命令如下："]
        for name in ordered:
            lines.append("")
            lines.append(helps[name])
        return "\n".join(lines)

    def _resolve_org_symbol(self, fleet_or_symbol: str) -> tuple[str, str] | None:
        key = (fleet_or_symbol or "").strip()
        if not key:
            return None

        if key in self.fleets:
            return key, self.fleets[key]

        if key.isalnum() and key.upper() == key:
            return key, key

        return None

    def _members_cache_file(self, symbol: str):
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", symbol.strip())
        return DATA_DIR / f"org_members_cache_{safe}.json"

    def _load_members_cache_from_disk(self, symbol: str) -> tuple[list, float] | None:
        cache_file = self._members_cache_file(symbol)
        if not cache_file.exists():
            return None
        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            members = raw.get("members")
            fetched_at = raw.get("fetched_at")
            if isinstance(members, list) and isinstance(fetched_at, (int, float)):
                return members, float(fetched_at)
        except Exception:
            return None
        return None

    def _save_members_cache_to_disk(self, symbol: str, members: list, fetched_at: float):
        cache_file = self._members_cache_file(symbol)
        cache_file.write_text(
            json.dumps(
                {"symbol": symbol, "fetched_at": fetched_at, "members": members},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    async def _get_members(self, symbol: str, ttl_seconds: int = 3600) -> tuple[list, str]:
        now = time.time()

        mem_members = self.members_cache_by_symbol.get(symbol)
        mem_ts = self.last_fetch_time_by_symbol.get(symbol)
        if mem_members and isinstance(mem_ts, (int, float)) and now - float(mem_ts) <= ttl_seconds:
            return mem_members, "memory_fresh"

        disk = self._load_members_cache_from_disk(symbol)
        if disk:
            disk_members, disk_ts = disk
            if disk_members and now - float(disk_ts) <= ttl_seconds:
                self.members_cache_by_symbol[symbol] = disk_members
                self.last_fetch_time_by_symbol[symbol] = float(disk_ts)
                return disk_members, "disk_fresh"

        members = await fetch_org_members(symbol)
        if members:
            self.members_cache_by_symbol[symbol] = members
            self.last_fetch_time_by_symbol[symbol] = now
            try:
                self._save_members_cache_to_disk(symbol, members, now)
            except Exception as e:
                logger.exception(e)
            return members, "remote"

        if mem_members:
            return mem_members, "memory_stale"

        if disk:
            disk_members, _ = disk
            if disk_members:
                return disk_members, "disk_stale"

        return [], "empty"

    async def _send_members_images(
        self,
        event: AstrMessageEvent,
        org_display_name: str,
        symbol: str,
        members: list,
        page: int | None = None,
        chunk_size: int = 200,
        max_pages_send: int = 10,
    ):
        total = len(members)
        if total == 0:
            yield event.plain_result("❌ 未获取到成员信息。")
            return

        total_pages = (total + chunk_size - 1) // chunk_size
        save_dir = DATA_DIR

        if page is not None:
            if page < 1 or page > total_pages:
                yield event.plain_result(f"❌ 页码超出范围：1 - {total_pages}")
                return
            start = (page - 1) * chunk_size
            end = min(start + chunk_size, total)
            img_path = members_to_image(
                members[start:end],
                save_dir,
                org_display_name=org_display_name,
                total_count=total,
                page=page,
                total_pages=total_pages,
                output_filename=f"members_{symbol}_{page}.png",
            )
            yield event.image_result(img_path)
            return

        pages_to_send = min(total_pages, max_pages_send)
        if total_pages > 1:
            note = f"共 {total} 人，拆分为 {total_pages} 张图片。"
            if total_pages > max_pages_send:
                note += f"\n仅发送前 {max_pages_send} 张，可用：/查成员 {org_display_name} <页码>"
            yield event.plain_result(note)

        for p in range(1, pages_to_send + 1):
            start = (p - 1) * chunk_size
            end = min(start + chunk_size, total)
            img_path = members_to_image(
                members[start:end],
                save_dir,
                org_display_name=org_display_name,
                total_count=total,
                page=p,
                total_pages=total_pages,
                output_filename=f"members_{symbol}_{p}.png",
            )
            yield event.image_result(img_path)

    # ======================
    # 从【当前时间】开始生成 N 个区间
    # ======================
    def _generate_next_ranges(self, initial_time: datetime, count: int = 10):
        now = datetime.now().astimezone()

        elapsed = now - initial_time
        cycles = elapsed // CYCLE_DURATION
        cursor = initial_time + cycles * CYCLE_DURATION

        # 如果当前已过开启时间，跳到下一个周期
        if now > cursor + OPEN_DURATION:
            cursor += CYCLE_DURATION

        ranges = []

        while len(ranges) < count:
            open_start = cursor
            open_end = cursor + OPEN_DURATION
            ranges.append((open_start, open_end))
            cursor += CYCLE_DURATION

        return ranges

    # ======================
    # 指令：行政机库时间（图片）
    # ======================
    @filter.command("行政机库时间")
    async def executive_hangar_time(self, event: AstrMessageEvent):
        # 先回复“正在生成中”
        yield event.plain_result("⏳ 正在计算并生成时间表，请稍候...")
        
        try:
            initial_time = self._load_initial_time()
            ranges = self._generate_next_ranges(initial_time, count=10)

            lines = ["🟢【开启时间】>>>>>> 🔴【关闭时间】\n"]
            for start, end in ranges:
                lines.append(f"🟢{start.strftime('%Y/%m/%d %H:%M:%S')} 🔴{end.strftime('%Y/%m/%d %H:%M:%S')}")
                # lines.append(f"🔴{end.strftime('%Y/%m/%d %H:%M:%S')}")
                lines.append("")

            text = "\n".join(lines)
            logger.debug(f"[hangar_time] generating image for text (len={len(text)}): {repr(text)}")
            
            img = text_to_image(text, DATA_DIR)
            
            if not img:
                logger.warning("[hangar_time] text_to_image returned None/empty.")
                yield event.plain_result(text)
            else:
                logger.debug(f"[hangar_time] text_to_image success. type={type(img)}")
                yield event.image_result(img)

        except Exception as e:
            logger.exception(e)
            yield event.plain_result("❌ 查询行政机库时间失败")

    # ======================
    # 指令：查命令
    # ======================
    @filter.command("查命令")
    async def show_commands(self, event: AstrMessageEvent, command_name: str = ""):
        yield event.plain_result(self._build_command_help_text(command_name))

    # ======================
    # 指令：添加舰队
    # ======================
    @filter.command("添加舰队")
    async def add_fleet(self, event: AstrMessageEvent, mapping: str = ""):
        raw = (mapping or "").strip()
        if not raw:
            msg = event.message_str.strip()
            parts = msg.split(maxsplit=1)
            raw = parts[1].strip() if len(parts) == 2 else ""

        if not raw:
            yield event.plain_result(self._build_command_help_text("添加舰队"))
            return

        if "-" in raw:
            name, symbol = raw.split("-", 1)
        else:
            parts = raw.split(maxsplit=1)
            if len(parts) != 2:
                yield event.plain_result(self._build_command_help_text("添加舰队"))
                return
            name, symbol = parts

        name = name.strip()
        symbol = symbol.strip()
        if not name or not symbol:
            yield event.plain_result(self._build_command_help_text("添加舰队"))
            return

        self.fleets[name] = symbol
        try:
            self._save_fleets_to_disk()
        except Exception as e:
            logger.exception(e)
            yield event.plain_result("❌ 写入舰队编号文件失败。")
            return

        yield event.plain_result(f"✅ 已保存舰队：{name} -> {symbol}")

    # ======================
    # 指令：同步舰队编号
    # ======================
    @filter.command("同步舰队编号")
    async def sync_fleets(self, event: AstrMessageEvent):
        fleets = self._sync_fleets_from_disk()
        if not fleets:
            yield event.plain_result("✅ 已同步舰队编号：当前为空。")
            return

        preview = list(fleets.items())[:20]
        lines = [f"✅ 已同步舰队编号：共 {len(fleets)} 个"]
        lines += [f"- {k} -> {v}" for k, v in preview]
        if len(fleets) > 20:
            lines.append("- ...")
        yield event.plain_result("\n".join(lines))

    # ======================
    # 指令：查成员（参数形式）
    # ======================
    @filter.command("查成员")
    async def query_members(self, event: AstrMessageEvent, fleet: str = "", page: int | None = None):
        fleet = (fleet or "").strip()
        if not fleet:
            yield event.plain_result(self._build_command_help_text("查成员"))
            return

        resolved = self._resolve_org_symbol(fleet)
        if not resolved:
            yield event.plain_result(
                "❌ 未找到该舰队编号。\n"
                f"{self._build_command_help_text('添加舰队')}"
            )
            return
        org_display_name, symbol = resolved

        yield event.plain_result(f"⏳ 正在获取 {org_display_name}({symbol}) 成员信息，请稍候...")

        try:
            members, source = await self._get_members(symbol, ttl_seconds=3600)

            if source in {"memory_stale", "disk_stale"}:
                yield event.plain_result("⚠️ 获取最新成员失败，已使用缓存数据。")
            elif source in {"disk_fresh"}:
                yield event.plain_result("ℹ️ 已使用本地缓存数据。")

            async for r in self._send_members_images(
                event,
                org_display_name=org_display_name,
                symbol=symbol,
                members=members,
                page=page,
            ):
                yield r
                
        except Exception as e:
            logger.exception(e)
            yield event.plain_result("❌ 获取成员信息发生异常，可能是网络原因。")

    # ======================
    # 指令：查xxx成员（自然语言形式）
    # ======================
    @filter.regex(r"^查(.+?)成员$")
    async def query_members_regex(self, event: AstrMessageEvent):
        if not (event.is_wake or event.is_at_or_wake_command):
            return

        m = re.match(r"^查(.+?)成员$", event.message_str.strip())
        if not m:
            return
        fleet = (m.group(1) or "").strip()
        if not fleet:
            return

        async for r in self.query_members(event, fleet=fleet):
            yield r

    # ======================
    # 指令：鹿港成员（兼容旧命令）
    # ======================
    @filter.command("鹿港成员")
    async def lugang_members(self, event: AstrMessageEvent):
        async for r in self.query_members(event, fleet="鹿港"):
            yield r

    # ======================
    # 指令：同步行政机库时间
    # ======================
    @filter.command("同步行政机库时间")
    async def sync_executive_hangar_time(self, event: AstrMessageEvent, time_str: str = ""):
        msg = event.message_str.strip()
        parts = msg.split(maxsplit=1)

        try:
            local_tz = datetime.now().astimezone().tzinfo

            if len(parts) == 2:
                dt = datetime.strptime(parts[1], "%Y/%m/%d %H:%M:%S")
                dt = dt.replace(tzinfo=local_tz)
            else:
                dt = datetime.now(timezone.utc).astimezone()

            self._save_initial_time(dt)

            yield event.plain_result(
                "✅ 行政机库起始时间已同步\n"
                f"起始时间：{dt.strftime('%Y/%m/%d %H:%M:%S')}"
            )

        except ValueError:
            yield event.plain_result(
                "❌ 时间格式错误\n"
                f"{self._build_command_help_text('同步行政机库时间')}"
            )
