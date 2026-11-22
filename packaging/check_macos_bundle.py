"""Fail packaging if a macOS app still links to the build machine's Nix store."""
from pathlib import Path
import subprocess
import sys

bundle = Path(sys.argv[1])
magic_numbers = {bytes.fromhex(value) for value in
                 ('feedface', 'feedfacf', 'cefaedfe', 'cffaedfe', 'cafebabe', 'bebafeca')}
checked = 0
for path in bundle.rglob('*'):
    if path.is_symlink() or not path.is_file():
        continue
    with path.open('rb') as source:
        if source.read(4) not in magic_numbers:
            continue
    checked += 1
    links = subprocess.check_output(['otool', '-L', str(path)], text=True)
    if any(line.strip().startswith('/nix/store/') for line in links.splitlines()[1:]):
        raise SystemExit(f'Nonportable Nix dependency in {path}:\n{links}')
    commands = subprocess.check_output(['otool', '-l', str(path)], text=True)
    if any(line.strip().startswith('path /nix/store/') for line in commands.splitlines()):
        raise SystemExit(f'Nonportable Nix RPATH in {path}')
if not checked:
    raise SystemExit('No Mach-O binaries found in the app')
print(f'Checked {checked} Mach-O files: no Nix store load paths or RPATHs')
