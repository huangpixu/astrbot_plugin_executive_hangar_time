import json
from datetime import datetime, timedelta, timezone

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger


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
    StarTools.get_data_dir("astrbot_plugin_executive_hangar_time")
    / "hangar_time.json"
)


@register(
    "astrbot_plugin_executive_hangar_time",
    "huangpixu",
    "查询星际公民行政机库时间。",
    "1.1.4",
    "https://github.com/huangpixu/astrbot_plugin_executive_hangar_time.git",
)
class ExecutiveHangarTime(Star):

    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件初始化：若文件不存在，创建一个"""
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
    # 核心逻辑：
    # 从【当前时间】开始生成 N 个连续区间
    # ======================
    def _generate_next_ranges(
        self,
        initial_time: datetime,
        count: int = 15,
    ):
        now = datetime.now().astimezone()

        # 计算当前时间到 initial_time 已经过了多少周期
        elapsed = now - initial_time
        cycles = elapsed // CYCLE_DURATION

        # 找到当前周期的起点
        cursor = initial_time + cycles * CYCLE_DURATION

        # 如果当前时间还在当前开启周期内，cursor 保持不变
        # 如果当前时间在关闭周期内，则 cursor 移到下一个开启
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
    # 指令：行政机库时间
    # ======================
    @filter.command("行政机库时间")
    async def executive_hangar_time(self, event: AstrMessageEvent):
        try:
            initial_time = self._load_initial_time()

            ranges = self._generate_next_ranges(
                initial_time,
                count=15,
            )

            lines = ["【开启时间】——【关闭时间】"]
            for start, end in ranges:
                lines.append(
                    f"{start.strftime('%Y/%m/%d %H:%M:%S')}——"
                    f"{end.strftime('%Y/%m/%d %H:%M:%S')}"
                )

            yield event.plain_result("\n".join(lines))

        except Exception as e:
            logger.exception(e)
            yield event.plain_result("❌ 查询行政机库时间失败")

    # ======================
    # 指令：同步行政机库时间
    # ======================
    @filter.command("同步行政机库时间")
    async def sync_executive_hangar_time(self, event: AstrMessageEvent):
        """
        用法：
        /同步行政机库时间 2026/1/4 17:35:08
        """
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
