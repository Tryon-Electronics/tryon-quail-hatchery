"""Installer and tracker tests; HA/Pyscript runtime is simulated explicitly."""
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import re
import tempfile
import unittest
from types import SimpleNamespace

import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / 'custom_components/tryon_quail_hatchery'
PAYLOAD = COMP / 'payload'
spec = importlib.util.spec_from_file_location('installer', COMP / 'installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor('!input', lambda loader, node: {'input': loader.construct_scalar(node)})


class FakeState:
    def __init__(self):
        self.values, self.attrs = {}, {}
    def get(self, key):
        return self.values.get(key, 'unknown')
    def getattr(self, key):
        return self.attrs.get(key, {})
    def exist(self, key):
        return key in self.values
    def set(self, key, value=None, new_attributes=None, **kwargs):
        self.values[key] = str(value)
        if new_attributes is not None:
            self.attrs[key] = new_attributes
    def names(self, domain=None):
        return [key for key in self.values if not domain or key.startswith(domain + '.')]
    def delete(self, key):
        self.values.pop(key, None)
        self.attrs.pop(key, None)


class FakeService:
    def __init__(self, state):
        self.state = state
    def __call__(self, func):
        return func
    def call(self, domain, action, entity_id=None, **kwargs):
        if action == 'set_options':
            self.state.attrs.setdefault(entity_id, {})['options'] = kwargs['options']
        elif action == 'select_option':
            self.state.set(entity_id, kwargs['option'])
        elif action == 'set_value':
            self.state.set(entity_id, kwargs['value'])
        elif action in ('turn_on', 'turn_off'):
            self.state.set(entity_id, 'on' if action == 'turn_on' else 'off')


def tracker(data_dir):
    state = FakeState()
    def executor(func):
        async def wrapped(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapped
    context = {'state': state, 'service': FakeService(state),
               'pyscript_executor': executor, 'time_trigger': lambda *args: lambda fn: fn,
               'log': logging.getLogger('tracker-test')}
    code = (PAYLOAD / 'pyscript/incubator.py').read_text(encoding='utf-8')
    exec(compile(code, 'incubator.py', 'exec'), context)
    context['DATA_DIR'] = str(data_dir)
    context['DATA_FILE'] = str(data_dir / 'batches.json')
    context['BACKUP_FILE'] = str(data_dir / 'batches.backup.json')
    return context, state


class PackageTests(unittest.TestCase):
    def test_all_payload_checksums_and_formats(self):
        manifest = json.loads((PAYLOAD / 'bundle.json').read_text())
        for item in manifest['files']:
            path = PAYLOAD / item['source']
            self.assertEqual(installer.digest(path.read_bytes()), item['sha256'])
            if path.suffix == '.json':
                json.loads(path.read_text(encoding='utf-8'))
            elif path.suffix == '.yaml':
                yaml.load(path.read_text(encoding='utf-8'), Loader=Loader)
            elif path.suffix == '.py':
                compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        self.assertEqual(json.loads((PAYLOAD / 'incubator_data/batches.json').read_text()), [])

    def test_helper_and_service_coverage(self):
        helpers = yaml.safe_load((PAYLOAD / 'packages/incubator.yaml').read_text(encoding='utf-8'))
        defined = {domain + '.' + key for domain, values in helpers.items() for key in values}
        text = (PAYLOAD / 'pyscript/incubator.py').read_text(encoding='utf-8')
        dash = (PAYLOAD / 'dashboards/quail-hatchery.yaml').read_text(encoding='utf-8')
        used = set(re.findall(r'input_(?:text|number|select|boolean|datetime)\.[A-Za-z0-9_]+', text + dash))
        self.assertEqual(len(defined), 27)
        self.assertEqual(used - defined, set())
        exported = set(re.findall(r'@service\s+async def (\w+)', text))
        calls = set(re.findall(r'pyscript\.(incubator_[a-z_]+)', dash))
        self.assertEqual(calls - exported, set())

    def test_fresh_install_and_existing_data_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = installer.install_bundle(tmp, str(PAYLOAD))
            self.assertEqual(len(first['installed']), 9)
            data = Path(tmp) / 'incubator_data/batches.json'
            data.write_text('[{"id":99,"notes":"user record"}]')
            second = installer.install_bundle(tmp, str(PAYLOAD))
            self.assertIn('incubator_data/batches.json', second['preserved'])
            self.assertEqual(json.loads(data.read_text())[0]['id'], 99)
            self.assertFalse(second['conflicts'])

    def test_user_edits_are_preserved_and_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer.install_bundle(tmp, str(PAYLOAD))
            path = Path(tmp) / 'pyscript/incubator.py'
            path.write_text('# user modified script\n')
            result = installer.install_bundle(tmp, str(PAYLOAD))
            self.assertIn('pyscript/incubator.py', result['conflicts'])
            self.assertEqual(path.read_text(), '# user modified script\n')
            self.assertTrue(path.with_name('incubator.py.quail-update').exists())

    def test_untouched_managed_file_updates_with_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer.install_bundle(tmp, str(PAYLOAD))
            path = Path(tmp) / 'pyscript/incubator.py'
            old = b'# installed earlier version\n'
            path.write_bytes(old)
            state_path = Path(tmp) / installer.STATE_FILE
            state = json.loads(state_path.read_text())
            state['files']['pyscript/incubator.py'] = installer.digest(old)
            state_path.write_text(json.dumps(state))
            result = installer.install_bundle(tmp, str(PAYLOAD))
            self.assertIn('pyscript/incubator.py', result['updated'])
            self.assertEqual(path.with_name('incubator.py.quail-backup').read_bytes(), old)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                installer.safe_target(Path(tmp), '../outside')

    def test_legacy_survival_and_dates_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, _ = tracker(Path(tmp))
            batch = {'id': 1, 'eggs': 3, 'Survival': 3, 'start': '2026-7-11'}
            self.assertTrue(core['migrate_batch_schema'](batch))
            self.assertEqual(batch['hatched'], 3)
            self.assertEqual(batch['start'], '2026-07-11')

    def test_add_refresh_archive_delete_and_backup(self):
        async def run(tmp):
            core, state = tracker(Path(tmp))
            await core['add_batch'](name='Test batch', eggs=12, start='2026-01-01')
            await core['update_sensors']()
            self.assertEqual(state.get('sensor.incubator_active_batches'), '1')
            self.assertEqual(state.get('sensor.incubator_total_eggs'), '12')
            await core['incubator_archive_batch'](id=1)
            self.assertEqual(state.get('sensor.incubator_archived_batches'), '1')
            self.assertTrue(state.exist('sensor.incubator_archive_1'))
            await core['incubator_delete_batch'](id=1)
            self.assertEqual(json.loads(Path(core['DATA_FILE']).read_text()), [])
            self.assertTrue(Path(core['BACKUP_FILE']).exists())
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run(tmp))

    def test_invalid_json_keeps_existing_entities(self):
        async def run(tmp):
            core, state = tracker(Path(tmp))
            Path(core['DATA_FILE']).write_text('{broken')
            state.set('sensor.incubator_batch_9', '5')
            await core['update_sensors']()
            self.assertTrue(state.exist('sensor.incubator_batch_9'))
            self.assertEqual(state.get('sensor.incubator_data_status'), 'error')
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run(tmp))

    def test_duplicate_active_tag_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            core, _ = tracker(Path(tmp))
            batches = json.loads((PAYLOAD / 'examples/batches.example.json').read_text(encoding='utf-8'))
            batch, tag = core['active_tag_conflict'](batches, 'Blue', '001')
            self.assertIsNotNone(batch)
            self.assertEqual(tag['uid'], '1-1')
            self.assertEqual(core['active_tag_conflict'](batches, 'Blue', '001', exclude_uid='1-1'), (None, None))

    def test_invalid_batch_input_does_not_write(self):
        async def run(tmp):
            core, _ = tracker(Path(tmp))
            await core['ensure_file']()
            with self.assertRaises(ValueError):
                await core['add_batch'](name='Invalid', eggs=0, start='2026-01-01')
            self.assertEqual(json.loads(Path(core['DATA_FILE']).read_text()), [])
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run(tmp))

    def test_milestone_template_excludes_archives(self):
        bp = yaml.load((PAYLOAD / 'blueprints/automation/incubator/incubator_notifications.yaml').read_text(), Loader=Loader)
        variables = next(step['variables'] for step in bp['actions'] if 'variables' in step)
        env = Environment()
        env.tests['match'] = lambda value, pattern: re.match(pattern, value) is not None
        active = SimpleNamespace(entity_id='sensor.incubator_batch_1', state='7', attributes={
            'friendly_name':'Example hatch', 'days_to_candle':0, 'days_to_lockdown':7, 'days_to_hatch':11})
        archived = SimpleNamespace(entity_id='sensor.incubator_archive_2', state='Archived', attributes={
            'friendly_name':'Old batch', 'days_to_hatch':0})
        message = env.from_string(variables['milestone_message']).render(states=SimpleNamespace(sensor=[active,archived]))
        self.assertIn('candling day today', message)
        self.assertNotIn('Old batch', message)
        self.assertNotIn('lockdown starts today', message)
        empty = env.from_string(variables['milestone_message']).render(states=SimpleNamespace(sensor=[]))
        self.assertEqual(empty.strip(), '')


if __name__ == '__main__':
    unittest.main()
