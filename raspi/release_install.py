"""Standalone user install/update/rollback. Never read or modify user credentials."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import uuid

MANIFEST = 'release-manifest.json'
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?'
PRIVATE = {'secrets.json', 'settings.json', 'voice-settings.json', 'voice-reviews.json',
           'gemini-key.enc', 'key-encryption.key', 'pairing.json'}


class ReleaseError(ValueError):
    def __init__(self): super().__init__('RELEASE_OPERATION_FAILED')


def _no_links(path):
    for parent in (path, *path.parents):
        if parent.is_symlink(): raise ReleaseError()


def verify(root):
    root = Path(root).absolute(); _no_links(root)
    try:
        path = root/MANIFEST
        if path.stat().st_size > 4_000_000: raise ReleaseError()
        manifest = json.loads(path.read_bytes())
        if (set(manifest) != {'schema', 'version', 'platform', 'files'} or manifest['schema'] != 1
                or manifest['platform'] != 'linux-arm64' or not re.fullmatch(VERSION, manifest['version'])
                or not isinstance(manifest['files'], dict) or not 1 <= len(manifest['files']) <= 20000): raise ReleaseError()
        actual = set()
        for path in root.rglob('*'):
            if path.is_symlink() or not (path.is_file() or path.is_dir()): raise ReleaseError()
            if path.is_file(): actual.add(path.relative_to(root).as_posix())
        if actual != set(manifest['files']) | {MANIFEST}: raise ReleaseError()
        total = 0
        for name, record in manifest['files'].items():
            relative = PurePosixPath(name)
            if (not name or relative.is_absolute() or '..' in relative.parts or str(relative) != name
                    or '\\' in name or relative.name in PRIVATE or relative.name.startswith('.env')
                    or set(record) != {'sha256', 'size', 'mode'}
                    or not re.fullmatch('[a-f0-9]{64}', record['sha256'])
                    or type(record['size']) is not int or not 0 <= record['size'] <= 512_000_000
                    or record['mode'] not in (0o644, 0o755)): raise ReleaseError()
            path = root/name; info = path.stat(); total += info.st_size
            if total > 1_000_000_000 or info.st_size != record['size'] or stat.S_IMODE(info.st_mode) != record['mode']:
                raise ReleaseError()
            with path.open('rb') as source: digest = hashlib.file_digest(source, 'sha256').hexdigest()
            if digest != record['sha256']: raise ReleaseError()
        return manifest
    except ReleaseError: raise
    except Exception: raise ReleaseError() from None


@contextmanager
def _locked(prefix):
    _no_links(prefix)
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = prefix.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077: raise ReleaseError()
    handle = os.open(prefix/'.install.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077: raise ReleaseError()
        fcntl.flock(handle, fcntl.LOCK_EX)
        releases = prefix/'releases'; _no_links(releases); releases.mkdir(exist_ok=True, mode=0o700)
        yield
    finally: os.close(handle)


def _target(prefix, name):
    path = prefix/name
    if not os.path.lexists(path): return None
    if not path.is_symlink(): raise ReleaseError()
    target = os.readlink(path)
    parts = PurePosixPath(target).parts
    if len(parts) != 2 or parts[0] != 'releases' or not re.fullmatch(VERSION, parts[1]): raise ReleaseError()
    resolved = prefix/target; _no_links(resolved); verify(resolved)
    return target


def _link(prefix, name, target):
    temporary = prefix/('.link-'+uuid.uuid4().hex)
    try:
        temporary.symlink_to(target); os.replace(temporary, prefix/name)
        fd = os.open(prefix, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally: temporary.unlink(missing_ok=True)


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def install(bundle, prefix):
    bundle = Path(bundle).absolute(); prefix = Path(prefix).absolute()
    manifest = verify(bundle)
    with _locked(prefix):
        prior = _target(prefix, 'current')
        target = prefix/'releases'/manifest['version']
        stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=prefix))
        try:
            for name, record in manifest['files'].items():
                output = stage/name; output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(bundle/name, output); output.chmod(record['mode'])
                with output.open('rb') as source: os.fsync(source.fileno())
            shutil.copyfile(bundle/MANIFEST, stage/MANIFEST)
            with (stage/MANIFEST).open('rb') as source: os.fsync(source.fileno())
            verify(stage)
            if target.exists():
                if verify(target) != manifest: raise ReleaseError()
            else:
                for directory in sorted((p for p in stage.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                    _sync_directory(directory)
                _sync_directory(stage); os.replace(stage, target); _sync_directory(prefix/'releases')
            if prior and prior != 'releases/'+manifest['version']: _link(prefix, 'previous', prior)
            _link(prefix, 'current', 'releases/'+manifest['version'])
        finally:
            if stage.exists(): shutil.rmtree(stage)
    return target


def rollback(prefix):
    prefix = Path(prefix).absolute()
    with _locked(prefix):
        current = _target(prefix, 'current'); previous = _target(prefix, 'previous')
        if not current or not previous or current == previous: raise ReleaseError()
        _link(prefix, 'current', previous); _link(prefix, 'previous', current)


def shortcuts(prefix, applications, bin_directory, desktop=None):
    prefix = Path(prefix).absolute()
    _target(prefix, 'current')
    executable = prefix/'current/bin/stackchan-raspi'
    text = str(executable)
    if any(ord(c) < 32 for c in text) or '=' in text: raise ReleaseError()
    escaped = ''.join('\\'+c if c in '\\"`$' else c for c in text).replace('\\', '\\\\').replace('%', '%%')
    entry = ('[Desktop Entry]\nType=Application\nName=Stackchan Raspberry Pi Host\n'
        'Name[ja]=スタックちゃん ホスト\nComment=Start the host manually; no automatic API startup\n'
        f'Exec="{escaped}"\nIcon=audio-headphones\nTerminal=false\nCategories=AudioVideo;\nX-Stackchan-Managed=true\n')
    for folder in (Path(applications), *([Path(desktop)] if desktop is not None else [])):
        _no_links(folder); folder.mkdir(parents=True, exist_ok=True, mode=0o755)
        info = folder.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o022: raise ReleaseError()
        target = folder/'stackchan-raspi.desktop'
        if os.path.lexists(target):
            if target.is_symlink() or not target.is_file() or 'X-Stackchan-Managed=true' not in target.read_text(): raise ReleaseError()
        temporary = folder/('.shortcut-'+uuid.uuid4().hex)
        try:
            temporary.write_text(entry); temporary.chmod(0o755 if desktop is not None and folder == Path(desktop) else 0o644)
            os.replace(temporary, target)
        finally: temporary.unlink(missing_ok=True)
    folder = Path(bin_directory); _no_links(folder); folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    info = folder.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022: raise ReleaseError()
    target = folder/'stackchan-raspi'
    if os.path.lexists(target) and (not target.is_symlink() or os.readlink(target) != str(executable)): raise ReleaseError()
    temporary = folder/('.launcher-'+uuid.uuid4().hex)
    try: temporary.symlink_to(executable); os.replace(temporary, target)
    finally: temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Stackchan Pi user install/update/rollback')
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--prefix', type=Path, default=Path.home()/'.local/share/stackchan-raspi-app')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--shortcuts', action='store_true')
    parser.add_argument('--desktop', type=Path)
    args = parser.parse_args()
    try:
        if args.rollback: rollback(args.prefix)
        else: install(args.bundle, args.prefix)
        if args.shortcuts:
            shortcuts(args.prefix, Path.home()/'.local/share/applications', Path.home()/'.local/bin', args.desktop)
        print('RELEASE_READY'); return 0
    except Exception:
        print('RELEASE_OPERATION_FAILED'); return 1


if __name__ == '__main__': raise SystemExit(main())
