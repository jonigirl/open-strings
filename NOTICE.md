# Open Strings

Open Strings is a fork of [Smart Citizen](https://github.com/Osiris-DevWorks/smart-citizen)
by Osiris DevWorks.

- Upstream copyright (C) 2024-2026 Osiris DevWorks.
- Fork copyright (C) 2026 Joni Hayes.

This fork has been modified by Joni Hayes starting in 2026. The original
"Smart Citizen" branding, logos, and donation links have been removed.

The configurable data folder feature was adapted from a community contribution
to the Smart Citizen upstream by Coerwyn
(https://github.com/Osiris-DevWorks/smart-citizen/pull/3).

The combined work is licensed under the GNU General Public License v3.0
only (GPL-3.0-only). See `LICENSE` for the full terms.

## Bundled third-party tools

### unp4k / unforge

Open Strings downloads upstream `unp4k.exe` and uses a patched `unforge.cli.exe`
based on [unp4k](https://github.com/dolkensp/unp4k) by Peter Dolkens and contributors.
The patched unforge ZIP is included in release installers and supplied as a separate
release asset. Tools are installed into `%APPDATA%\Open Strings\tools\<version>\`.

The patched package retains upstream's MIT notice in `LICENSE.txt`. The
Open Strings-specific modifications are supplied under GPL-3.0-only, with the
full license in `OPENSTRINGS-LICENSE.txt`. The package also includes this notice
and build provenance identifying the pinned upstream revision and patch hashes.

Corresponding modifications and build instructions are available in the
[Open Strings source](https://github.com/jonigirl/open-strings), under
`scripts/build/unforge/` and `scripts/build/build_unforge.py`. For a release, use
its matching version tag. The upstream source revision is recorded in the
package's `build-info.json` and can be obtained from the upstream repository.

Copyright (C) Peter Dolkens and contributors.

Upstream components are licensed under the MIT License:

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## Bundled fonts

### Orbitron

Copyright (C) 2009 Matt McInerney.

Licensed under the SIL Open Font License, Version 1.1.
See `assets/fonts/Orbitron-OFL.txt` for the full licence text.

### Atkinson Hyperlegible

Copyright (C) 2020 Braille Institute of America, Inc.

Licensed under the SIL Open Font License, Version 1.1.
See `assets/fonts/OFL-Atkinson.txt` for the full licence text.
