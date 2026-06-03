import tempfile
import unittest
from pathlib import Path

from capcut_subtitle_converter import (
    CapCutDraftSource,
    SrtSource,
    discover_sources,
    extract_text_from_capcut_entry,
    format_srt_time,
    parse_srt,
    parse_srt_time,
    update_capcut_entry_text,
)


class SubtitleConverterTests(unittest.TestCase):
    def test_srt_round_trip_time_format(self):
        value = parse_srt_time("01:02:03,456")
        self.assertEqual(format_srt_time(value), "01:02:03,456")

    def test_parse_srt_multiline_text(self):
        blocks = parse_srt(
            "1\n00:00:01,000 --> 00:00:02,500\n第一行\n第二行\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\n下一句\n"
        )
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["text"], "第一行\n第二行")
        self.assertEqual(blocks[1]["start_us"], 3_000_000)

    def test_load_capcut_draft_text_and_timeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            draft = project / "draft_content.json"
            draft.write_text(
                '{"materials":{"texts":[{"id":"text-1","content":"简体中文"}]},'
                '"tracks":[{"segments":[{"material_id":"text-1",'
                '"target_timerange":{"start":1000000,"duration":2500000}}]}]}',
                encoding="utf-8",
            )

            source = CapCutDraftSource(draft, Path(tmpdir))
            source.load()

            self.assertEqual(source.name, "project")
            self.assertEqual(source.items[0].text, "简体中文")
            self.assertEqual(source.items[0].start_display, "00:00:01.000")
            self.assertEqual(source.items[0].end_display, "00:00:03.500")

    def test_capcut_json_string_content_is_preserved(self):
        entry = {"id": "text-1", "content": '{"text":"简体中文","styles":[]}'}

        self.assertEqual(extract_text_from_capcut_entry(entry), "简体中文")

        update_capcut_entry_text(entry, "繁體中文")

        self.assertIn("繁體中文", entry["content"])
        self.assertIn("styles", entry["content"])

    def test_discover_sources_finds_draft_and_srt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "project").mkdir()
            (root / "project" / "draft_content.json").write_text(
                '{"materials":{"texts":[]},"tracks":[]}', encoding="utf-8"
            )
            (root / "subtitle.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8"
            )

            sources = discover_sources(root)

            self.assertEqual(len(sources), 2)
            self.assertTrue(any(isinstance(source, CapCutDraftSource) for source in sources))
            self.assertTrue(any(isinstance(source, SrtSource) for source in sources))


if __name__ == "__main__":
    unittest.main()
