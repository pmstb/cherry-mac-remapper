#!/usr/bin/env python3
"""
Cherry Mac Remapper — macOS Key Remapping & LaunchAgent Manager for Cherry Keyboards.

Uses Apple's built-in `/usr/bin/hidutil` to remap keys exclusively for connected
CHERRY USB keyboards (default: CHERRY MX BOARD 3.0S, VendorID 0x046A / 1130,
ProductID 0x0079 / 121) without affecting the internal MacBook keyboard or
Apple Magic Keyboard.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
import webbrowser
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# Default Hardware IDs for CHERRY MX BOARD 3.0S
CHERRY_VENDOR_ID = 0x046A  # 1130
CHERRY_DEFAULT_PRODUCT_ID = 0x0079  # 121 (CHERRY MX BOARD 3.0S)

HID_USAGE_PAGE_KEYBOARD = 0x700000000

# USB HID Keyboard Usage IDs (0x07 page)
KEYS: dict[str, int] = {
    # Modifiers
    "left_control": 0x7000000E0,
    "left_shift": 0x7000000E1,
    "left_alt": 0x7000000E2,      # Physical Alt on Windows -> Option on Mac
    "left_gui": 0x7000000E3,      # Physical Windows key -> Command on Mac
    "right_control": 0x7000000E4,
    "right_shift": 0x7000000E5,
    "right_alt": 0x7000000E6,     # Physical AltGr -> Right Option on Mac
    "right_gui": 0x7000000E7,     # Right Windows / Command
    "caps_lock": 0x700000039,
    "application": 0x700000065,   # PC Menu / Context key
    # German ISO swap keys
    "grave_accent_and_tilde": 0x700000035,  # ^ / ° (top-left next to 1)
    "non_us_backslash": 0x700000064,        # < / > / | (bottom-left next to Y)
    # Function keys F1 - F12
    "f1": 0x70000003A,
    "f2": 0x70000003B,
    "f3": 0x70000003C,
    "f4": 0x70000003D,
    "f5": 0x70000003E,
    "f6": 0x70000003F,
    "f7": 0x700000040,
    "f8": 0x700000041,
    "f9": 0x700000042,
    "f10": 0x700000043,
    "f11": 0x700000044,
    "f12": 0x700000045,
    # PC Navigation / Special cluster
    "print_screen": 0x700000046,
    "scroll_lock": 0x700000047,
    "pause": 0x700000048,
    "insert": 0x700000049,
    # Extended Function keys (macOS uses F14/F15 natively for Display Brightness!)
    "f13": 0x700000068,
    "f14": 0x700000069,  # macOS Brightness Down
    "f15": 0x70000006A,  # macOS Brightness Up
    "f16": 0x70000006B,
    "f17": 0x70000006C,
    "f18": 0x70000006D,
    "f19": 0x70000006E,
    # Media / Volume keys in Keyboard usage page
    "mute": 0x70000007F,
    "volume_up": 0x700000080,
    "volume_down": 0x700000081,
}

KEY_LABELS: dict[int, str] = {
    0x7000000E0: "Left Control (⌃)",
    0x7000000E1: "Left Shift (⇧)",
    0x7000000E2: "Left Option / Alt (⌥)",
    0x7000000E3: "Left Command / Win (⌘)",
    0x7000000E4: "Right Control (⌃)",
    0x7000000E5: "Right Shift (⇧)",
    0x7000000E6: "Right Option / AltGr (⌥)",
    0x7000000E7: "Right Command (⌘)",
    0x700000039: "Caps Lock (⇪)",
    0x700000065: "Menu / App Key",
    0x700000035: "^ / ° (oben links)",
    0x700000064: "< / > / | (neben Y)",
    0x70000003A: "F1",
    0x70000003B: "F2",
    0x70000003C: "F3",
    0x70000003D: "F4",
    0x70000003E: "F5",
    0x70000003F: "F6",
    0x700000040: "F7",
    0x700000041: "F8",
    0x700000042: "F9",
    0x700000043: "F10",
    0x700000044: "F11",
    0x700000045: "F12",
    0x700000046: "Druck / Print Screen",
    0x700000047: "Rollen / Scroll Lock",
    0x700000048: "Pause / Untbr",
    0x700000049: "Einfg / Insert",
    0x700000068: "F13 (Screenshot/Sondertaste)",
    0x700000069: "F14 (Display dunkler 🔅)",
    0x70000006A: "F15 (Display heller 🔆)",
    0x70000006B: "F16",
    0x70000007F: "Ton aus (Mute 🔇)",
    0x700000080: "Lauter (Volume Up 🔊)",
    0x700000081: "Leiser (Volume Down 🔉)",
}

LAUNCH_AGENT_LABEL = "de.pmstb.cherry-mac-remapper"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "cherry-mac-remapper" / "config.json"


@dataclass
class RemapConfig:
    """User-configurable remapping options for a Cherry keyboard on macOS."""

    vendor_id: int = CHERRY_VENDOR_ID
    product_id: int = CHERRY_DEFAULT_PRODUCT_ID

    # 1. Bottom-left modifiers: Swap Windows (GUI) and Left Alt so layout is:
    #    [Strg -> Control ⌃] [Win -> Option ⌥] [Alt -> Command ⌘] [Space]
    swap_left_win_and_alt: bool = True

    # 2. Bottom-right modifiers (AltGr & Right Ctrl):
    #    - "command_only": AltGr becomes Right Command (⌘), Right Strg stays Right Control (⌃), FN stays FN (Default!)
    #    - "mac_order":    AltGr becomes Right Command (⌘), Right Strg becomes Right Option (⌥)
    #    - "option_only":  AltGr stays Right Option (⌥), Right Strg stays Right Control (⌃)
    right_modifiers_mode: str = "command_only"

    # 3. German ISO-DE fix: Swap `^ / °` (0x35) and `< / > / |` (0x64)
    #    Disabled by default because macOS 14.3+/15+ requires Input Monitoring permission
    #    for alphanumeric key remapping in hidutil.
    swap_iso_section_and_less_than: bool = False

    # 4. Map PrintScreen / ScrollLock / Pause to F13 / F14 (Brightness -) / F15 (Brightness +)
    map_pc_cluster_to_mac_fn: bool = True

    # 5. Map F1/F2 to F14/F15 (Display Brightness) and F10/F11/F12 to Mute/VolDown/VolUp
    map_f_keys_to_mac_media: bool = False

    # 6. Optional: Caps Lock -> Control or Escape ("none", "control", "escape")
    caps_lock_mode: str = "none"

    # 7. Custom additional rules: list of {"src": int, "dst": int}
    custom_mappings: list[dict[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemapConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


def build_user_key_mapping(config: RemapConfig) -> list[dict[str, int]]:
    """
    Build the `UserKeyMapping` array expected by `/usr/bin/hidutil property`.
    Each entry maps `HIDKeyboardModifierMappingSrc` -> `HIDKeyboardModifierMappingDst`.
    """
    pairs: list[tuple[int, int]] = []

    # 1. Left Windows <-> Left Alt
    if config.swap_left_win_and_alt:
        pairs.append((KEYS["left_gui"], KEYS["left_alt"]))   # Win -> Left Option (⌥)
        pairs.append((KEYS["left_alt"], KEYS["left_gui"]))   # Alt -> Left Command (⌘)

    # 2. Right side modifiers (AltGr / Right Ctrl)
    if config.right_modifiers_mode == "mac_order":
        # Physical [Space] [AltGr] [FN] [Right Ctrl]
        # -> [Space] [Right Command ⌘] [FN] [Right Option ⌥]
        pairs.append((KEYS["right_alt"], KEYS["right_gui"]))
        pairs.append((KEYS["right_control"], KEYS["right_alt"]))
    elif config.right_modifiers_mode == "command_only":
        pairs.append((KEYS["right_alt"], KEYS["right_gui"]))
    # "option_only" leaves Right Alt as Right Option (0xE6) and Right Ctrl as Right Control (0xE4)

    # 3. German ISO-DE `< > |` vs `^ °` swap
    if config.swap_iso_section_and_less_than:
        pairs.append((KEYS["non_us_backslash"], KEYS["grave_accent_and_tilde"]))
        pairs.append((KEYS["grave_accent_and_tilde"], KEYS["non_us_backslash"]))

    # 4. PrintScreen / ScrollLock / Pause -> F13 / F14 (Brightness Down) / F15 (Brightness Up)
    if config.map_pc_cluster_to_mac_fn:
        pairs.append((KEYS["print_screen"], KEYS["f13"]))
        pairs.append((KEYS["scroll_lock"], KEYS["f14"]))
        pairs.append((KEYS["pause"], KEYS["f15"]))

    # 5. Optional F-Key Media & Brightness mapping
    if config.map_f_keys_to_mac_media:
        pairs.append((KEYS["f1"], KEYS["f14"]))         # F1 -> Brightness Down
        pairs.append((KEYS["f2"], KEYS["f15"]))         # F2 -> Brightness Up
        pairs.append((KEYS["f10"], KEYS["mute"]))       # F10 -> Mute
        pairs.append((KEYS["f11"], KEYS["volume_down"]))  # F11 -> Volume Down
        pairs.append((KEYS["f12"], KEYS["volume_up"]))    # F12 -> Volume Up

    # 6. Caps Lock option
    if config.caps_lock_mode == "control":
        pairs.append((KEYS["caps_lock"], KEYS["left_control"]))

    # 7. Custom mappings override any earlier mapping with the same source
    mapping_by_src: dict[int, int] = {src: dst for src, dst in pairs}
    for custom in config.custom_mappings:
        src = int(custom["src"])
        dst = int(custom["dst"])
        if src == dst:
            mapping_by_src.pop(src, None)
        else:
            mapping_by_src[src] = dst

    return [
        {
            "HIDKeyboardModifierMappingSrc": src,
            "HIDKeyboardModifierMappingDst": dst,
        }
        for src, dst in mapping_by_src.items()
    ]


def describe_mapping(mapping: list[dict[str, int]]) -> list[dict[str, Any]]:
    """Return human-readable descriptions for each active HID key mapping."""
    result = []
    for item in mapping:
        src = item["HIDKeyboardModifierMappingSrc"]
        dst = item["HIDKeyboardModifierMappingDst"]
        result.append(
            {
                "src": src,
                "dst": dst,
                "src_hex": f"0x{src:09X}",
                "dst_hex": f"0x{dst:09X}",
                "src_label": KEY_LABELS.get(src, f"Key 0x{src:X}"),
                "dst_label": KEY_LABELS.get(dst, f"Key 0x{dst:X}"),
            }
        )
    return result


def build_hidutil_command(config: RemapConfig, reset: bool = False) -> list[str]:
    """Construct the exact `/usr/bin/hidutil` command for the target keyboard."""
    matching = json.dumps(
        {"VendorID": config.vendor_id, "ProductID": config.product_id},
        separators=(",", ":"),
    )
    mapping = [] if reset else build_user_key_mapping(config)
    payload = json.dumps({"UserKeyMapping": mapping}, separators=(",", ":"))
    return [
        "/usr/bin/hidutil",
        "property",
        "--matching",
        matching,
        "--set",
        payload,
    ]


def detect_cherry_keyboards() -> list[dict[str, Any]]:
    """Detect connected Cherry USB/HID keyboards via `hidutil list`."""
    devices: dict[tuple[int, int], dict[str, Any]] = {}
    try:
        proc = subprocess.run(
            ["/usr/bin/hidutil", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        for line in proc.stdout.splitlines():
            # Match lines starting with hex VendorID and ProductID, e.g.:
            # 0x46a    0x79      0x120000   1         6     0x1000ad669 USB ... Mechanical Keyboard
            m = re.match(
                r"^\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+\S+\s+(\d+)\s+(\d+)\s+\S+\s+(\S+)\s+\S+\s+(.+?)\s{2,}",
                line,
            )
            if not m:
                continue
            vid = int(m.group(1), 16)
            pid = int(m.group(2), 16)
            usage_page = int(m.group(3))
            usage = int(m.group(4))
            transport = m.group(5)
            product_name = m.group(6).strip()

            if vid == CHERRY_VENDOR_ID or "cherry" in line.lower():
                key = (vid, pid)
                if key not in devices or (usage_page == 1 and usage == 6):
                    model_hint = (
                        "CHERRY MX BOARD 3.0S"
                        if (vid == 0x046A and pid == 0x0079)
                        else product_name
                    )
                    devices[key] = {
                        "vendor_id": vid,
                        "product_id": pid,
                        "vendor_hex": f"0x{vid:04X}",
                        "product_hex": f"0x{pid:04X}",
                        "product_name": product_name,
                        "model_name": model_hint,
                        "transport": transport,
                    }
    except Exception:
        pass

    return list(devices.values())


def get_active_hidutil_mapping(
    vendor_id: int = CHERRY_VENDOR_ID,
    product_id: int = CHERRY_DEFAULT_PRODUCT_ID,
) -> dict[str, Any]:
    """Query `hidutil` to see whether a UserKeyMapping is currently active on the device."""
    matching = json.dumps(
        {"VendorID": vendor_id, "ProductID": product_id},
        separators=(",", ":"),
    )
    try:
        proc = subprocess.run(
            [
                "/usr/bin/hidutil",
                "property",
                "--matching",
                matching,
                "--get",
                "UserKeyMapping",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        raw = proc.stdout.strip()
        is_active = bool(raw) and "(null)" not in raw and "(\n)" not in raw and "()" not in raw
        # When reset to `[]`, hidutil outputs an empty array `(\n)`
        has_entries = "HIDKeyboardModifierMappingSrc" in raw
        return {
            "active": is_active and has_entries,
            "raw_output": raw,
        }
    except Exception as exc:
        return {
            "active": False,
            "raw_output": str(exc),
        }


def apply_mapping(config: RemapConfig) -> dict[str, Any]:
    """Apply the configured key mapping via `hidutil`."""
    cmd = build_hidutil_command(config, reset=False)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    status = get_active_hidutil_mapping(config.vendor_id, config.product_id)
    mapping = build_user_key_mapping(config)
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": " ".join(cmd),
        "mapping_count": len(mapping),
        "mappings": describe_mapping(mapping),
        "device_active": status["active"],
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def reset_mapping(
    vendor_id: int = CHERRY_VENDOR_ID,
    product_id: int = CHERRY_DEFAULT_PRODUCT_ID,
) -> dict[str, Any]:
    """Reset the Cherry keyboard mapping back to factory Windows defaults."""
    cfg = RemapConfig(vendor_id=vendor_id, product_id=product_id)
    cmd = build_hidutil_command(cfg, reset=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    status = get_active_hidutil_mapping(vendor_id, product_id)
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": " ".join(cmd),
        "device_active": status["active"],
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def get_launch_agent_path(custom_dir: Path | None = None) -> Path:
    """Return path to `~/Library/LaunchAgents/de.pmstb.cherry-mac-remapper.plist`."""
    base = custom_dir if custom_dir is not None else (Path.home() / "Library" / "LaunchAgents")
    return base / f"{LAUNCH_AGENT_LABEL}.plist"


def generate_launch_agent_plist(config: RemapConfig) -> bytes:
    """Generate the macOS LaunchAgent XML plist content for `hidutil`."""
    cmd = build_hidutil_command(config, reset=False)
    plist_dict = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": cmd,
        "RunAtLoad": True,
        "KeepAlive": False,
    }
    return plistlib.dumps(plist_dict, fmt=plistlib.FMT_XML)


def get_autostart_status(custom_dir: Path | None = None) -> dict[str, Any]:
    """Check whether the LaunchAgent plist is installed."""
    plist_path = get_launch_agent_path(custom_dir)
    exists = plist_path.exists()
    plist_data: dict[str, Any] | None = None
    if exists:
        try:
            plist_data = plistlib.loads(plist_path.read_bytes())
        except Exception:
            plist_data = None
    return {
        "installed": exists,
        "plist_path": str(plist_path),
        "label": LAUNCH_AGENT_LABEL,
        "plist": plist_data,
    }


def install_autostart(
    config: RemapConfig,
    custom_dir: Path | None = None,
    run_launchctl: bool = True,
) -> dict[str, Any]:
    """
    Write the LaunchAgent `.plist` so the Cherry Mac layout is automatically
    applied at every login/boot, and immediately apply the mapping.
    """
    plist_path = get_launch_agent_path(custom_dir)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_bytes = generate_launch_agent_plist(config)
    plist_path.write_bytes(plist_bytes)

    if run_launchctl and custom_dir is None:
        uid = os.getuid()
        subprocess.run(
            ["/bin/launchctl", "bootout", f"gui/{uid}", str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["/bin/launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )

    apply_res = apply_mapping(config)
    return {
        "success": True,
        "installed": plist_path.exists(),
        "plist_path": str(plist_path),
        "apply_result": apply_res,
    }


def remove_autostart(
    vendor_id: int = CHERRY_VENDOR_ID,
    product_id: int = CHERRY_DEFAULT_PRODUCT_ID,
    custom_dir: Path | None = None,
    run_launchctl: bool = True,
    also_reset_keys: bool = True,
) -> dict[str, Any]:
    """
    Remove the LaunchAgent `.plist` and optionally reset the Cherry key mapping
    immediately (ideal when switching back to the native Mac keyboard).
    """
    plist_path = get_launch_agent_path(custom_dir)
    was_installed = plist_path.exists()

    if run_launchctl and custom_dir is None and was_installed:
        uid = os.getuid()
        subprocess.run(
            ["/bin/launchctl", "bootout", f"gui/{uid}", str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )

    if plist_path.exists():
        plist_path.unlink()

    reset_res = reset_mapping(vendor_id, product_id) if also_reset_keys else None
    return {
        "success": not plist_path.exists(),
        "was_installed": was_installed,
        "installed": plist_path.exists(),
        "plist_path": str(plist_path),
        "reset_result": reset_res,
    }


def save_config(config: RemapConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> RemapConfig:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RemapConfig.from_dict(data)
        except Exception:
            pass
    return RemapConfig()


def get_full_status(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Collect complete status of connected hardware, active mapping, and autostart."""
    config = load_config(config_path)
    devices = detect_cherry_keyboards()
    hid_status = get_active_hidutil_mapping(config.vendor_id, config.product_id)
    autostart = get_autostart_status()
    planned_mapping = build_user_key_mapping(config)
    return {
        "config": config.to_dict(),
        "devices": devices,
        "cherry_connected": len(devices) > 0,
        "mapping_active": hid_status["active"],
        "hidutil_raw": hid_status["raw_output"],
        "autostart": autostart,
        "planned_mappings": describe_mapping(planned_mapping),
        "hidutil_command": " ".join(build_hidutil_command(config, reset=False)),
        "reset_command": " ".join(build_hidutil_command(config, reset=True)),
    }


