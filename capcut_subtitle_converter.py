#!/usr/bin/env python3
"""CapCut 字幕簡體轉繁體工具。

這是一個以 Tkinter 實作的桌面程式，可以匯入 CapCut 專案資料夾或 SRT
字幕資料夾，讀取既有字幕、批次簡轉繁、手動編輯每一條字幕並儲存回原檔。
"""
from __future__ import annotations

import copy
import json
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Iterable

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - depends on optional runtime package
    OpenCC = None  # type: ignore[assignment]


APP_TITLE = "CapCut 字幕簡體轉繁體工具"
CAPCUT_DRAFT_FILE = "draft_content.json"
SUPPORTED_TEXT_SUFFIXES = {".srt"}


# Fallback mapping is intentionally small: it keeps the app usable when OpenCC is
# not installed, while README and requirements still guide users to install OpenCC
# for accurate phrase-level conversion.
FALLBACK_CHAR_MAP = str.maketrans(
    {
        "汉": "漢",
        "语": "語",
        "简": "簡",
        "体": "體",
        "繁": "繁",
        "国": "國",
        "发": "發",
        "后": "後",
        "为": "為",
        "这": "這",
        "个": "個",
        "们": "們",
        "会": "會",
        "来": "來",
        "时": "時",
        "间": "間",
        "开": "開",
        "关": "關",
        "见": "見",
        "说": "說",
        "对": "對",
        "实": "實",
        "现": "現",
        "进": "進",
        "过": "過",
        "还": "還",
        "应": "應",
        "当": "當",
        "与": "與",
        "类": "類",
        "长": "長",
        "门": "門",
        "问": "問",
        "题": "題",
        "书": "書",
        "读": "讀",
        "写": "寫",
        "转": "轉",
        "换": "換",
        "导": "導",
        "入": "入",
        "项": "項",
        "目": "目",
        "栏": "欄",
        "显": "顯",
        "示": "示",
        "资": "資",
        "料": "料",
        "夹": "夾",
        "储": "儲",
        "存": "存",
        "内": "內",
        "容": "容",
        "启": "啟",
        "动": "動",
        "画": "畫",
        "声": "聲",
        "频": "頻",
        "视": "視",
        "输": "輸",
        "处": "處",
        "复": "複",
        "制": "製",
    }
)


@dataclass
class SubtitleItem:
    """A single editable subtitle entry."""

    source: "SubtitleSource"
    index: int
    start_us: int
    end_us: int
    text: str

    @property
    def start_display(self) -> str:
        return format_time(self.start_us)

    @property
    def end_display(self) -> str:
        return format_time(self.end_us)


class SubtitleSource:
    """Base class for subtitle files shown in the project list."""

    def __init__(self, path: Path, display_root: Path | None = None) -> None:
        self.path = path
        self.display_root = display_root
        self.items: list[SubtitleItem] = []
        self.dirty = False

    @property
    def name(self) -> str:
        if self.display_root:
            try:
                return str(self.path.relative_to(self.display_root))
            except ValueError:
                pass
        return self.path.name

    def load(self) -> None:
        raise NotImplementedError

    def save(self) -> None:
        raise NotImplementedError

    def set_text(self, item_index: int, new_text: str) -> None:
        self.items[item_index].text = new_text
        self.dirty = True

    def convert_all(self, converter: "TextConverter") -> int:
        changed = 0
        for item in self.items:
            converted = converter.convert(item.text)
            if converted != item.text:
                self.set_text(item.index, converted)
                changed += 1
        return changed


