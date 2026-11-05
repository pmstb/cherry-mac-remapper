#!/usr/bin/env python3
"""Automated test suite for Cherry Mac Remapper."""

from __future__ import annotations

import json
import plistlib
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cherry_remapper as cr  # noqa: E402


class TestCherryRemapperMappings(unittest.TestCase):
    """Test HID keycode mapping generation for all Mac layout configurations."""

    def test_default_mac_layout_mapping(self) -> None:
        cfg = cr.RemapConfig()
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }

        # 1. Left Win (0xE3) -> Left Option (0xE2) and Left Alt (0xE2) -> Left Command (0xE3)
        self.assertEqual(by_src[cr.KEYS["left_gui"]], cr.KEYS["left_alt"])
        self.assertEqual(by_src[cr.KEYS["left_alt"]], cr.KEYS["left_gui"])

        # 2. Right AltGr (0xE6) -> Right Command (0xE7), while Left & Right Strg stay Control (not remapped)
        self.assertEqual(by_src[cr.KEYS["right_alt"]], cr.KEYS["right_gui"])
        self.assertNotIn(cr.KEYS["left_control"], by_src)
        self.assertNotIn(cr.KEYS["right_control"], by_src)

        # 3. ISO swap is off by default so hidutil applies without macOS Input Monitoring warning
        self.assertNotIn(cr.KEYS["non_us_backslash"], by_src)
        self.assertNotIn(cr.KEYS["grave_accent_and_tilde"], by_src)

        # 4. PrintScreen / ScrollLock / Pause -> F13 / F14 / F15
        self.assertEqual(by_src[cr.KEYS["print_screen"]], cr.KEYS["f13"])
        self.assertEqual(by_src[cr.KEYS["scroll_lock"]], cr.KEYS["f14"])
        self.assertEqual(by_src[cr.KEYS["pause"]], cr.KEYS["f15"])

        # 5. Physical ≣ Menu key (0x65 between FN and Right Strg) -> Right Option (0xE6)
        self.assertEqual(by_src[cr.KEYS["application"]], cr.KEYS["right_alt"])

    def test_cherry_symbols_f_key_mode(self) -> None:
        cfg = cr.RemapConfig(f_keys_mode="cherry_symbols", menu_key_mode="none")
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }
        self.assertEqual(by_src[cr.KEYS["f1"]], cr.KEYS["mute"])
        self.assertEqual(by_src[cr.KEYS["f2"]], cr.KEYS["volume_down"])
        self.assertEqual(by_src[cr.KEYS["f3"]], cr.KEYS["volume_up"])
        self.assertNotIn(cr.KEYS["application"], by_src)

    def test_iso_swap_and_mac_order_when_enabled(self) -> None:
        cfg = cr.RemapConfig(
            right_modifiers_mode="mac_order",
            swap_iso_section_and_less_than=True,
        )
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }
        self.assertEqual(by_src[cr.KEYS["right_alt"]], cr.KEYS["right_gui"])
        self.assertEqual(by_src[cr.KEYS["right_control"]], cr.KEYS["right_alt"])
        self.assertEqual(
            by_src[cr.KEYS["non_us_backslash"]], cr.KEYS["grave_accent_and_tilde"]
        )
        self.assertEqual(
            by_src[cr.KEYS["grave_accent_and_tilde"]], cr.KEYS["non_us_backslash"]
        )

    def test_right_modifiers_option_only_mode(self) -> None:
        cfg = cr.RemapConfig(right_modifiers_mode="option_only")
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }
        # In option_only mode, Right Alt stays Right Option (not remapped)
        self.assertNotIn(cr.KEYS["right_alt"], by_src)
        self.assertNotIn(cr.KEYS["right_control"], by_src)

    def test_right_modifiers_command_only_mode(self) -> None:
        cfg = cr.RemapConfig(right_modifiers_mode="command_only")
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }
        self.assertEqual(by_src[cr.KEYS["right_alt"]], cr.KEYS["right_gui"])
        self.assertNotIn(cr.KEYS["right_control"], by_src)

    def test_f_keys_media_and_capslock_control(self) -> None:
        cfg = cr.RemapConfig(
            map_f_keys_to_mac_media=True,
            caps_lock_mode="control",
        )
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }
        self.assertEqual(by_src[cr.KEYS["f1"]], cr.KEYS["f14"])
        self.assertEqual(by_src[cr.KEYS["f2"]], cr.KEYS["f15"])
        self.assertEqual(by_src[cr.KEYS["f10"]], cr.KEYS["mute"])
        self.assertEqual(by_src[cr.KEYS["f11"]], cr.KEYS["volume_down"])
        self.assertEqual(by_src[cr.KEYS["f12"]], cr.KEYS["volume_up"])
        self.assertEqual(by_src[cr.KEYS["caps_lock"]], cr.KEYS["left_control"])

    def test_custom_mapping_override_and_identity_removal(self) -> None:
        cfg = cr.RemapConfig(
            custom_mappings=[
                {"src": cr.KEYS["print_screen"], "dst": cr.KEYS["print_screen"]},
                {"src": cr.KEYS["insert"], "dst": cr.KEYS["f16"]},
            ]
        )
        mapping = cr.build_user_key_mapping(cfg)
        by_src = {
            m["HIDKeyboardModifierMappingSrc"]: m["HIDKeyboardModifierMappingDst"]
            for m in mapping
        }
        self.assertNotIn(cr.KEYS["print_screen"], by_src)
        self.assertEqual(by_src[cr.KEYS["insert"]], cr.KEYS["f16"])

    def test_build_hidutil_command_apply_and_reset(self) -> None:
        cfg = cr.RemapConfig()
        apply_cmd = cr.build_hidutil_command(cfg, reset=False)
        self.assertEqual(apply_cmd[0], "/usr/bin/hidutil")
        self.assertEqual(apply_cmd[1], "property")
        self.assertEqual(apply_cmd[2], "--matching")
        self.assertEqual(json.loads(apply_cmd[3]), {"VendorID": 1130, "ProductID": 121})
        self.assertEqual(apply_cmd[4], "--set")
        parsed_set = json.loads(apply_cmd[5])
        self.assertIn("UserKeyMapping", parsed_set)
        self.assertGreater(len(parsed_set["UserKeyMapping"]), 0)

        reset_cmd = cr.build_hidutil_command(cfg, reset=True)
        self.assertEqual(json.loads(reset_cmd[5]), {"UserKeyMapping": []})


