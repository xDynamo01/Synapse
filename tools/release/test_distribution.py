"""Deterministic distribution guard tests; fixtures are never runtime acceptance."""
from contextlib import closing, redirect_stdout
import io
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import diagnose
import zipfile

import package


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synapse-distribution-guards-")
        self.root = Path(self.temporary.name)
        self.python = Path(__import__('sys').executable)
        self.installer = package.ROOT / 'tools/release/install-windows.ps1'
        self.install_root = self.root / 'installed'
        self.state = self.root / 'state'
        self.state.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, name, legacy=False, mutate=None):
        checksums = {}
        programs = ('synapse-backend','synapse-desktop','synapse-image-decoder','synapse-page-analyzer') if legacy else package.PROGRAMS
        payloads = {program+'.exe': program.encode() for program in programs}
        payloads['python/synapse_ai/__init__.py'] = b''
        payloads['start-windows.ps1'] = b'# fixture only'
        if not legacy:
            payloads.update({key:b'fixture' for key in ('check-runtime/runtime-manifest.json','check-runtime/runtime/python.exe','runtime/python.exe','runtime/python314.dll','runtime/Lib/socket.py','runtime/DLLs/_socket.pyd','runtime/DLLs/_ssl.pyd','runtime/DLLs/_sqlite3.pyd','distribution-common.ps1','diagnose.py','install-windows.ps1')})
        if not legacy:
            checker_files={'python.exe':b'fixture','python314.dll':b'fixture','DLLs/_sqlite3.pyd':b'fixture'}
            for key,data in checker_files.items():
                payloads['check-runtime/runtime/'+key]=data
            payloads['check-runtime/runtime-manifest.json']=json.dumps({'cpython':'323c59a5e348347be2ce2b7ea55fcb30bf68b2d3','dependencies':{'zlib-ng-2.2.4':'a502e047655c31db29601def76ad6539acacf43d','sqlite-3.50.4.0':'ef547e549b49a2822214ef7880c0ca212b32929e'},'files':{key:package.digest(data) for key,data in checker_files.items()}}).encode()
        manifest = {'version':name,'platform':'windows','architecture':'x64','sha256':checksums}
        if not legacy:
            manifest.update(format=2,compatibility=package.CONTRACT,source_tree={'files':{},'sha256':package.digest(b'{}')})
        for key,data in payloads.items():
            checksums[key] = package.digest(data)
        if mutate:
            mutate(manifest,payloads)
        payloads['manifest.json'] = json.dumps(manifest).encode()
        archive = self.root / (name+'.zip')
        with zipfile.ZipFile(archive,'w') as output:
            for key,data in payloads.items():
                output.writestr(key,data)
        return archive

    def install(self, archive=None, success=True):
        command=['pwsh','-NoProfile','-File',str(self.installer),'-InstallRoot',str(self.install_root),'-StateRoot',str(self.state),'-Python',str(self.python)]
        if archive:
            command += ['-Package',str(archive),'-TrustedSha256',package.digest(archive.read_bytes())]
        else:
            command += ['-Rollback']
        reply=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if success:
            self.assertEqual(reply.returncode,0,reply.stderr)
        else:
            self.assertNotEqual(reply.returncode,0,reply.stdout)
        return reply

    def test_missing_provider_gpu_tools_are_explicit(self):
        with patch('diagnose.shutil.which', return_value=None), patch('diagnose.socket.create_connection', side_effect=OSError):
            result=diagnose.diagnose(self.root)
        self.assertEqual(result['gpu']['status'],'unavailable')
        self.assertIsNone(result['gpu']['vram_bytes'])
        self.assertEqual(result['local_provider']['status'],'unavailable')
        self.assertEqual(result['resource_admission'],'not_evaluated_no_workload')
        self.assertFalse(any(result['tools'].values()))
        self.assertFalse(any(result['programs'].values()))

    def test_optional_capabilities_report_setup_without_importing_ml_or_starting_browser(self):
        # Replace only the Python mapping; clearing/restoring Windows process
        # environment loses intentionally empty variables through os.putenv.
        with patch('diagnose.os.environ',{}), patch('diagnose.importlib.util.find_spec',return_value=None), patch('diagnose.subprocess.run') as launch:
            result=diagnose.optional_capabilities(self.root)
        self.assertEqual(result['voice']['status'],'external_setup_required')
        self.assertEqual(result['browser']['status'],'external_setup_required')
        self.assertEqual(result['browser']['chromium_executables'],[])
        self.assertEqual(result['automatic_install'],'disabled')
        launch.assert_not_called()

    def test_voice_runtime_configuration_matches_native_fixed_schema_and_overrides(self):
        python=self.root/'python.exe';python.write_bytes(b'synthetic')
        models=self.root/'models';models.mkdir()
        configuration=self.root/'voice-runtime.json'
        configuration.write_text(json.dumps({'python':str(python),'models':str(models)}))
        with patch('diagnose.os.environ',{}):
            selected=diagnose.voice_configuration(self.root)
        self.assertEqual(selected,(str(python),str(models),'voice-runtime.json'))
        other=self.root/'other';other.mkdir();override=other/'python.exe';override.write_bytes(b'synthetic')
        with patch('diagnose.os.environ',{'SYNAPSE_VOICE_PYTHON':str(override)}):
            self.assertEqual(diagnose.voice_configuration(self.root)[0],str(override))
        for invalid in ('{bad',json.dumps({'python':str(python),'models':str(models),'command':'run'}),json.dumps({'python':'relative.exe','models':str(models)})):
            configuration.write_text(invalid)
            with patch('diagnose.os.environ',{}),self.assertRaises((ValueError,OSError)):
                diagnose.voice_configuration(self.root)
        configuration.unlink()
        with patch('diagnose.os.environ',{'SYNAPSE_VOICE_PYTHON':str(python)}):
            self.assertEqual(diagnose.voice_configuration(self.root),(str(python),None,'environment'))

    def test_zip_bytes_reproduce_for_identical_inputs(self):
        archive=self.archive('fixture')
        sources=[]
        with zipfile.ZipFile(archive) as fixture:
            for name in fixture.namelist():
                if name=='manifest.json':
                    continue
                path=self.root/'inputs'/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(fixture.read(name))
                sources.append((name,path))
        with patch('package.files', return_value=sources), patch('package.source_fingerprint', return_value={'files':{},'sha256':package.digest(b'{}')}), redirect_stdout(io.StringIO()):
            first=package.build(self.root,self.root/'one','0.3.1')
            second=package.build(self.root,self.root/'two','0.3.1')
        self.assertEqual(first.read_bytes(),second.read_bytes())

    def test_full_worker_runtime_prunes_unrelated_developer_packages(self):
        runtime=self.root/'python'
        for name in ('python.exe','python314.dll','Lib/socket.py','Lib/Site-Packages/private.py','Lib/test/test_private.py','Lib/SITEcustomize.py','Lib/private.PTH','Scripts/private.py','DLLs/_socket.pyd'):
            path=runtime/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'fixture')
        with patch('package.subprocess.run',return_value=subprocess.CompletedProcess([],0)):
            selected=dict(package.runtime_files(runtime))
        self.assertEqual(set(selected),{'runtime/python.exe','runtime/python314.dll','runtime/Lib/socket.py','runtime/DLLs/_socket.pyd'})

    def test_complete_contract_and_trusted_digest(self):
        archive=self.archive('current')
        self.assertEqual(package.verify(archive,package.digest(archive.read_bytes()))['format'],2)
        with self.assertRaisesRegex(ValueError,'trusted digest'):
            package.verify(archive,'0'*64)

    def test_missing_tampered_incompatible_and_unsafe_entries(self):
        mutations=[
            lambda m,p: (p.pop('synapse-desktop-slint.exe'),m['sha256'].pop('synapse-desktop-slint.exe')),
            lambda m,p: (p.pop('check-runtime/runtime/python314.dll'),m['sha256'].pop('check-runtime/runtime/python314.dll')),
            lambda m,p: p.update({'start-windows.ps1':b'tampered'}),
            lambda m,p: m['compatibility'].update({'storage_max':999}),
            lambda m,p: (p.update({'../escape':b'x'}),m['sha256'].update({'../escape':package.digest(b'x')})),
        ]
        for index,mutation in enumerate(mutations):
            # deepcopy contract prevents one fixture modifying process-wide expected contract.
            def apply(manifest,payloads):
                manifest['compatibility']=dict(package.CONTRACT)
                mutation(manifest,payloads)
            archive=self.archive('invalid'+str(index),mutate=apply)
            with self.assertRaises(ValueError):
                package.verify(archive)
            self.install(archive,success=False)
            self.assertFalse((self.install_root/'active.json').exists())

    def test_active_state_is_not_updated(self):
        archive=self.archive('locked')
        with (self.state/'.synapse-core.lock').open('a+b'):
            self.install(archive,success=False)
            self.assertFalse((self.install_root/'active.json').exists())
        self.install(archive)

    def test_schema_rollback_guard_preserves_pointer_and_data(self):
        old=self.archive('legacy',legacy=True)
        current=self.archive('current')
        self.install(old)
        self.install(current)
        pointer=(self.install_root/'active.json').read_bytes()
        with closing(sqlite3.connect(self.state/'core.sqlite3')) as db, db:
            db.execute('PRAGMA user_version=16')
            db.execute('CREATE TABLE marker(value)')
            db.execute("INSERT INTO marker VALUES('preserve')")
        rejected=self.install(success=False)
        self.assertIn('incompatible',rejected.stderr)
        self.assertEqual(pointer,(self.install_root/'active.json').read_bytes())
        with closing(sqlite3.connect(self.state/'core.sqlite3')) as db, db:
            self.assertEqual(db.execute('SELECT value FROM marker').fetchone(),('preserve',))
            db.execute('PRAGMA user_version=15')
        self.install()
        self.assertEqual(json.loads((self.install_root/'active.json').read_text())['current'],package.digest(old.read_bytes()))

    def test_installed_tamper_rejected_on_reinstall_and_rollback(self):
        old=self.archive('old')
        new=self.archive('new')
        self.install(old)
        self.install(new)
        old_dir=self.install_root/'versions'/package.digest(old.read_bytes())
        (old_dir/'synapse-backend.exe').write_bytes(b'tampered')
        self.install(success=False)
        self.install(old,success=False)


if __name__=='__main__':
    unittest.main()