class CapCutDraftSource(SubtitleSource):
    """Subtitle adapter for CapCut's draft_content.json file."""

    def __init__(self, path: Path, display_root: Path | None = None) -> None:
        super().__init__(path, display_root)
        self.data: dict[str, Any] = {}
        self.text_entries: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        folder = self.path.parent
        if self.display_root:
            try:
                return str(folder.relative_to(self.display_root)) or folder.name
            except ValueError:
                pass
        return folder.name

    def load(self) -> None:
        with self.path.open("r", encoding="utf-8") as file_obj:
            self.data = json.load(file_obj)

        text_materials = self.data.get("materials", {}).get("texts", [])
        text_by_id = {entry.get("id"): entry for entry in text_materials if entry.get("id")}
        timeline_by_material_id = self._collect_timeline_ranges(text_by_id.keys())

        self.text_entries = []
        self.items = []
        for entry in text_materials:
            material_id = entry.get("id")
            raw_text = extract_text_from_capcut_entry(entry)
            if raw_text is None:
                continue

            start_us, end_us = timeline_by_material_id.get(material_id, (0, 0))
            item = SubtitleItem(
                source=self,
                index=len(self.items),
                start_us=start_us,
                end_us=end_us,
                text=raw_text,
            )
            self.text_entries.append(entry)
            self.items.append(item)
        self.dirty = False

    def save(self) -> None:
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        if not backup_path.exists():
            backup_path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        for item, entry in zip(self.items, self.text_entries):
            update_capcut_entry_text(entry, item.text)

        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        self.dirty = False

    def set_text(self, item_index: int, new_text: str) -> None:
        super().set_text(item_index, new_text)
        update_capcut_entry_text(self.text_entries[item_index], new_text)

    def _collect_timeline_ranges(self, material_ids: Iterable[str]) -> dict[str, tuple[int, int]]:
        wanted_ids = set(material_ids)
        result: dict[str, tuple[int, int]] = {}
        tracks = self.data.get("tracks", [])
        for track in tracks:
            for segment in track.get("segments", []) or []:
                material_id = segment.get("material_id")
                if material_id not in wanted_ids:
                    continue
                timerange = segment.get("target_timerange") or segment.get("source_timerange") or {}
                start = int(timerange.get("start", 0) or 0)
                duration = int(timerange.get("duration", 0) or 0)
                result[material_id] = (start, start + duration)
        return result


class SrtSource(SubtitleSource):
    """Subtitle adapter for .srt files."""

    def load(self) -> None:
        content = self.path.read_text(encoding="utf-8-sig")
        self.items = []
        for index, block in enumerate(parse_srt(content)):
            item = SubtitleItem(
                source=self,
                index=index,
                start_us=block["start_us"],
                end_us=block["end_us"],
                text=block["text"],
            )
            self.items.append(item)
        self.dirty = False

    def save(self) -> None:
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        if not backup_path.exists():
            backup_path.write_text(self.path.read_text(encoding="utf-8-sig"), encoding="utf-8")

        blocks = []
        for number, item in enumerate(self.items, start=1):
            blocks.append(
                f"{number}\n{format_srt_time(item.start_us)} --> {format_srt_time(item.end_us)}\n{item.text}"
            )
        self.path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        self.dirty = False


class TextConverter:
    """Simplified Chinese to Traditional Chinese converter."""

    def __init__(self) -> None:
        self.engine = OpenCC("s2t") if OpenCC else None

    @property
    def engine_name(self) -> str:
        return "OpenCC s2t" if self.engine else "內建簡易字表"

    def convert(self, text: str) -> str:
        if self.engine:
            return self.engine.convert(text)
        return text.translate(FALLBACK_CHAR_MAP)


class EditSubtitleDialog(simpledialog.Dialog):
    """Modal subtitle editor opened by clicking a row."""

    def __init__(self, parent: tk.Misc, item: SubtitleItem, converter: TextConverter) -> None:
        self.item = item
        self.converter = converter
        self.result_text: str | None = None
        super().__init__(parent, title="編輯字幕")

    def body(self, master: tk.Frame) -> tk.Widget:
        ttk.Label(master, text=f"開始時間：{self.item.start_display}").grid(row=0, column=0, sticky="w")
        ttk.Label(master, text=f"結束時間：{self.item.end_display}").grid(row=1, column=0, sticky="w")
        ttk.Label(master, text="字幕內容：").grid(row=2, column=0, sticky="nw", pady=(8, 0))
        self.text_widget = tk.Text(master, width=72, height=8, wrap="word")
        self.text_widget.grid(row=3, column=0, sticky="nsew")
        self.text_widget.insert("1.0", self.item.text)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(3, weight=1)
        return self.text_widget

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        ttk.Button(box, text="簡轉繁", command=self.convert_current).pack(side="left", padx=4)
        ttk.Button(box, text="確定", command=self.ok, default="active").pack(side="left", padx=4)
        ttk.Button(box, text="取消", command=self.cancel).pack(side="left", padx=4)
        box.pack(pady=8)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def convert_current(self) -> None:
        current = self.text_widget.get("1.0", "end-1c")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", self.converter.convert(current))

    def apply(self) -> None:
        self.result_text = self.text_widget.get("1.0", "end-1c")


class CapCutSubtitleApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x680")
        self.minsize(900, 520)

        self.converter = TextConverter()
        self.imported_folder: Path | None = None
        self.sources: list[SubtitleSource] = []
        self.current_source: SubtitleSource | None = None

        self._build_ui()
        self._update_status(f"請先匯入資料夾。轉換引擎：{self.converter.engine_name}")

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(side="top", fill="x")

        ttk.Button(toolbar, text="匯入資料夾", command=self.import_folder).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="讀取現有字幕", command=self.load_selected_source).pack(side="left", padx=6)
        ttk.Button(toolbar, text="重新整理", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(toolbar, text="全部簡轉繁", command=self.convert_current_source).pack(side="left", padx=6)
        ttk.Button(toolbar, text="儲存", command=self.save_current_source).pack(side="left", padx=6)

        self.folder_label = ttk.Label(toolbar, text="尚未匯入資料夾")
        self.folder_label.pack(side="left", padx=12)

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        left_frame = ttk.LabelFrame(paned, text="專案列表", padding=6)
        right_frame = ttk.LabelFrame(paned, text="字幕內容", padding=6)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=4)

        self.project_list = tk.Listbox(left_frame, exportselection=False)
        project_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.project_list.yview)
        self.project_list.configure(yscrollcommand=project_scroll.set)
        self.project_list.pack(side="left", fill="both", expand=True)
        project_scroll.pack(side="right", fill="y")
        self.project_list.bind("<<ListboxSelect>>", self.on_project_selected)

        columns = ("start", "end", "text")
        self.subtitle_table = ttk.Treeview(right_frame, columns=columns, show="headings", selectmode="browse")
        self.subtitle_table.heading("start", text="開始時間")
        self.subtitle_table.heading("end", text="結束時間")
        self.subtitle_table.heading("text", text="字幕內容")
        self.subtitle_table.column("start", width=130, anchor="center", stretch=False)
        self.subtitle_table.column("end", width=130, anchor="center", stretch=False)
        self.subtitle_table.column("text", width=650, anchor="w")
        table_scroll_y = ttk.Scrollbar(right_frame, orient="vertical", command=self.subtitle_table.yview)
        table_scroll_x = ttk.Scrollbar(right_frame, orient="horizontal", command=self.subtitle_table.xview)
        self.subtitle_table.configure(yscrollcommand=table_scroll_y.set, xscrollcommand=table_scroll_x.set)
        self.subtitle_table.grid(row=0, column=0, sticky="nsew")
        table_scroll_y.grid(row=0, column=1, sticky="ns")
        table_scroll_x.grid(row=1, column=0, sticky="ew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        self.subtitle_table.bind("<Return>", self.edit_selected_subtitle)
        self.subtitle_table.bind("<ButtonRelease-1>", self.edit_selected_subtitle)

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(8, 4)).pack(side="bottom", fill="x")

    def import_folder(self) -> None:
        folder = filedialog.askdirectory(title="選擇 CapCut 專案或字幕資料夾")
        if not folder:
            return
        self.imported_folder = Path(folder)
        self.folder_label.configure(text=str(self.imported_folder))
        self.refresh()

    def refresh(self) -> None:
        if not self.imported_folder:
            messagebox.showinfo("提示", "請先按「匯入資料夾」選擇資料夾。")
            return
        if self._confirm_discard_unsaved_changes() is False:
            return
        self.sources = discover_sources(self.imported_folder)
        self.current_source = None
        self.project_list.delete(0, "end")
        self.clear_subtitle_table()
        for source in self.sources:
            self.project_list.insert("end", source.name)
        if self.sources:
            self.project_list.selection_set(0)
            self.project_list.activate(0)
            self.on_project_selected()
            self._update_status(f"找到 {len(self.sources)} 個專案/字幕檔。")
        else:
            self._update_status("找不到 draft_content.json 或 .srt 字幕檔。")

    def on_project_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.project_list.curselection()
        if not selection:
            return
        if self.current_source and self.current_source.dirty:
            if not messagebox.askyesno("尚未儲存", "目前字幕尚未儲存，仍要切換專案嗎？"):
                previous_index = self.sources.index(self.current_source)
                self.project_list.selection_clear(0, "end")
                self.project_list.selection_set(previous_index)
                return
        self.current_source = self.sources[selection[0]]
        self.load_selected_source()

    def load_selected_source(self) -> None:
        if not self.current_source:
            messagebox.showinfo("提示", "請先在左欄選擇專案。")
            return
        try:
            self.current_source.load()
        except Exception as exc:  # noqa: BLE001 - GUI should report load errors to users
            messagebox.showerror("讀取失敗", f"無法讀取字幕：\n{exc}")
            return
        self.populate_subtitle_table()
        self._update_status(f"已讀取 {self.current_source.name}，共 {len(self.current_source.items)} 條字幕。")

    def convert_current_source(self) -> None:
        if not self.current_source:
            messagebox.showinfo("提示", "請先選擇並讀取專案。")
            return
        changed = self.current_source.convert_all(self.converter)
        self.populate_subtitle_table()
        self._update_status(f"已用 {self.converter.engine_name} 轉換 {changed} 條字幕，請按「儲存」寫回檔案。")

    def save_current_source(self) -> None:
        if not self.current_source:
            messagebox.showinfo("提示", "請先選擇並讀取專案。")
            return
        try:
            self.current_source.save()
        except Exception as exc:  # noqa: BLE001 - GUI should report save errors to users
            messagebox.showerror("儲存失敗", f"無法儲存字幕：\n{exc}")
            return
        self.populate_project_labels()
        self._update_status(f"已儲存 {self.current_source.name}。第一次儲存會保留 .bak 備份。")

    def edit_selected_subtitle(self, _event: tk.Event | None = None) -> None:
        if not self.current_source:
            return
        selected = self.subtitle_table.selection()
        if not selected:
            return
        item_index = int(selected[0])
        item = self.current_source.items[item_index]
        dialog = EditSubtitleDialog(self, item, self.converter)
        if dialog.result_text is None or dialog.result_text == item.text:
            return
        self.current_source.set_text(item_index, dialog.result_text)
        self.populate_subtitle_table(select_index=item_index)
        self.populate_project_labels()
        self._update_status("字幕已更新，請按「儲存」寫回檔案。")

    def populate_subtitle_table(self, select_index: int | None = None) -> None:
        self.clear_subtitle_table()
        if not self.current_source:
            return
        for item in self.current_source.items:
            self.subtitle_table.insert(
                "",
                "end",
                iid=str(item.index),
                values=(item.start_display, item.end_display, item.text.replace("\n", " / ")),
            )
        if select_index is not None:
            self.subtitle_table.selection_set(str(select_index))
            self.subtitle_table.focus(str(select_index))

    def populate_project_labels(self) -> None:
        self.project_list.delete(0, "end")
        for source in self.sources:
            marker = " *" if source.dirty else ""
            self.project_list.insert("end", source.name + marker)
        if self.current_source:
            self.project_list.selection_set(self.sources.index(self.current_source))

    def clear_subtitle_table(self) -> None:
        self.subtitle_table.delete(*self.subtitle_table.get_children())

    def _confirm_discard_unsaved_changes(self) -> bool:
        dirty_sources = [source for source in self.sources if source.dirty]
        if not dirty_sources:
            return True
        return messagebox.askyesno("尚未儲存", "有字幕尚未儲存，仍要重新整理並放棄變更嗎？")

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)


