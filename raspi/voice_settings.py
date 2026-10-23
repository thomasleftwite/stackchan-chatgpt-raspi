"""Private XDG voice preferences. Keys and audio are never accepted by this store."""
import copy
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid

from desktop.voices import REVIEW_REASONS, load_catalog

MAX_SETTINGS = 65536


def settings_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', ''))
    if not base.is_absolute(): base = Path.home()/'.config'
    return base/'stackchan-raspi/voice-settings.json'


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('SETTINGS_PERMISSIONS')
        raw = source.read(MAX_SETTINGS+1)
        if len(raw) > MAX_SETTINGS: raise ValueError('SETTINGS_TOO_LARGE')
        return raw


def _directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('SETTINGS_PERMISSIONS')


def _atomic(path, raw):
    fd, temp = tempfile.mkstemp(prefix='.voice-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(raw); target.flush(); os.fsync(target.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temp): os.unlink(temp)


class VoiceSettings:
    def __init__(self, path=None, *, catalog=None):
        self.path = Path(path) if path is not None else settings_path()
        self.catalog = catalog if catalog is not None else load_catalog()
        self.data = {'version': 1, 'records': {}, 'selected': {}}
        self.load_error = False
        try:
            if self.path.parent.exists(): _directory(self.path.parent)
            raw = _read(self.path)
            value = json.loads(raw)
            self.validate(value); self.data = value
        except FileNotFoundError: pass
        except (ValueError, OSError, UnicodeError, TypeError, RecursionError): self.load_error = True

    def validate(self, data):
        if (not isinstance(data, dict) or set(data) != {'version', 'records', 'selected'}
                or type(data['version']) is not int or data['version'] != 1
                or not isinstance(data['records'], dict) or not isinstance(data['selected'], dict)):
            raise ValueError('SETTINGS_INVALID')
        for name, record in data['records'].items():
            if (not isinstance(name, str) or not re.fullmatch(r'gemini-[a-z0-9.-]{1,100}:[A-Za-z]{1,32}', name)
                    or not isinstance(record, dict) or set(record) != {'status', 'reason', 'revision', 'heard'}
                    or record['status'] not in REVIEW_REASONS
                    or record['reason'] not in REVIEW_REASONS[record['status']]
                    or not isinstance(record['revision'], str) or len(record['revision']) > 100
                    or type(record['heard']) is not bool
                    or (record['status'] == 'approved' and not record['heard'])):
                raise ValueError('SETTINGS_INVALID')
        for model, voice in data['selected'].items():
            if (not isinstance(model, str) or not re.fullmatch(r'gemini-[a-z0-9.-]{1,100}', model)
                    or not isinstance(voice, str) or not re.fullmatch(r'[A-Za-z]{1,32}|', voice)):
                raise ValueError('SETTINGS_INVALID')

    def candidates(self, model):
        return tuple(self.catalog['voices']) if model in self.catalog['models'] else ()

    def approved(self, model):
        return tuple(voice for voice in self.candidates(model)
            if self.data['records'].get(model+':'+voice, {}).get('status') == 'approved'
            and self.data['records'][model+':'+voice].get('heard') is True
            and self.data['records'][model+':'+voice].get('revision') == self.catalog['revision'])

    def selected(self, model):
        voice = self.data['selected'].get(model, '')
        return voice if voice in self.approved(model) else ''

    def save(self, data, *, recover=False):
        self.validate(data)
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        if len(raw) > MAX_SETTINGS: raise ValueError('SETTINGS_TOO_LARGE')
        if self.load_error and not recover: raise ValueError('SETTINGS_RECOVERY_REQUIRED')
        _directory(self.path.parent)
        if self.path.is_symlink(): raise ValueError('SETTINGS_PERMISSIONS')
        # A new explicit review can replace corrupt data only after preserving it privately.
        if self.load_error and self.path.exists():
            _atomic(self.path.with_name(self.path.name+'.invalid-'+uuid.uuid4().hex), _read(self.path))
        _atomic(self.path, raw)
        self.data = data; self.load_error = False

    def select(self, model, voice):
        if voice and voice not in self.approved(model): raise ValueError('VOICE_NOT_APPROVED')
        data = copy.deepcopy(self.data); data['selected'][model] = voice
        self.save(data)

    def decide(self, model, voice, approved, reason, *, heard=False):
        status = 'approved' if approved else 'excluded'
        if voice not in self.candidates(model) or reason not in REVIEW_REASONS[status]:
            raise ValueError('VOICE_INVALID')
        if approved and not heard: raise ValueError('JAPANESE_REVIEW_REQUIRED')
        data = copy.deepcopy(self.data)
        data['records'][model+':'+voice] = {'status': status, 'reason': reason,
            'revision': self.catalog['revision'], 'heard': bool(heard)}
        if approved: data['selected'][model] = voice
        elif data['selected'].get(model) == voice: data['selected'][model] = ''
        self.save(data, recover=True)
