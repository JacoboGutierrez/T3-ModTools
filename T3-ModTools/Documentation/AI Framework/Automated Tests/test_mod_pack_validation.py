"""Pack validation uses installed read-only assets and isolated binary outputs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys
import zipfile

TOOLS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(TOOLS))
import t3_modding as modding
from t3_anm_compat import CompatibilityPlan
import t3_anm_runtime


ANM = b'''Animation {
Fps 30
MaxTimeValue 1
Time 0 { Joint { Name "|root"
TransformationMatrix { 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 }
} }
}
'''


class PackValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='t3-pack-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        self.manager = modding.ModManager(self.game, log=lambda _: None)
        (self.game / 'T3.exe').write_bytes(b'pristine player fixture')
        (self.game / 'Ai.Dll').write_bytes(b'pristine AI fixture')
        with zipfile.ZipFile(self.game / 'Game.cod', 'w') as archive:
            archive.writestr('readme.txt', b'original asset fixture')
        self.pack = modding.ModProject('pack', 'Pack', self.root / 'staged_pack')
        self.pack.files_path.mkdir(parents=True)
        (self.pack.files_path / 'custom.anm').write_bytes(ANM)
        self.pack.patches_path.mkdir()
        self.pack.executable_patch_path.write_text(json.dumps({
            'format_version': 1, 'patches': [],
        }))
        self.validation = self.root / 'validation'

    def test_uses_original_archives_without_copying_or_modifying_them(self):
        originals = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in self.game.iterdir() if p.is_file()}
        installed = self.game / 'T3_Modded.exe'
        installed.write_bytes(b'previous working build')
        original_analyze = modding.analyze_anm_compatibility
        received = []

        def install(validator, projects, *, synchronize_runtime=True, anm_plan=None):
            # Match the loader's actual fallback, which used to fail in validation/.
            if anm_plan is None:
                anm_plan = modding.analyze_anm_compatibility(validator.game_folder, projects)
            self.assertFalse(synchronize_runtime)
            self.assertEqual(projects, [self.pack])
            self.assertEqual(validator.game_folder, self.validation)
            self.assertFalse((self.validation / 'Game.cod').exists())
            self.assertEqual(anm_plan.report['archives'][0]['name'], 'Game.cod')
            self.assertEqual(anm_plan.report['animations'][0]['path'], 'custom.anm')
            received.append(anm_plan)
            (validator.game_folder / 'T3_Modded.exe').write_bytes(b'test output only')

        with mock.patch.object(modding, 'analyze_anm_compatibility', wraps=original_analyze) as analyze:
            with mock.patch.object(modding.ModManager, 'install_loader', install):
                self.manager._validate_pack_patches(self.pack, self.validation)
        analyze.assert_called_once_with(self.game, [self.pack])
        self.assertEqual(len(received), 1)
        self.assertEqual(installed.read_bytes(), b'previous working build')
        for path, digest in originals.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_automatic_ai_target_is_copied_even_without_explicit_ai_patch(self):
        plan = CompatibilityPlan(navigation=True)
        def install(validator, projects, **kwargs):
            self.assertIs(kwargs['anm_plan'], plan)
            self.assertEqual((validator.game_folder / 'Ai.Dll').read_bytes(), b'pristine AI fixture')
        with mock.patch.object(modding, 'analyze_anm_compatibility', return_value=plan):
            with mock.patch.object(modding.ModManager, 'install_loader', install):
                self.manager._validate_pack_patches(self.pack, self.validation)

    def test_missing_installed_archives_still_rejects_anm_pack(self):
        (self.game / 'Game.cod').unlink()
        with mock.patch.object(modding.ModManager, 'install_loader') as install:
            with self.assertRaisesRegex(ValueError, 'installed original COD archives'):
                self.manager._validate_pack_patches(self.pack, self.validation)
        install.assert_not_called()

    def test_missing_required_ai_binary_is_not_silently_ignored(self):
        (self.game / 'Ai.Dll').unlink()
        with mock.patch.object(modding, 'analyze_anm_compatibility', return_value=CompatibilityPlan(navigation=True)):
            with self.assertRaisesRegex(FileNotFoundError, 'Ai.Dll'):
                self.manager._validate_pack_patches(self.pack, self.validation)

    def test_non_animation_pack_needs_no_archives(self):
        (self.game / 'Game.cod').unlink()
        (self.pack.files_path / 'custom.anm').unlink()
        with mock.patch.object(modding.ModManager, 'install_loader') as install:
            self.manager._validate_pack_patches(self.pack, self.validation)
        self.assertEqual(install.call_args.kwargs['anm_plan'].report['archives'], [])

    def source(self, name, patches=(), enabled=True):
        folder = self.manager.mods_folder / name
        project = modding.ModProject(name, name, folder, enabled=enabled)
        project.files_path.mkdir(parents=True)
        project.patches_path.mkdir()
        project.metadata_path.write_text(json.dumps({'id': name, 'name': name}))
        (project.files_path / 'asset.txt').write_text(name)
        if patches:
            project.executable_patch_path.write_text(json.dumps({'format_version': 1, 'patches': list(patches)}))
        return project

    def legacy_bind_patch(self):
        return {
            'id': 'anm_missing_joint_local_bind', 'type': 'aob_replace',
            'section': '.text', 'expected_matches': 1,
            'pattern': t3_anm_runtime.BIND_ORIGINAL.hex(' ').upper(),
            'replacement': t3_anm_runtime.BIND_FIXED.hex(' ').upper(),
        }

    def test_verified_legacy_migration_precedes_patch_renaming(self):
        # Real historical digest, not a mocked detector.
        legacy = self.legacy_bind_patch()
        self.assertTrue(t3_anm_runtime.is_legacy_patch(legacy))
        current = {'id': 'current', 'target': 'Ai.Dll', 'type': 'aob_replace',
                   'pattern': '11 22', 'replacement': '33 44'}
        source = self.source('original', [legacy, current])
        with mock.patch.object(self.manager, '_validate_pack_patches'):
            result = self.manager.create_mod_pack('Merged', [source])
        patches = self.manager._read_patch_manifest(result.project)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]['target'], 'Ai.Dll')
        self.assertNotEqual(patches[0]['id'], 'current')
        report = json.loads((result.project.folder / 'MERGE_REPORT.json').read_text())
        self.assertEqual(report['replaced_legacy_patches'], [{
            'source_mod': 'original', 'source_patch': legacy['id'], 'target': 'T3.exe'}])
        self.assertEqual(report['patch_sources'][0]['source_patch'], 'current')

    def test_modified_legacy_patch_fails_without_publishing_or_changing_selection(self):
        legacy = self.legacy_bind_patch()
        legacy['replacement'] = '90' * len(t3_anm_runtime.BIND_FIXED)
        source = self.source('original', [legacy])
        self.manager._save_state([source])
        before = self.manager.load_order_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Modified legacy ANM patch'):
            self.manager.create_mod_pack('Rejected', [source])
        self.assertFalse((self.manager.mods_folder / 'rejected').exists())
        self.assertTrue(source.enabled)
        self.assertEqual(self.manager.load_order_path.read_bytes(), before)

    def test_pack_retains_resolved_variant_configuration_and_validates_automatic_patches(self):
        source = self.source('animation_source')
        plan = CompatibilityPlan(variants=[('ca/base.anm', 'ca/alternative.anm')], navigation=True)
        plan.report['variant_configuration_inputs'] = [{'file': 'source/anm_variants.json', 'sha256': 'fixture'}]
        # Source analysis already resolves priority and validates the profile;
        # the pack must retain exactly that result even without explicit patches.
        def validate(pack, destination):
            config = json.loads((pack.folder / 'anm_variants.json').read_text())
            self.assertEqual(config, {'format_version': 1, 'library': 'ca/casts/t900s/tps/anim.lib',
                                     'pairs': [{'base': 'ca/base.anm', 'alternative': 'ca/alternative.anm'}]})
            self.assertFalse(pack.executable_patch_path.exists())
        with mock.patch.object(modding, 'analyze_anm_compatibility', return_value=plan) as analyze:
            with mock.patch.object(self.manager, '_validate_pack_patches', side_effect=validate) as validation:
                result = self.manager.create_mod_pack('Variants', [source])
        analyze.assert_called_once_with(self.game, [source])
        validation.assert_called_once()
        report = json.loads((result.project.folder / 'MERGE_REPORT.json').read_text())
        self.assertEqual(report['animation_variant_pairs'], 1)
        self.assertEqual(report['animation_variant_sources'], plan.report['variant_configuration_inputs'])

    def test_pack_priority_disabled_sources_and_snapshot_semantics(self):
        first = self.source('top')
        second = self.source('bottom')
        disabled = self.source('disabled', enabled=False)
        (disabled.files_path / 'excluded.txt').write_text('excluded')
        result = self.manager.create_mod_pack('Merged', [first, second, disabled])
        self.assertEqual((result.project.files_path / 'asset.txt').read_text(), 'top')
        self.assertFalse((result.project.files_path / 'excluded.txt').exists())
        self.assertEqual(result.sources, ['top', 'bottom'])
        self.assertFalse(first.enabled)
        self.assertFalse(second.enabled)
        self.assertTrue(first.folder.exists())
        self.assertTrue(result.project.enabled)

    def test_validation_failure_preserves_selection_and_installed_outputs(self):
        source = self.source('source', [{'id': 'invalid', 'type': 'aob_replace',
                                         'pattern': '11 22', 'replacement': '33 44'}])
        self.manager._save_state([source])
        self.manager.compiled_pack_path.write_bytes(b'old archive')
        (self.game / 'T3_Modded.exe').write_bytes(b'old exe')
        paths = [self.manager.load_order_path, self.manager.compiled_pack_path, self.game / 'T3_Modded.exe']
        before = {p: p.read_bytes() for p in paths}
        with mock.patch.object(self.manager, '_validate_pack_patches', side_effect=ValueError('conflict')):
            with self.assertRaisesRegex(ValueError, 'conflict'):
                self.manager.create_mod_pack('Rejected', [source])
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertTrue(source.enabled)
        self.assertFalse((self.manager.mods_folder / 'rejected').exists())
        self.assertFalse(list(self.manager.data_folder.glob('.modpack-*')))

    def test_malformed_anm_cannot_be_hidden_by_pack_creation(self):
        source = self.source('source')
        (source.files_path / 'invalid.anm').write_bytes(b'not an animation')
        with self.assertRaisesRegex(ValueError, 'ANM compatibility analysis failed'):
            self.manager.create_mod_pack('Rejected', [source])
        self.assertFalse((self.manager.mods_folder / 'rejected').exists())


if __name__ == '__main__':
    unittest.main()
