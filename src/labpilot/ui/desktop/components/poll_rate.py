"""Poll-interval default: not a real instrument parameter (it's purely how
often this native window's own poller re-reads the instrument over HTTP),
so it isn't a "generic setting" the way an instrument-type's real
acquisition parameters are (e.g. a detector's `integration_time_ms`,
already exposed by SettingsTreeComponent from the instrument's own
DeviceSchema) — it used to also render as its own live-adjustable spinbox,
which made every window's config surface include one control that doesn't
correspond to anything on the actual instrument. Now purely internal:
`default_ms` (tier-2, from ui_blocks.toml's `[kind."dimensionality"]` block
spec — e.g. detectors default to 200ms, a slower default for ND scans)
just sets `ctx.poll_interval` once at window-build time. The window's
config-facing UI is left showing only genuine generic/manufacturer
settings (SettingsTreeComponent).
"""

from __future__ import annotations

from components.base import UIComponent


class PollRateComponent(UIComponent):
    component_type = "poll_rate"
    default_params = {"default_ms": 200}

    def build(self) -> None:
        self.ctx.poll_interval = int(self.params["default_ms"])
