"""Verify an official Semgrep wheel and install only its native engine/libraries."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import platform
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def install(directory):
    data = json.loads((ROOT/'.semgrep/tool.json').read_text(encoding='utf-8'))
    version = data['version']
    machine = platform.machine().lower()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version) or machine not in ('amd64','x86_64'):
        raise ValueError('Unsupported Semgrep version/platform')
    artifact = data['artifacts'][platform.system()+'-x86_64']
    url = urlsplit(artifact['url'])
    if (url.scheme != 'https' or url.hostname != 'files.pythonhosted.org' or url.username is not None
            or url.query or url.fragment or not url.path.endswith('.whl')
            or not re.fullmatch(r'[a-f0-9]{64}',artifact['sha256'])
            or type(artifact['size']) is not int or not 0 < artifact['size'] <= 128*1024*1024
            or artifact['executable'] not in ('semgrep-core','semgrep-core.exe')):
        raise ValueError('Invalid pinned Semgrep artifact')
    with TemporaryDirectory(prefix='eos-semgrep-install-') as temporary:
        wheel = Path(temporary)/'semgrep.whl'
        digest = sha256()
        size = 0
        with build_opener(NoRedirect()).open(Request(artifact['url']), timeout=30) as response, wheel.open('wb') as output:
            while chunk := response.read(1024*1024):
                size += len(chunk)
                if size > artifact['size']:
                    raise ValueError('Semgrep download exceeds pinned size')
                digest.update(chunk)
                output.write(chunk)
        if size != artifact['size'] or digest.hexdigest() != artifact['sha256']:
            raise ValueError('Semgrep artifact checksum mismatch')
        destination = directory.resolve()/version
        with ZipFile(wheel) as archive:
            files = native_files(archive.infolist(), version, artifact['executable'])
            for relative, _ in files:
                target = destination/relative
                if target.is_symlink() or target.parent.is_symlink():
                    raise ValueError('Semgrep destination must not be a symlink')
            for relative, item in files:
                target = destination/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(item))
                target.chmod(0o755)
        return destination/artifact['executable']


def native_files(members, version, executable):
    """Select only the engine and its bundled libraries; keep the relative `libs/` layout."""
    base = PurePosixPath(f'semgrep-{version}.data/purelib/semgrep/bin')
    files = []
    for item in members:
        path = PurePosixPath(item.filename)
        if item.is_dir() or base not in path.parents:
            continue
        relative = path.relative_to(base)
        library = re.fullmatch(r'[A-Za-z0-9_+-]+\.dll|lib[A-Za-z0-9_+-]+(?:\.so(?:\.[0-9]+)*|(?:\.[0-9]+)*\.dylib)',
                               relative.name)
        if relative == PurePosixPath(executable) or (
                library and relative.parent in (PurePosixPath('.'), PurePosixPath('libs'))):
            files.append((relative, item))
    if (sum(relative == PurePosixPath(executable) for relative, _ in files) != 1
            or len({relative for relative, _ in files}) != len(files)
            or any(item.file_size > 512*1024*1024 for _, item in files)
            or sum(item.file_size for _, item in files) > 1024*1024*1024):
        raise ValueError('Invalid native Semgrep archive layout')
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('.semgrep-native'))
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args(argv)
    try:
        executable = install(args.directory)
        if args.github_output:
            with args.github_output.open('a',encoding='utf-8') as output:
                output.write('executable='+str(executable)+'\n')
        print('Semgrep native engine installed with verified artifact checksum')
        return 0
    except (OSError,ValueError,KeyError,TypeError,BadZipFile):
        print('Semgrep native engine installation failed; no unverified executable accepted')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
