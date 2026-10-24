"""Build a Linux ARM64 bundle from an explicit public-file allowlist."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from raspi.release_install import MANIFEST, ReleaseError, verify

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PYTHON = ('__init__.py', 'host.py', 'host_network.py', 'host_ui.py', 'key_store.py',
    'voice_ui.py', 'voice_settings.py', 'voice_preview.py', 'provision.py', 'provision_network.py',
    'provision_ui.py', 'launcher.py', 'diagnostics.py')
SECRET = re.compile(rb'AIza[0-9A-Za-z_-]{35}|gh[pousr]_[0-9A-Za-z]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')


def _copy(source, target, *, executable=False):
    if source.is_symlink() or not source.is_file(): raise ReleaseError()
    if source.stat().st_size < 10_000_000 and SECRET.search(source.read_bytes()): raise ReleaseError()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target); target.chmod(0o755 if executable else 0o644)


def build(output, *, allow_dirty=False):
    profile = json.loads((ROOT/'raspi/release-profile.json').read_text())
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    if dirty and not allow_dirty: raise ReleaseError()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    node_root = ROOT/f'.runtime/node-v{profile["node"]}-linux-arm64'
    node = node_root/'bin/node'
    with node.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != profile['node_binary_sha256']: raise ReleaseError()
    output = Path(output).absolute(); output.mkdir(parents=True, exist_ok=True)
    name = f'StackchanHost-{profile["version"]}-linux-arm64'
    archive = output/(name+'.tar.gz')
    if archive.exists(): raise ReleaseError()
    with tempfile.TemporaryDirectory(prefix='stackchan-build-') as directory:
        stage = Path(directory)/name; stage.mkdir()
        for filename in RUNTIME_PYTHON: _copy(ROOT/'raspi'/filename, stage/'raspi'/filename)
        for filename in ('LICENSE',): _copy(ROOT/filename, stage/filename)
        _copy(ROOT/'desktop/voices.py', stage/'desktop/voices.py')
        _copy(ROOT/'raspi/release-profile.json', stage/'raspi/release-profile.json')
        _copy(ROOT/'raspi/release_install.py', stage/'install.py')
        _copy(ROOT/'raspi/README.md', stage/'raspi/README.md')
        _copy(ROOT/'TODO.md', stage/'TODO.md')
        documentation = subprocess.check_output(['git', 'ls-files', 'docs'], cwd=ROOT, text=True).splitlines()
        for filename in (*documentation, 'docs/INSTALL_RASPI.md', 'docs/RELEASE_NOTES_RASPI.md'):
            _copy(ROOT/filename, stage/filename)
        readme = stage/'README.md'
        readme.write_text('# Stackchan Raspberry Pi Host\n\nInstall/update/rollback: [docs/INSTALL_RASPI.md](docs/INSTALL_RASPI.md).\n\nUsage: [raspi/README.md](raspi/README.md).\n')
        readme.chmod(0o644)
        for filename in ('package.json', 'package-lock.json', 'voice-catalog.json'):
            _copy(ROOT/'server'/filename, stage/'server'/filename)
        compiled = tuple((ROOT/'server/dist').glob('*.js'))
        if not compiled: raise ReleaseError()
        for source in compiled: _copy(source, stage/'server/dist'/source.name)
        packages = json.loads((ROOT/'server/package-lock.json').read_text())['packages']
        for package, record in packages.items():
            if not package or record.get('dev', False): continue
            if not package.startswith('node_modules/') or '..' in Path(package).parts: raise ReleaseError()
            folder = ROOT/'server'/package
            installed = json.loads((folder/'package.json').read_text())
            if installed['version'] != record['version']: raise ReleaseError()
            for source in folder.rglob('*'):
                relative = source.relative_to(folder)
                if 'node_modules' in relative.parts: continue
                if source.is_file(): _copy(source, stage/'server'/package/relative)
        _copy(node, stage/'runtime/node/bin/node', executable=True)
        _copy(node_root/'LICENSE', stage/'runtime/node/LICENSE')
        launcher = stage/'bin/stackchan-raspi'; launcher.parent.mkdir()
        launcher.write_text('#!/bin/sh\nset -eu\napp_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\nexec /usr/bin/python3 -I -B "$app_root/raspi/launcher.py" "$@"\n')
        launcher.chmod(0o755)
        metadata = stage/'build-source.json'
        metadata.write_text(json.dumps({'base_commit': commit, 'dirty': dirty}, sort_keys=True)+'\n'); metadata.chmod(0o644)
        for directory in (stage, *(p for p in stage.rglob('*') if p.is_dir())): directory.chmod(0o755)
        records = {}
        for source in sorted(stage.rglob('*')):
            if source.is_file():
                with source.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                records[source.relative_to(stage).as_posix()] = {'sha256': digest,
                    'size': source.stat().st_size, 'mode': source.stat().st_mode & 0o777}
        (stage/MANIFEST).write_text(json.dumps({'schema': 1, 'version': profile['version'],
            'platform': profile['platform'], 'files': records}, sort_keys=True, indent=2)+'\n')
        (stage/MANIFEST).chmod(0o644)
        verify(stage)
        temporary = archive.with_suffix('.partial')
        try:
            with temporary.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w') as tar:
                    for source in (stage, *sorted(stage.rglob('*'))):
                        info = tar.gettarinfo(str(source), arcname=str(source.relative_to(stage.parent)))
                        info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = 0
                        if source.is_file():
                            with source.open('rb') as stream: tar.addfile(info, stream)
                        else: tar.addfile(info)
            os.replace(temporary, archive)
        finally: temporary.unlink(missing_ok=True)
    with archive.open('rb') as source: digest = hashlib.file_digest(source, 'sha256').hexdigest()
    archive.with_suffix(archive.suffix+'.sha256').write_text(digest+'  '+archive.name+'\n')
    return archive


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, default=ROOT/'releases')
    parser.add_argument('--allow-dirty', action='store_true'); args = parser.parse_args()
    try: print(build(args.output, allow_dirty=args.allow_dirty).name); return 0
    except Exception: print('RELEASE_BUILD_FAILED'); return 1


if __name__ == '__main__': raise SystemExit(main())
