import json
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
DATA_FILE = (
    StarTools.get_data_dir("astrbot_plugin_the_homeward_sail")
    / "hangar_time.json"
)


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
        self.members_cache = []
        self.last_fetch_time = 0

    async def initialize(self):
        if not DATA_FILE.exists():
            now = datetime.now(timezone.utc).astimezone()
            DATA_FILE.write_text(
                json.dumps(
                    {"initial_open_time": now.isoformat()},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    # ======================
    # 文件读写
    # ======================
    def _load_initial_time(self) -> datetime:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["initial_open_time"])

    def _save_initial_time(self, dt: datetime):
        DATA_FILE.write_text(
            json.dumps(
                {"initial_open_time": dt.isoformat()},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

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
            
            img = text_to_image(text, StarTools.get_data_dir("astrbot_plugin_the_homeward_sail"))
            
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
    # 指令：鹿港成员
    # ======================
    @filter.command("鹿港成员")
    async def lugang_members(self, event: AstrMessageEvent):
        yield event.plain_result("⏳ 正在获取鹿港成员信息并生成图片，请稍候...")
        
        try:
            current_time = time.time()
            # 1小时缓存
            if not self.members_cache or current_time - self.last_fetch_time > 3600:
                members = await fetch_org_members("GFHB")
                if members:
                    self.members_cache = members
                    self.last_fetch_time = current_time
                else:
                    if not self.members_cache:
                        yield event.plain_result("❌ 获取成员信息失败，且无本地缓存。")
                        return
            
            save_dir = StarTools.get_data_dir("astrbot_plugin_the_homeward_sail")
            img_path = members_to_image(self.members_cache, save_dir)
            
            if img_path:
                yield event.image_result(img_path)
            else:
                yield event.plain_result("❌ 生成图片失败。")
                
        except Exception as e:
            logger.exception(e)
            yield event.plain_result("❌ 获取成员信息发生异常，可能是网络原因。")

    # ======================
    # 指令：同步行政机库时间
    # ======================
    @filter.command("同步行政机库时间")
    async def sync_executive_hangar_time(self, event: AstrMessageEvent):
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
                "正确示例：/同步行政机库时间 2026/1/4 17:35:08"
            )
