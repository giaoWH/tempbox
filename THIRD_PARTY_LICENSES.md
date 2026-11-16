# Third-Party Licenses

TempBox's own source code is licensed under the **Apache License 2.0**
(see [LICENSE](LICENSE) and [NOTICE](NOTICE)). That license does not replace or
supersede the licenses of third-party components.

This file summarizes the components relevant to the packaged macOS application.
The corresponding license texts are provided in [`licenses/`](licenses/).

## Runtime components

| Component | Version | License | Notes |
|---|---|---|---|
| Python | 3.14.10 | Python Software Foundation License 2.0 | Bundled Python runtime; see `licenses/Python-3.14.txt` |
| PySide6 | 6.12.0 | LGPL-3.0-only (selected) | Qt for Python bindings; upstream also offers GPL/commercial options |
| Shiboken6 | 6.12.0 | LGPL-3.0-only (selected) | PySide6 binding runtime |
| Qt | 6.12.0 | LGPL-3.0-only (selected) | QtCore, QtGui, QtWidgets and other Qt frameworks/plugins collected by PyInstaller; upstream also offers GPL/commercial options |
| Send2Trash | 2.2.0 | BSD-3-Clause | Copyright (c) 2017, Virgil Dupras |
| PyInstaller | 6.22.3 | GPL-2.0-or-later with Bootloader Exception | Build tool; its bootloader is embedded in the application. Run-time hooks are Apache-2.0; see `licenses/PyInstaller-6.22.3-COPYING.txt` |
| macOS system frameworks | OS-provided | Apple system terms | Not redistributed inside the application |

## Bundled native libraries

PyInstaller also includes the following native libraries from the Python
environment. Their license texts are in `licenses/`.

| Library | Version | License |
|---|---|---|
| OpenSSL (libcrypto/libssl) | 3.6.5 | Apache-2.0 |
| zlib | 1.3.2 | zlib License |
| libffi | 3.7.0 | MIT |
| libexpat | 2.9.0 | MIT |
| bzip2 | 1.0.8 | bzip2 License |
| liblzma (XZ Utils) | 5.8.3 | Public domain / 0BSD components (see upstream COPYING) |
| libmpdec | 4.0.0 | BSD-2-Clause |
| zstd | 1.5.7 | BSD-3-Clause |

These versions come from the Conda environment used for the v1.0.0 build. Recheck
them when the Python environment is updated.

## License texts

- [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt) — TempBox source license
- [`licenses/LGPL-3.0.txt`](licenses/LGPL-3.0.txt) — PySide6, Shiboken6 and Qt
- [`licenses/GPL-3.0.txt`](licenses/GPL-3.0.txt) — alternative upstream Qt/PySide license text
- [`licenses/GPL-2.0.txt`](licenses/GPL-2.0.txt) — PyInstaller bootloader license family
- [`licenses/PyInstaller-6.22.3-COPYING.txt`](licenses/PyInstaller-6.22.3-COPYING.txt) — PyInstaller license and bootloader exception
- [`licenses/Python-3.14.txt`](licenses/Python-3.14.txt) — Python runtime license and bundled notices
- [`licenses/send2trash-BSD-3-Clause.txt`](licenses/send2trash-BSD-3-Clause.txt) — Send2Trash license
- [`licenses/openssl-3.6.5-LICENSE.txt`](licenses/openssl-3.6.5-LICENSE.txt) — OpenSSL
- [`licenses/zlib-1.3.2-LICENSE.txt`](licenses/zlib-1.3.2-LICENSE.txt) — zlib
- [`licenses/libffi-3.7.0-LICENSE.txt`](licenses/libffi-3.7.0-LICENSE.txt) — libffi
- [`licenses/libexpat-2.9.0-COPYING.txt`](licenses/libexpat-2.9.0-COPYING.txt) — libexpat
- [`licenses/bzip2-1.0.8-LICENSE.txt`](licenses/bzip2-1.0.8-LICENSE.txt) — bzip2
- [`licenses/liblzma-5.8.3-COPYING.txt`](licenses/liblzma-5.8.3-COPYING.txt) — liblzma/XZ Utils
- [`licenses/liblzma-5.8.3-COPYING-0BSD.txt`](licenses/liblzma-5.8.3-COPYING-0BSD.txt) — liblzma 0BSD components
- [`licenses/libmpdec-4.0.0-COPYRIGHT.txt`](licenses/libmpdec-4.0.0-COPYRIGHT.txt) — libmpdec
- [`licenses/zstd-1.5.7-LICENSE.txt`](licenses/zstd-1.5.7-LICENSE.txt) — zstd

## Qt / LGPL compliance notes

TempBox uses the LGPL-3.0 option for Qt and PySide6. The packaged application is
built as a one-directory PyInstaller bundle. Qt, PySide6, Shiboken6 and their
plugins are separate dynamically linked frameworks/libraries in the bundle; the
application does not statically link them. Users may replace those libraries with
compatible versions, and the complete corresponding source code for the exact
versions is available from the upstream projects:

The v1.0.0 bundle currently contains QtCore, QtDBus, QtGui, QtNetwork, QtOpenGL,
QtPdf, QtQml, QtQmlMeta, QtQmlModels, QtQmlWorkerScript, QtQuick, QtSvg,
QtVirtualKeyboard, QtVirtualKeyboardQml and QtWidgets frameworks plus Qt plugins
selected by PyInstaller. All of these are covered by the LGPL-3.0 option noted
above. This list reflects the actual build output and should be rechecked whenever
the PyInstaller/Qt version changes.

- Qt source: <https://code.qt.io/cgit/qt/qtbase.git/>
- Qt for Python / PySide6 source: <https://code.qt.io/cgit/pyside/pyside-setup.git/>
- PySide6 release notes and source archives: <https://pypi.org/project/PySide6/6.12.0/>

The PySide6 wheel does not ship separate notice files for every Qt third-party
component. Before publishing a release, Qt's third-party notices should be reviewed
against the actual bundle; upstream source references include
<https://code.qt.io/cgit/qt/qtbase.git/tree/src/3rdparty>. No Qt source files were
modified by TempBox.

## Python

The Python runtime is included by PyInstaller. Its license file also contains
notices for third-party components bundled with that Python distribution. See
`licenses/Python-3.14.txt`.

## PyInstaller

PyInstaller is used only to build the macOS application. The generated application
contains the PyInstaller bootloader and PyInstaller runtime hooks; the bootloader is
distributed under the GPL-2.0-or-later with the PyInstaller Bootloader Exception.
The full text is included in `licenses/PyInstaller-6.22.3-COPYING.txt`.

This summary is provided for attribution and convenience, not as legal advice.