class RemapperHTTPRequestHandler(BaseHTTPRequestHandler):
    """Local HTTP API + static UI server for the Cherry Mac Remapper."""

    ui_root = Path(__file__).resolve().parent

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep console output clean
        pass

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            index_file = self.ui_root / "index.html"
            content = index_file.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path == "/api/status":
            self._send_json(get_full_status())
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_POST(self) -> None:
        body = self._read_json_body()

        if self.path == "/api/apply":
            current = load_config()
            if body:
                merged = {**current.to_dict(), **body}
                current = RemapConfig.from_dict(merged)
                save_config(current)
            res = apply_mapping(current)
            # If autostart is already installed, keep its plist updated with the latest config
            if get_autostart_status()["installed"]:
                install_autostart(current)
            self._send_json({"action": "apply", "result": res, "status": get_full_status()})
            return

        if self.path == "/api/reset":
            current = load_config()
            res = reset_mapping(current.vendor_id, current.product_id)
            self._send_json({"action": "reset", "result": res, "status": get_full_status()})
            return

        if self.path == "/api/autostart/install":
            current = load_config()
            if body:
                merged = {**current.to_dict(), **body}
                current = RemapConfig.from_dict(merged)
                save_config(current)
            res = install_autostart(current)
            self._send_json(
                {"action": "autostart_install", "result": res, "status": get_full_status()}
            )
            return

        if self.path == "/api/autostart/remove":
            current = load_config()
            also_reset = bool(body.get("also_reset_keys", True))
            res = remove_autostart(
                current.vendor_id,
                current.product_id,
                also_reset_keys=also_reset,
            )
            self._send_json(
                {"action": "autostart_remove", "result": res, "status": get_full_status()}
            )
            return

        self._send_json({"error": "Unknown endpoint"}, status=HTTPStatus.NOT_FOUND)


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = HTTPServer((host, port), RemapperHTTPRequestHandler)
    url = f"http://{host}:{port}"
    print(f"🍒 Cherry Mac Remapper läuft unter: {url}")
    print("Drücke Ctrl+C zum Beenden.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer beendet.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cherry Mac Remapper — Steuert das Mac-Tastenlayout für Cherry-Tastaturen via Apple hidutil."
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Zeigt erkannte Cherry-Tastatur, aktives Mapping und Autostart-Status")

    apply_p = sub.add_parser("apply", help="Aktiviert das Mac-Tastenlayout sofort für die Cherry-Tastatur")
    apply_p.add_argument(
        "--right-mode",
        choices=["mac_order", "option_only", "command_only"],
        default=None,
        help="Belegung der rechten Seite (AltGr / Strg rechts)",
    )
    apply_p.add_argument(
        "--no-iso-swap",
        action="store_true",
        help="Kein Tausch von < > | und ^ °",
    )
    apply_p.add_argument(
        "--f-media",
        action="store_true",
        help="F1/F2 auf Helligkeit und F10-F12 auf Lautstärke legen",
    )

    sub.add_parser("reset", help="Setzt die Cherry-Tastatur sofort auf Windows-Standard zurück")
    sub.add_parser("install-autostart", help="Richtet den macOS LaunchAgent für automatischen Start beim Login ein")
    sub.add_parser(
        "remove-autostart",
        help="Entfernt den Autostart-LaunchAgent und setzt die Tastenbelegung komplett zurück",
    )

    serve_p = sub.add_parser("serve", help="Startet die lokale Konfigurations-Oberfläche im Browser")
    serve_p.add_argument("--port", type=int, default=8765)
    serve_p.add_argument("--no-open", action="store_true", help="Browser nicht automatisch öffnen")

    args = parser.parse_args(argv)
    cmd = args.command or "status"

    if cmd == "status":
        st = get_full_status()
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return 0

    if cmd == "apply":
        cfg = load_config()
        if args.right_mode is not None:
            cfg.right_modifiers_mode = args.right_mode
        if args.no_iso_swap:
            cfg.swap_iso_section_and_less_than = False
        if args.f_media:
            cfg.map_f_keys_to_mac_media = True
        save_config(cfg)
        res = apply_mapping(cfg)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["success"] else 1

    if cmd == "reset":
        cfg = load_config()
        res = reset_mapping(cfg.vendor_id, cfg.product_id)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["success"] else 1

    if cmd == "install-autostart":
        cfg = load_config()
        res = install_autostart(cfg)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["success"] else 1

    if cmd == "remove-autostart":
        cfg = load_config()
        res = remove_autostart(cfg.vendor_id, cfg.product_id, also_reset_keys=True)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["success"] else 1

    if cmd == "serve":
        run_server(port=args.port, open_browser=not args.no_open)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
