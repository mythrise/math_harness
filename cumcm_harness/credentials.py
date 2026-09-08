"""Local-only Exa credential storage; never part of a workspace or release."""
import os
import stat
import tempfile
from .common import ROOT, Blocked

EXA_KEY_FILE = ROOT / '.runtime' / 'credentials' / 'exa-api-key'


def _validate(key):
    if not isinstance(key, str) or not 8 <= len(key) <= 1024 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise Blocked('Invalid Exa credential format; value omitted')
    return key


def get_exa_api_key():
    """An explicit environment value takes precedence over the local file."""
    if os.environ.get('EXA_API_KEY'):
        return _validate(os.environ['EXA_API_KEY'])
    path = EXA_KEY_FILE
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return ''
    except OSError:
        raise Blocked('Cannot securely read local Exa credential') from None
    with os.fdopen(fd, 'r', encoding='utf-8') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise Blocked('Local Exa credential must be owner-only (chmod 600)')
        try:
            return _validate(handle.read(1025).rstrip('\n'))
        except UnicodeError:
            raise Blocked('Invalid Exa credential encoding; value omitted') from None


def save_exa_api_key(key):
    key = _validate(key)
    path = EXA_KEY_FILE
    if path.is_symlink() or any(p.is_symlink() for p in (path.parent, path.parent.parent)):
        raise Blocked('Refusing a symlink credential location')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.exa-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(key + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
