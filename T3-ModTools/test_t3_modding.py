import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

from t3_modding import ModManager, ModProject


class BuildCleanupTests(unittest.TestCase):
    def test_build_recreates_load_order_from_current_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game_folder = root / "game"
            mods_folder = game_folder / "mods"
            project_folder = mods_folder / "current_mod"
            files_folder = project_folder / "files"
            files_folder.mkdir(parents=True)
            (files_folder / "asset.txt").write_text("asset", encoding="utf-8")

            manager = ModManager(game_folder, mods_folder, log=Mock())
            manager.load_order_path.write_text(
                json.dumps({"format_version": 1, "mods": [{"id": "stale_mod", "enabled": True}]}),
                encoding="utf-8",
            )
            manager.load_order_path.with_suffix(".tmp").write_text("stale temporary state", encoding="utf-8")
            project = ModProject("current_mod", "Current Mod", project_folder, enabled=True)

            manager.build([project])

            state = json.loads(manager.load_order_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"format_version": 1, "mods": [{"id": "current_mod", "enabled": True}]},
                state,
            )
            self.assertFalse(manager.load_order_path.with_suffix(".tmp").exists())


class BuildTransactionTests(unittest.TestCase):
    def make_manager(self):
        manager = object.__new__(ModManager)
        manager.game_folder = Path("game")
        manager.mods_folder = Path("mods")
        manager.log = Mock()
        manager.build = Mock(return_value="package")
        manager.install_loader = Mock(return_value="executable")
        return manager

    @staticmethod
    def exists_for_outputs_and_backups(path):
        return path in (Path("mods/Mods.Cod"), Path("game/T3_Modded.exe")) or \
            ".build_backup." in path.name

    def test_stale_fixed_backup_is_not_reused(self):
        manager = self.make_manager()
        replacements = []

        with patch.object(Path, "exists", self.exists_for_outputs_and_backups), \
                patch("t3_modding.os.replace", side_effect=lambda source, target: replacements.append((source, target))), \
                patch.object(Path, "unlink") as unlink:
            result = manager.build_all([])

        self.assertEqual("package", result.package)
        self.assertEqual("executable", result.executable)
        self.assertEqual(2, len(replacements))
        self.assertTrue(all(".build_backup." in target.name for _, target in replacements))
        self.assertNotIn(Path("game/T3_Modded.exe.build_backup"), [target for _, target in replacements])
        self.assertEqual(2, unlink.call_count)

    def test_partial_staging_failure_restores_the_first_output(self):
        manager = self.make_manager()
        replacements = []

        def replace(source, target):
            replacements.append((source, target))
            if source == Path("game/T3_Modded.exe"):
                raise PermissionError(5, "Access is denied", str(target))

        with patch.object(Path, "exists", self.exists_for_outputs_and_backups), \
                patch("t3_modding.os.replace", side_effect=replace), \
                patch.object(Path, "unlink") as unlink:
            with self.assertRaises(PermissionError):
                manager.build_all([])

        self.assertEqual(3, len(replacements))
        pack_backup = replacements[0][1]
        self.assertEqual((pack_backup, Path("mods/Mods.Cod")), replacements[2])
        unlink.assert_not_called()


class ExecutablePatchTests(unittest.TestCase):
    class FakePE:
        @staticmethod
        def section_range(name, file_size):
            if name != ".text":
                raise ValueError(name)
            return 0, file_size

    def setUp(self):
        self.manager = object.__new__(ModManager)
        self.project = ModProject("test_mod", "Test Mod", Path("mods/test_mod"))

    def test_aob_write_writes_relative_to_unique_anchor(self):
        original = bytes.fromhex("AA BB CC DD 00 00 00 00 EE FF")
        data = bytearray(original)
        patch_data = {
            "id": "inject",
            "type": "aob_write",
            "section": ".text",
            "pattern": "AA BB CC DD",
            "write_offset": "0x4",
            "expected": "00 00 00 00",
            "replacement": "11 22 33 44",
            "expected_matches": 1,
        }

        result = self.manager._apply_manifest_patch(
            original, data, self.FakePE(), {}, self.project, patch_data, 1
        )

        self.assertEqual(bytes.fromhex("AA BB CC DD 11 22 33 44 EE FF"), bytes(data))
        self.assertEqual(4, result.file_offset)
        self.assertEqual(4, result.size)

    def test_aob_write_rejects_unexpected_destination_bytes(self):
        original = bytes.fromhex("AA BB CC DD 00 01 00 00 EE FF")
        patch_data = {
            "id": "inject",
            "type": "aob_write",
            "section": ".text",
            "pattern": "AA BB CC DD",
            "write_offset": 4,
            "expected": "00 00 00 00",
            "replacement": "11 22 33 44",
            "expected_matches": 1,
        }

        with self.assertRaisesRegex(ValueError, "expected bytes do not match"):
            self.manager._apply_manifest_patch(
                original, bytearray(original), self.FakePE(), {}, self.project, patch_data, 1
            )


if __name__ == "__main__":
    unittest.main()
