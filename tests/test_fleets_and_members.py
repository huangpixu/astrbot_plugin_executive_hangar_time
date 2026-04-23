from pathlib import Path

import tempfile
import unittest
from unittest import mock


class FakeEvent:
    def __init__(self, message_str: str, *, is_wake: bool = True, is_at: bool = True):
        self.message_str = message_str
        self.is_wake = is_wake
        self.is_at_or_wake_command = is_at

    def plain_result(self, text: str):
        return ("plain", text)

    def image_result(self, url_or_path: str):
        return ("image", url_or_path)


def _get_first_plain_text(result) -> str:
    if isinstance(result, tuple) and len(result) == 2 and result[0] == "plain":
        return str(result[1])
    return str(result)


def _is_image_result(result) -> bool:
    return isinstance(result, tuple) and len(result) == 2 and result[0] == "image"


def _make_plugin(main_mod):
    plugin = main_mod.TheHomewardSail.__new__(main_mod.TheHomewardSail)
    plugin.members_cache_by_symbol = {}
    plugin.last_fetch_time_by_symbol = {}
    plugin.fleets = {}
    return plugin


class FleetsAndMembersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import sys
        import types

        class _LoggerStub:
            def debug(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                return None

            def exception(self, *args, **kwargs):
                return None

        class _FilterStub:
            def command(self, _name: str):
                def deco(fn):
                    return fn

                return deco

            def regex(self, _pattern: str):
                def deco(fn):
                    return fn

                return deco

        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.tmp_path.mkdir(parents=True, exist_ok=True)

        astrbot_mod = types.ModuleType("astrbot")
        astrbot_api_mod = types.ModuleType("astrbot.api")
        astrbot_api_event_mod = types.ModuleType("astrbot.api.event")
        astrbot_api_star_mod = types.ModuleType("astrbot.api.star")

        astrbot_api_mod.logger = _LoggerStub()

        astrbot_api_event_mod.filter = _FilterStub()
        astrbot_api_event_mod.AstrMessageEvent = object

        class _StarToolsStub:
            @classmethod
            def get_data_dir(cls, plugin_name: str | None = None):
                return self.tmp_path

        def _register_stub(*args, **kwargs):
            def deco(cls):
                return cls

            return deco

        astrbot_api_star_mod.Context = object
        astrbot_api_star_mod.Star = object
        astrbot_api_star_mod.register = _register_stub
        astrbot_api_star_mod.StarTools = _StarToolsStub

        sys.modules["astrbot"] = astrbot_mod
        sys.modules["astrbot.api"] = astrbot_api_mod
        sys.modules["astrbot.api.event"] = astrbot_api_event_mod
        sys.modules["astrbot.api.star"] = astrbot_api_star_mod

        import sys

        sys.path.insert(0, "/data/code/hpx_code/AstrBot/data/plugins")
        import astrbot_plugin_executive_hangar_time.main as main_mod
        import astrbot_plugin_executive_hangar_time.text_to_img as t2i
        from PIL import ImageFont

        self.main_mod = main_mod

        self._orig_data_dir = getattr(main_mod, "DATA_DIR")
        self._orig_hangar = getattr(main_mod, "HANGAR_TIME_FILE")
        self._orig_fleets = getattr(main_mod, "FLEETS_FILE")

        main_mod.DATA_DIR = self.tmp_path
        main_mod.HANGAR_TIME_FILE = self.tmp_path / "hangar_time.json"
        main_mod.FLEETS_FILE = self.tmp_path / "fleets.json"

        main_mod.HANGAR_TIME_FILE.write_text(
            '{"initial_open_time":"2026-01-01T00:00:00+08:00"}',
            encoding="utf-8",
        )
        main_mod.FLEETS_FILE.write_text('{"鹿港":"GFHB"}', encoding="utf-8")

        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
        font_path = next((p for p in font_candidates if Path(p).exists()), None)
        if not font_path:
            raise RuntimeError("No TrueType font found for tests")

        self._t2i_get_font_patch = mock.patch.object(
            t2i,
            "get_font",
            autospec=True,
            side_effect=lambda size, data_dir: ImageFont.truetype(font_path, size),
        )
        self._t2i_get_font_patch.start()

    def tearDown(self):
        self._t2i_get_font_patch.stop()
        self.main_mod.DATA_DIR = self._orig_data_dir
        self.main_mod.HANGAR_TIME_FILE = self._orig_hangar
        self.main_mod.FLEETS_FILE = self._orig_fleets
        self.tmpdir.cleanup()

    async def test_add_fleet_persists_and_sync(self):
        plugin = _make_plugin(self.main_mod)
        plugin._sync_fleets_from_disk()

        event = FakeEvent("添加舰队 新港-NEWH")
        results = [r async for r in plugin.add_fleet(event, mapping="新港-NEWH")]
        self.assertTrue(results)
        self.assertIn("已保存舰队", _get_first_plain_text(results[-1]))

        plugin2 = _make_plugin(self.main_mod)
        fleets = plugin2._sync_fleets_from_disk()
        self.assertEqual(fleets["新港"], "NEWH")

    async def test_query_members_paginates_images(self):
        plugin = _make_plugin(self.main_mod)
        plugin._sync_fleets_from_disk()

        async def fake_fetch(symbol: str, *args, **kwargs):
            return [
                {
                    "handle": f"user{i}",
                    "moniker": f"m{i}",
                    "rank": "正式成员",
                    "stars": 0,
                    "color_level": "black",
                    "rank_weight": 3,
                    "is_hidden": False,
                }
                for i in range(450)
            ]

        with mock.patch.object(self.main_mod, "fetch_org_members", new=fake_fetch):
            event = FakeEvent("/查成员 鹿港")
            results = [r async for r in plugin.query_members(event, fleet="鹿港", page=None)]

        self.assertTrue(any("拆分为 3 张图片" in _get_first_plain_text(r) for r in results))
        self.assertEqual(sum(1 for r in results if _is_image_result(r)), 3)

    async def test_query_members_page_out_of_range(self):
        plugin = _make_plugin(self.main_mod)
        plugin._sync_fleets_from_disk()

        async def fake_fetch(symbol: str, *args, **kwargs):
            return [
                {
                    "handle": f"user{i}",
                    "moniker": f"m{i}",
                    "rank": "正式成员",
                    "stars": 0,
                    "color_level": "black",
                    "rank_weight": 3,
                    "is_hidden": False,
                }
                for i in range(50)
            ]

        with mock.patch.object(self.main_mod, "fetch_org_members", new=fake_fetch):
            event = FakeEvent("/查成员 鹿港 2")
            results = [r async for r in plugin.query_members(event, fleet="鹿港", page=2)]

        self.assertTrue(any("页码超出范围" in _get_first_plain_text(r) for r in results))

    async def test_query_members_regex_requires_wake(self):
        plugin = _make_plugin(self.main_mod)
        plugin._sync_fleets_from_disk()

        async def fake_fetch(symbol: str, *args, **kwargs):
            return []

        with mock.patch.object(self.main_mod, "fetch_org_members", new=fake_fetch):
            event = FakeEvent("查鹿港成员", is_wake=False, is_at=False)
            results = [r async for r in plugin.query_members_regex(event)]

        self.assertEqual(results, [])
