"""Small macOS helpers.

PySide6 does not expose NSApplication, so a few lines of ctypes/ObjC runtime
glue are used instead of adding PyObjC as a dependency.
"""

from __future__ import annotations

import ctypes
import ctypes.util

# NSApplicationActivationPolicyAccessory: menu bar app without a Dock icon.
_ACCESSORY_POLICY = 1

_objc: ctypes.CDLL | None = None
_ns_app: int | None = None


def hide_dock_icon() -> None:
    """Run as a menu bar only app by hiding the Dock icon."""
    objc, ns_app = _shared_application()
    set_policy = ctypes.cast(
        objc.objc_msgSend,
        ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long),
    )
    set_policy(ns_app, objc.sel_registerName(b"setActivationPolicy:"), _ACCESSORY_POLICY)


def activate_application() -> None:
    """Bring the app to the front; needed when showing a window as accessory app."""
    objc, ns_app = _shared_application()
    activate = ctypes.cast(
        objc.objc_msgSend,
        ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool),
    )
    activate(ns_app, objc.sel_registerName(b"activateIgnoringOtherApps:"), True)


def _shared_application() -> tuple[ctypes.CDLL, int]:
    global _objc, _ns_app
    if _objc is None:
        library = ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
        _objc = ctypes.cdll.LoadLibrary(library)
        _objc.objc_getClass.restype = ctypes.c_void_p
        _objc.objc_getClass.argtypes = [ctypes.c_char_p]
        _objc.sel_registerName.restype = ctypes.c_void_p
        _objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = ctypes.cast(
            _objc.objc_msgSend,
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
        )
        _ns_app = send(
            _objc.objc_getClass(b"NSApplication"),
            _objc.sel_registerName(b"sharedApplication"),
        )
    return _objc, _ns_app