def discover_sources(folder: Path) -> list[SubtitleSource]:
    """Find CapCut draft files and SRT files under a folder."""

    sources: list[SubtitleSource] = []
    seen: set[Path] = set()
    if folder.name == CAPCUT_DRAFT_FILE and folder.is_file():
        sources.append(CapCutDraftSource(folder, folder.parent))
        return sources

    for path in sorted(folder.rglob(CAPCUT_DRAFT_FILE)):
        if should_skip_path(path):
            continue
        resolved = path.resolve()
        if resolved not in seen:
            sources.append(CapCutDraftSource(path, folder))
            seen.add(resolved)

    for path in sorted(folder.rglob("*")):
        if should_skip_path(path) or not path.is_file() or path.suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
            continue
        resolved = path.resolve()
        if resolved not in seen:
            sources.append(SrtSource(path, folder))
            seen.add(resolved)
    return sources


def should_skip_path(path: Path) -> bool:
    ignored_parts = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    return any(part in ignored_parts for part in path.parts)


def extract_text_from_capcut_entry(entry: dict[str, Any]) -> str | None:
    """Extract visible text from known CapCut text material shapes."""

    for key in ("content", "text"):
        value = entry.get(key)
        if isinstance(value, str):
            return extract_text_from_string_field(value)

    text_value = entry.get("text")
    if isinstance(text_value, dict):
        for key in ("content", "text"):
            nested = text_value.get(key)
            if isinstance(nested, str):
                return nested

    extra = entry.get("extra")
    if isinstance(extra, str):
        try:
            parsed_extra = json.loads(extra)
        except json.JSONDecodeError:
            return None
        for key in ("content", "text"):
            value = parsed_extra.get(key)
            if isinstance(value, str):
                return value
    return None


