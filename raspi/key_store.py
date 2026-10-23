"""Pi-only authenticated encryption at rest; no plaintext files or secret diagnostics.

The local wrapping key is private to the OS user, not a hardware security boundary.
An attacker running as that user or root can decrypt the stored API key.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat
import uuid

MAGIC = b'STACKCHAN-API-KEY-v1\0'
MAX_FILE = 1024


class KeyStoreError(ValueError):
    def __init__(self):
        super().__init__('KEY_STORE_UNAVAILABLE')


def _base(variable, fallback):
    path = Path(os.environ.get(variable, ''))
    return path if path.is_absolute() else Path.home()/fallback


@contextmanager
def _directory(path, create=False):
    """Walk without following directory symlinks, then pin the private directory."""
    path = Path(path).absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in ('.', '..'): raise KeyStoreError()
            if create:
                try: os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError: pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077: raise KeyStoreError()
        yield fd
    finally: os.close(fd)


def _read(fd, name):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(handle, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1): raise KeyStoreError()
        raw = source.read(MAX_FILE+1)
        if len(raw) > MAX_FILE: raise KeyStoreError()
        return raw


def _atomic(fd, name, raw):
    # Refuse unsafe destinations before replacement. All accesses use pinned dirfds.
    try: _read(fd, name)
    except FileNotFoundError: pass
    temp = '.key-write-'+uuid.uuid4().hex
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, 'wb') as target:
            target.write(raw); target.flush(); os.fsync(target.fileno())
        os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd); os.fsync(fd)
    finally:
        try: os.unlink(temp, dir_fd=fd)
        except FileNotFoundError: pass


class KeyStore:
    def __init__(self, config=None, data=None):
        self.config = Path(config) if config is not None else _base('XDG_CONFIG_HOME', '.config')/'stackchan-raspi'
        self.data = Path(data) if data is not None else _base('XDG_DATA_HOME', '.local/share')/'stackchan-raspi'

    @contextmanager
    def _locked(self, create=False):
        with _directory(self.config, create) as config:
            handle = os.open('.api-key.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                             0o600, dir_fd=config)
            try:
                info = os.fstat(handle)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1): raise KeyStoreError()
                fcntl.flock(handle, fcntl.LOCK_EX)
                yield config
            finally: os.close(handle)

    def _decrypt(self, raw, master):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if len(master) != 32 or not raw.startswith(MAGIC): raise KeyStoreError()
        offset = len(MAGIC)
        key = AESGCM(master).decrypt(raw[offset:offset+12], raw[offset+12:], MAGIC).decode('ascii')
        self._validate(key)
        return key

    @staticmethod
    def _validate(key):
        if not isinstance(key, str) or not re.fullmatch(r'[\x21-\x7e]{20,256}', key): raise KeyStoreError()

    def load(self):
        try:
            with self._locked() as config:
                try: raw = _read(config, 'gemini-key.enc')
                except FileNotFoundError: return ''
                with _directory(self.data) as data:
                    return self._decrypt(raw, _read(data, 'key-encryption.key'))
        except FileNotFoundError:
            # Only a missing config directory means no saved setting. Missing master
            # for an existing ciphertext must fail closed.
            if not os.path.lexists(self.config): return ''
            raise KeyStoreError() from None
        except Exception: raise KeyStoreError() from None

    def save(self, key):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._validate(key)
            with self._locked(create=True) as config:
                try: previous = _read(config, 'gemini-key.enc')
                except FileNotFoundError: previous = None
                with _directory(self.data, create=True) as data:
                    try: master = _read(data, 'key-encryption.key')
                    except FileNotFoundError:
                        if previous is not None: raise KeyStoreError()
                        master = AESGCM.generate_key(bit_length=256)
                        _atomic(data, 'key-encryption.key', master)
                    if len(master) != 32: raise KeyStoreError()
                    if previous is not None:
                        if self._decrypt(previous, master) == key: return
                    nonce = os.urandom(12)
                    _atomic(config, 'gemini-key.enc', MAGIC+nonce+AESGCM(master).encrypt(nonce, key.encode('ascii'), MAGIC))
        except Exception: raise KeyStoreError() from None

    def delete(self):
        try:
            with self._locked() as config:
                try: _read(config, 'gemini-key.enc')
                except FileNotFoundError: return
                os.unlink('gemini-key.enc', dir_fd=config); os.fsync(config)
                # Keep the private wrapping key: deleting the ciphertext removes
                # the saved setting without a two-file transaction or backup.
        except FileNotFoundError:
            if os.path.lexists(self.config): raise KeyStoreError() from None
        except Exception: raise KeyStoreError() from None
