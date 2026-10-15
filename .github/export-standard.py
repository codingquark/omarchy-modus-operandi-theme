#!/usr/bin/env python3
"""Export a standard Omarchy theme to a new directory; never publish or install it."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True, type=Path, help='authoritative source Git checkout')
parser.add_argument('--ref', required=True, help='reviewed source commit or ref')
parser.add_argument('--variant', required=True, choices=['modus-operandi', 'modus-vivendi'])
parser.add_argument('--output', required=True, type=Path, help='new directory; must not exist')
parser.add_argument('--preview', required=True, type=Path, help='verified 960x540 standard-install PNG')
parser.add_argument('--screenshot', required=True, type=Path, help='verified 1200x675 desktop WebP, under100KB')
parser.add_argument('--omarchy-ref', required=True, help='40-character commit used for validation/capture')
args = parser.parse_args()

def git(*parts):
    return subprocess.check_output(['git', '-C', str(args.source), *parts])

def digest(data):
    return hashlib.sha256(data).hexdigest()

def dimensions(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return struct.unpack('>II', data[16:24])
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        pos = 12
        while pos + 8 <= len(data):
            kind = data[pos:pos+4]
            size = int.from_bytes(data[pos+4:pos+8], 'little')
            chunk = data[pos+8:pos+8+size]
            if kind == b'VP8X':
                return tuple(1 + int.from_bytes(chunk[n:n+3], 'little') for n in [4, 7])
            if kind == b'VP8 ' and chunk[3:6] == b'\x9d\x01\x2a':
                return tuple(n & 0x3fff for n in struct.unpack('<HH',chunk[6:10]))
            if kind == b'VP8L' and chunk[0] == 0x2f:
                bits = int.from_bytes(chunk[1:5], 'little')
                return (1 + (bits & 0x3fff), 1 + ((bits >> 14) & 0x3fff))
            pos += 8 + size + (size % 2)
    raise ValueError('Unrecognized image data')

if args.output.exists():
    parser.error('Output already exists; use a new staging directory to prevent stale files.')
if not re.fullmatch(r'[0-9a-f]{40}', args.omarchy_ref):
    parser.error('--omarchy-ref must be the full tested commit SHA')
source_commit = git('rev-parse', '--verify', args.ref + '^{commit}').decode().strip()
preview = args.preview.read_bytes()
screenshot = args.screenshot.read_bytes()
if not preview.startswith(b'\x89PNG\r\n\x1a\n') or dimensions(preview) != (960, 540):
    parser.error('Preview must be a verified 960x540 PNG')
if screenshot[:4] != b'RIFF' or dimensions(screenshot) != (1200, 675) or len(screenshot) >= 100000:
    parser.error('Screenshot must be a verified 1200x675 WebP smaller than100KB')

variant = args.variant
prefix = 'themes/' + variant + '/'
allowed = {'colors.toml', 'icons.theme', 'shell.toml', 'btop.theme', 'helix.toml',
           'chromium.theme', 'vscode-theme.json', 'light.mode'}
files = {}
sources = {}
for row in git('ls-tree', '-rz', source_commit, '--', prefix).split(b'\0'):
    if not row:
        continue
    meta, encoded_path = row.split(b'\t', 1)
    path = encoded_path.decode()
    relative = path.removeprefix(prefix)
    if relative in allowed or relative.startswith('backgrounds/'):
        mode, kind, sha = meta.decode().split()
        if mode != '100644' or kind != 'blob':
            parser.error(f'Unexpected source file type: {path}')
        data = git('cat-file', 'blob', sha)
        files[relative] = data
        sources[relative] = {'path': path, 'blob': sha, 'sha256': digest(data)}
if 'colors.toml' not in files or not any(p.startswith('backgrounds/') for p in files):
    parser.error('Source variant needs colors.toml and at least one background')
for name in ['LICENSE', 'THIRD_PARTY_NOTICES.md']:
    files[name] = git('show', source_commit + ':' + name)
    sources[name] = {'path': name, 'sha256': digest(files[name])}
files['preview.png'] = preview
files['.github/desktop.webp'] = screenshot
files['.github/export-standard.py'] = Path(__file__).read_bytes()

title = variant.replace('-', ' ').title()
repo = 'omarchy-' + variant + '-theme'
files['README.md'] = f'''# {title} for Omarchy

The standard-install edition of {title}, based on [Modus Themes by Protesilaos Stavrou](https://protesilaos.com/emacs/modus-themes/).

![{title} standard installation](preview.png)

## Install

In Omarchy, open **Install → Style → Theme** and paste this repository URL, or run:

```sh
omarchy theme install https://github.com/codingquark/{repo}
```

Select `{variant}` in the theme picker. Omarchy's theme updater can pull future updates from this repository.

If the full Modus package already owns a local `{variant}` theme symlink, choose which edition to keep before installing this one: both use the same theme name. The standard installer replaces an existing entry with that name.

## What this edition includes

The palette, wallpaper, shell, btop, Helix, browser tint and VS Code color files come from the [shared source package](https://github.com/codingquark/omarchy-modus-themes). Omarchy generates its standard terminal, Hyprland and Aether/Neovim configuration from `colors.toml`.

This edition does not include the full package's custom Modus Neovim highlight groups, exact terminal ANSI/cursor/opacity settings, Hyprland group-bar/opacity rules or automatic Cliamp integration. For those, use the [full package's documented installer](https://github.com/codingquark/omarchy-modus-themes#install-both-themes). The full package remains independently available and unchanged by this distribution.

The preview and [gallery screenshot](.github/desktop.webp) show a standard installation. No universal desktop contrast claim is made: the full package's 224-pair check covers different authored configurations.

## Source and updates

Generated from source commit [`{source_commit}`](https://github.com/codingquark/omarchy-modus-themes/commit/{source_commit}), validated against Omarchy [`{args.omarchy_ref}`](https://github.com/omacom/omarchy/commit/{args.omarchy_ref}). File provenance and image hashes are recorded in [.github/source.json](.github/source.json).

Maintain the palette and app color files in the shared source repository. This repository is an export, not a second manually edited palette. Publishing is manual and requires no CI credentials.

To prepare an update, use Python 3 and Git to export a reviewed source commit into a new directory, supplying previews captured and validated on its standard installation:

```sh
python3 .github/export-standard.py \\
  --source ../omarchy-modus-themes --ref SOURCE_COMMIT \\
  --variant {variant} --output ../{repo}-export \\
  --preview /path/to/verified-preview.png \\
  --screenshot /path/to/verified-desktop.webp \\
  --omarchy-ref TESTED_OMARCHY_COMMIT
```

The exporter reads committed Git objects, copies only supported files, and refuses an existing output directory. Install and validate the new export in isolation, check its screenshots, then replace the tracked export files in this checkout, review the diff, commit and push. Remove files absent from the new export; preserve `.git`. Update the corresponding gallery asset if the appearance changed. The exporter never installs a theme or publishes anything itself.

## License and credits

Independent port; not an official Modus Themes project. GPL-3.0-or-later; see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), including attribution and the Omarchy template notice. Original wallpaper by Dhavan Vaidya. [Support Protesilaos](https://protesilaos.com/donations/).
'''.encode()
metadata = {'variant': variant, 'source_repository': 'https://github.com/codingquark/omarchy-modus-themes',
            'source_commit': source_commit, 'omarchy_commit': args.omarchy_ref, 'source_files': sources,
            'images': {'preview.png': digest(preview), '.github/desktop.webp': digest(screenshot)}}
files['.github/source.json'] = (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode()
args.output.mkdir(parents=True)
for name, data in files.items():
    path = args.output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
print(f'Exported {variant} from {source_commit} to {args.output}')