class TestLaunchAgentAndConfigPersistence(unittest.TestCase):
    """Test LaunchAgent plist creation, removal, and JSON config persistence."""

    def test_generate_and_manage_launch_agent(self) -> None:
        cfg = cr.RemapConfig()
        plist_bytes = cr.generate_launch_agent_plist(cfg)
        plist_data = plistlib.loads(plist_bytes)

        self.assertEqual(plist_data["Label"], cr.LAUNCH_AGENT_LABEL)
        self.assertTrue(plist_data["RunAtLoad"])
        self.assertEqual(plist_data["StartInterval"], 5)
        self.assertEqual(plist_data["ProgramArguments"][0], "/bin/sh")
        self.assertIn("/usr/bin/hidutil", plist_data["ProgramArguments"][2])
        self.assertIn("LaunchEvents", plist_data)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            st_before = cr.get_autostart_status(custom_dir=tmp_path)
            self.assertFalse(st_before["installed"])

            with patch.object(cr, "apply_mapping", return_value={"success": True}):
                res_install = cr.install_autostart(
                    cfg, custom_dir=tmp_path, run_launchctl=False
                )
            self.assertTrue(res_install["installed"])
            self.assertTrue(cr.get_autostart_status(custom_dir=tmp_path)["installed"])

            with patch.object(cr, "reset_mapping", return_value={"success": True}):
                res_remove = cr.remove_autostart(
                    custom_dir=tmp_path, run_launchctl=False, also_reset_keys=True
                )
            self.assertTrue(res_remove["success"])
            self.assertTrue(res_remove["was_installed"])
            self.assertFalse(res_remove["installed"])
            self.assertFalse(cr.get_autostart_status(custom_dir=tmp_path)["installed"])

    def test_save_and_load_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            original = cr.RemapConfig(
                right_modifiers_mode="option_only",
                swap_iso_section_and_less_than=False,
                map_f_keys_to_mac_media=True,
                caps_lock_mode="control",
            )
            cr.save_config(original, path=cfg_file)
            loaded = cr.load_config(path=cfg_file)
            self.assertEqual(loaded.right_modifiers_mode, "option_only")
            self.assertFalse(loaded.swap_iso_section_and_less_than)
            self.assertTrue(loaded.map_f_keys_to_mac_media)
            self.assertEqual(loaded.caps_lock_mode, "control")


class TestHTTPServerAPI(unittest.TestCase):
    """Test the local HTTP server endpoints and HTML serving."""

    def test_http_endpoints(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), cr.RemapperHTTPRequestHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"

        try:
            # 1. GET / serves index.html
            with urllib.request.urlopen(f"{base_url}/") as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("Cherry Mac Remapper", html)
                self.assertIn("Autostart entfernen", html)

            # 2. GET /api/status returns valid JSON status
            with urllib.request.urlopen(f"{base_url}/api/status") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("config", data)
                self.assertIn("devices", data)
                self.assertIn("planned_mappings", data)
        finally:
            server.shutdown()
            server.server_close()

    def test_live_status_and_hidutil_integration(self) -> None:
        status = cr.get_full_status()
        self.assertIsInstance(status["devices"], list)
        self.assertIn("mapping_active", status)
        self.assertTrue(status["hidutil_command"].startswith("/usr/bin/hidutil"))
        self.assertTrue(status["reset_command"].startswith("/usr/bin/hidutil"))


if __name__ == "__main__":
    unittest.main()
