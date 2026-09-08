"""Digital (TTL) pulse-sequence editor — the native control surface for a
`mock_pulse_sequencer`-style adapter's `sequence` settable (a `DeviceSchema`
dtype `"json"` field: a flat list of `{"duration_ns": float, "channels":
[int, ...]}` steps — see instruments/mock/pulse_sequencers.py). No generic
component renders a "json"-dtype settable (SettingsTreeComponent skips it
outright — see its own docstring), so this is a dedicated, adapter-shape-
aware component rather than a config-tree entry.

A `QTableWidget` (one row per step: duration + comma-separated channel
indices) is the editable source of truth; "Upload" writes the whole list
in one `write({"sequence": [...]})` call, matching how the adapter itself
replaces its sequence wholesale rather than incrementally. Below it, a
read-only digital timing-diagram preview (one step-trace per channel)
redraws from the same in-memory row data on every edit — deliberately not
tied to live polling (this instrument doesn't auto-poll; see
ui_blocks.toml's `[detector."GENERIC"]` block), since the sequence being
edited is what's about to be uploaded, not yet necessarily what's running.
"""

from __future__ import annotations

from typing import Any

import httpx
import pyqtgraph as pg
from components.base import UIComponent
from components.widgets import IconButton, dock
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class PulseSequenceEditorComponent(UIComponent):
    component_type = "pulse_sequence_editor"
    default_params = {"dock_title": "Pulse Sequence"}

    def build(self) -> None:
        window = self.window
        self.n_channels = self._fetch_n_channels()

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Duration (ns)", "Channels (e.g. 0,2)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(lambda _item: self._redraw_preview())
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        add_btn = IconButton("Add step")
        # clicked emits a bool `checked` arg — a bare .connect(self._add_row)
        # would pass it as duration_ns; wrap so a click always uses the
        # method's own defaults.
        add_btn.clicked.connect(lambda _checked=False: self._add_row())
        remove_btn = IconButton("Remove step", "edit-delete")
        remove_btn.clicked.connect(self._remove_selected_row)
        upload_btn = IconButton("Upload", "document-save")
        upload_btn.clicked.connect(self._upload)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(upload_btn)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setProperty("class", "muted")
        layout.addWidget(self.status_label)

        self.preview = pg.PlotWidget()
        self.preview.setLabel("bottom", "Time", units="ns")
        self.preview.setMouseEnabled(x=False, y=False)
        self.preview.setMaximumHeight(160)
        self._preview_curves = [
            self.preview.plot(pen=pg.mkPen((i * 60) % 255, 220, 255, width=2))
            for i in range(max(self.n_channels, 1))
        ]
        layout.addWidget(self.preview)

        d = dock(self.params["dock_title"], window)
        d.setWidget(content)
        self.add_dock(d, "left")

        self._load_existing_sequence()

    def on_data(self, data: dict) -> None:
        if "running" in data:
            state = "Running" if data["running"] else "Stopped"
            self.status_label.setText(
                f"{state} — {data.get('sequence_length', '?')} steps, "
                f"{data.get('total_duration_ns', 0):.0f} ns total"
            )

    # ---- table <-> sequence list ----

    def _fetch_n_channels(self) -> int:
        try:
            data = self.ctx.client.read(self.ctx.instrument.id)
            return int(data.get("n_channels", 8))
        except Exception:
            return 8

    def _load_existing_sequence(self) -> None:
        try:
            inst = self.ctx.client.get_instrument(self.ctx.instrument.id)
        except Exception:
            inst = None
        sequence = (inst or {}).get("custom_settings", {}).get("sequence") or []
        self.table.blockSignals(True)
        for step in sequence:
            self._add_row(step.get("duration_ns", 0.0), step.get("channels", []))
        self.table.blockSignals(False)
        self._redraw_preview()

    def _add_row(self, duration_ns: float = 100.0, channels: list[int] | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(duration_ns)))
        channels_text = ",".join(str(c) for c in (channels or []))
        self.table.setItem(row, 1, QTableWidgetItem(channels_text))
        self._redraw_preview()

    def _remove_selected_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._redraw_preview()

    def _read_sequence(self) -> list[dict[str, Any]]:
        sequence = []
        for row in range(self.table.rowCount()):
            duration_item = self.table.item(row, 0)
            channels_item = self.table.item(row, 1)
            try:
                duration_ns = float(duration_item.text()) if duration_item else 0.0
            except ValueError:
                duration_ns = 0.0
            channels_text = channels_item.text() if channels_item else ""
            channels = [
                int(c.strip()) for c in channels_text.split(",") if c.strip() != ""
            ]
            sequence.append({"duration_ns": duration_ns, "channels": channels})
        return sequence

    def _upload(self) -> None:
        ctx = self.ctx
        sequence = self._read_sequence()
        try:
            ctx.client.write(ctx.instrument.id, {"sequence": sequence})
            self.status_label.setText(f"Uploaded {len(sequence)} steps")
        except httpx.HTTPStatusError as e:
            self.status_label.setText(f"Upload failed: {e.response.status_code} {e.response.text}")
        except Exception as e:
            self.status_label.setText(f"Upload failed: {e}")

    # ---- timing-diagram preview ----

    def _redraw_preview(self) -> None:
        sequence = self._read_sequence()
        n = max(self.n_channels, 1)
        times = [[0.0] for _ in range(n)]
        levels = [[0.0] for _ in range(n)]
        t = 0.0
        for step in sequence:
            duration = max(step["duration_ns"], 0.0)
            active = set(step["channels"])
            for ch in range(n):
                level = 1.0 if ch in active else 0.0
                times[ch].append(t)
                levels[ch].append(level)
                times[ch].append(t + duration)
                levels[ch].append(level)
            t += duration
        for ch in range(n):
            offset = ch * 1.5
            y = [v + offset for v in levels[ch]]
            self._preview_curves[ch].setData(times[ch], y)