def extract_text_from_string_field(value: str) -> str:
    """Return plain text from a CapCut string field that may contain JSON."""

    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed_value, dict):
        for key in ("content", "text"):
            nested = parsed_value.get(key)
            if isinstance(nested, str):
                return nested
    return value


def update_text_in_string_field(value: str, text: str) -> str:
    """Update a CapCut string field while preserving JSON wrappers when present."""

    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        return text
    if isinstance(parsed_value, dict):
        for key in ("content", "text"):
            if isinstance(parsed_value.get(key), str):
                parsed_value[key] = text
                return json.dumps(parsed_value, ensure_ascii=False)
    return text


def update_capcut_entry_text(entry: dict[str, Any], text: str) -> None:
    """Update text in all recognized CapCut fields without deleting unknown data."""

    for key in ("content", "text"):
        value = entry.get(key)
        if isinstance(value, str):
            entry[key] = update_text_in_string_field(value, text)
            return

    text_value = entry.get("text")
    if isinstance(text_value, dict):
        for key in ("content", "text"):
            if isinstance(text_value.get(key), str):
                text_value[key] = text
                return

    extra = entry.get("extra")
    if isinstance(extra, str):
        try:
            parsed_extra = json.loads(extra)
        except json.JSONDecodeError:
            return
        changed_extra = copy.deepcopy(parsed_extra)
        for key in ("content", "text"):
            if isinstance(changed_extra.get(key), str):
                changed_extra[key] = text
                entry["extra"] = json.dumps(changed_extra, ensure_ascii=False)
                return


def parse_srt(content: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?:^|\n)\s*(?:\d+\s*\n)?"
        r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
        r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})[^\n]*\n"
        r"(?P<text>.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    blocks = []
    for match in pattern.finditer(content.strip()):
        blocks.append(
            {
                "start_us": parse_srt_time(match.group("start")),
                "end_us": parse_srt_time(match.group("end")),
                "text": match.group("text").strip(),
            }
        )
    return blocks


def parse_srt_time(value: str) -> int:
    hours, minutes, rest = value.split(":")
    seconds, milliseconds = rest.split(",")
    total_ms = (
        int(hours) * 60 * 60 * 1000
        + int(minutes) * 60 * 1000
        + int(seconds) * 1000
        + int(milliseconds)
    )
    return total_ms * 1000


def format_srt_time(value_us: int) -> str:
    value_ms = max(0, value_us // 1000)
    milliseconds = value_ms % 1000
    total_seconds = value_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def format_time(value_us: int) -> str:
    value_ms = max(0, value_us // 1000)
    milliseconds = value_ms % 1000
    total_seconds = value_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def main() -> None:
    app = CapCutSubtitleApp()
    app.mainloop()


if __name__ == "__main__":
    main()
