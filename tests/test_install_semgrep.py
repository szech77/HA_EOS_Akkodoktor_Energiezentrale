"""The native Semgrep engine is only accepted from the pinned, checksum-verified wheel."""
from contextlib import redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from tools import install_semgrep
from tools.install_semgrep import main, native_files
from test_energy import temporary_project_directory

VERSION = '1.185.0'
BASE = f'semgrep-{VERSION}.data/purelib/semgrep/bin/'
LINUX = {BASE+'semgrep-core': b'engine', BASE+'libs/libz.so.1': b'z', BASE+'libs/libtree-sitter.so.0.26': b't',
         BASE+'libs/libstdc++.so.6': b's', BASE+'__init__.py': b'', 'semgrep/main.py': b'python'}
WINDOWS = {BASE+'semgrep-core.exe': b'engine', BASE+'libstdc++-6.dll': b's', BASE+'zlib1.dll': b'z',
           BASE+'__init__.py': b''}


def wheel(files):
    data = BytesIO()
    with ZipFile(data, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


def selected(files, executable):
    with ZipFile(BytesIO(wheel(files))) as archive:
        return sorted(str(path) for path, _ in native_files(archive.infolist(), VERSION, executable))


def test_only_engine_and_bundled_libraries_are_selected_with_their_relative_layout():
    assert selected(LINUX, 'semgrep-core') == ['libs/libstdc++.so.6', 'libs/libtree-sitter.so.0.26',
                                               'libs/libz.so.1', 'semgrep-core']
    assert selected(WINDOWS, 'semgrep-core.exe') == ['libstdc++-6.dll', 'semgrep-core.exe', 'zlib1.dll']


def test_missing_or_ambiguous_engines_are_rejected():
    with pytest.raises(ValueError):
        selected({BASE+'libs/libz.so.1': b'z'}, 'semgrep-core')
    data = BytesIO()
    with ZipFile(data, 'w') as archive, pytest.warns(UserWarning):
        archive.writestr(BASE+'semgrep-core.exe', b'first')
        archive.writestr(BASE+'semgrep-core.exe', b'second')
    with ZipFile(data) as archive, pytest.raises(ValueError):
        native_files(archive.infolist(), VERSION, 'semgrep-core.exe')
    # Nested copies and directory entries are not the engine and are never extracted.
    assert selected({**WINDOWS, BASE+'nested/semgrep-core.exe': b'x', BASE+'semgrep-core.exe/': b''},
                    'semgrep-core.exe') == ['libstdc++-6.dll', 'semgrep-core.exe', 'zlib1.dll']


def test_traversal_and_unexpected_files_are_never_extracted():
    files = {**WINDOWS, BASE+'../../evil.dll': b'x', BASE+'libs/../../evil.dll': b'x',
             BASE+'other/lib.dll': b'x', BASE+'tool.exe': b'x', BASE+'libs/script.sh': b'x'}
    assert selected(files, 'semgrep-core.exe') == ['libstdc++-6.dll', 'semgrep-core.exe', 'zlib1.dll']


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def run_install(root, payload, artifact_changes=None, system='Windows', machine='x86_64', host=None):
    artifact = {'url':'https://files.pythonhosted.org/packages/semgrep.whl', 'sha256':sha256(payload).hexdigest(),
                'size':len(payload), 'executable':'semgrep-core.exe' if system == 'Windows' else 'semgrep-core',
                **(artifact_changes or {})}
    (root/'.semgrep').mkdir(exist_ok=True)
    (root/'.semgrep/tool.json').write_text(json.dumps({'version':VERSION,
        'artifacts':{system+'-x86_64':artifact}}), encoding='utf-8')
    opened = []

    class Opener:
        def open(self, request, timeout):
            opened.append(request.full_url)
            return Response(payload)

    output = StringIO()
    with patch.object(install_semgrep, 'ROOT', root), patch.object(install_semgrep, 'build_opener',
            return_value=Opener()), patch('platform.system', return_value=host or system), \
            patch('platform.machine', return_value=machine), redirect_stdout(output):
        code = main(['--directory', str(root/'native'), '--github-output', str(root/'github-output')])
    return code, opened, output.getvalue()


@pytest.mark.parametrize('system,files', [('Windows', WINDOWS), ('Linux', LINUX)])
def test_verified_wheel_installs_engine_and_reports_its_path(system, files):
    with temporary_project_directory() as root:
        code, opened, _ = run_install(root, wheel(files), system=system)
        executable = 'semgrep-core.exe' if system == 'Windows' else 'semgrep-core'
        assert code == 0 and len(opened) == 1
        assert (root/'native'/VERSION/executable).read_bytes() == b'engine'
        assert not (root/'native'/VERSION/'__init__.py').exists()
        assert (root/'github-output').read_text(encoding='utf-8') == (
            'executable=' + str((root/'native'/VERSION/executable).resolve()) + '\n')


@pytest.mark.parametrize('changes', [
    {'sha256':'0'*64}, {'size':1}, {'size':10**9},
    {'url':'http://files.pythonhosted.org/packages/semgrep.whl'},
    {'url':'https://example.com/packages/semgrep.whl'},
    {'url':'https://user@files.pythonhosted.org/packages/semgrep.whl'},
    {'url':'https://files.pythonhosted.org/packages/semgrep.whl?x=1'},
    {'executable':'../semgrep-core.exe'},
])
def test_unverified_or_unexpected_artifacts_are_not_installed(changes):
    with temporary_project_directory() as root:
        payload = wheel(WINDOWS)
        if changes.get('size') == 1:
            changes = {**changes, 'sha256':sha256(payload[:1]).hexdigest()}
        code, _, output = run_install(root, payload, changes)
        assert code == 1
        assert not (root/'native').exists() and not (root/'github-output').exists()
        assert 'no unverified executable accepted' in output


def test_corrupt_wheel_and_unsupported_platform_fail_closed():
    with temporary_project_directory() as root:
        assert run_install(root, b'not a zip')[0] == 1
        assert run_install(root, wheel(WINDOWS), host='Darwin')[0] == 1
        assert run_install(root, wheel(WINDOWS), machine='aarch64')[0] == 1
        assert not (root/'native').exists()
