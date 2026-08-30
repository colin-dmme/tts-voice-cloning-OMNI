"""Windows shell identity and native icon integration shared by desktop UIs."""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes
from importlib import resources
from pathlib import Path


APP_USER_MODEL_ID = "ColinTTS.Local.Desktop"
APP_DISPLAY_NAME = "Colin TTS Local"
APP_PUBLISHER = "Colin TTS"

_ICON_HANDLES: list[int] = []


def app_asset_path(filename: str) -> Path:
    """Return an unpacked package asset path used by Qt, Tk, and packaging."""
    return Path(str(resources.files("omni_tts_shared").joinpath("assets", filename)))


def app_icon_path() -> Path:
    return app_asset_path("colin_tts.ico")


def app_icon_png_path() -> Path:
    return app_asset_path("colin_tts_icon.png")


def set_windows_process_identity() -> bool:
    """Assign the explicit shell identity before any top-level window exists."""
    if sys.platform != "win32":
        return False
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    setter = shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [wintypes.LPCWSTR]
    setter.restype = ctypes.c_long
    return setter(APP_USER_MODEL_ID) >= 0


def apply_native_window_identity(hwnd: int) -> bool:
    """Set HWND icons and its per-window AppUserModelID for taskbar/Alt+Tab."""
    if sys.platform != "win32" or not hwnd:
        return False
    outer_hwnd = _root_hwnd(hwnd)
    icon_ok = _set_hwnd_icons(outer_hwnd, app_icon_path())
    app_id_ok = _set_hwnd_app_user_model_id(outer_hwnd)
    return icon_ok and app_id_ok


def configure_tk_window(root) -> None:
    """Apply Tk-level assets, followed by native HWND identity after creation."""
    ico_path = app_icon_path()
    png_path = app_icon_png_path()
    if ico_path.exists():
        root.iconbitmap(default=str(ico_path))
    if png_path.exists():
        import tkinter as tk

        photo = tk.PhotoImage(master=root, file=str(png_path))
        root.iconphoto(True, photo)
        root._colin_tts_icon_photo = photo

    root.update_idletasks()

    def apply_native() -> None:
        apply_native_window_identity(int(root.winfo_id()))

    apply_native()
    root.after_idle(apply_native)


def _root_hwnd(hwnd: int) -> int:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_ancestor = user32.GetAncestor
    get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    get_ancestor.restype = wintypes.HWND
    return int(get_ancestor(wintypes.HWND(hwnd), 2) or hwnd)  # GA_ROOT


def _set_hwnd_icons(hwnd: int, icon_path: Path) -> bool:
    if not icon_path.exists():
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    load_image = user32.LoadImageW
    load_image.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    load_image.restype = wintypes.HANDLE
    send_message = user32.SendMessageW
    send_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    send_message.restype = wintypes.LPARAM
    get_metric = user32.GetSystemMetrics
    get_metric.argtypes = [ctypes.c_int]
    get_metric.restype = ctypes.c_int

    image_icon = 1
    load_from_file = 0x0010
    wm_seticon = 0x0080
    dimensions = (
        (1, get_metric(11), get_metric(12)),  # ICON_BIG / SM_CXICON / SM_CYICON
        (0, get_metric(49), get_metric(50)),  # ICON_SMALL / SM_CXSMICON / SM_CYSMICON
        (2, get_metric(49), get_metric(50)),  # ICON_SMALL2
    )
    loaded = False
    for icon_kind, width, height in dimensions:
        handle = load_image(None, str(icon_path), image_icon, width, height, load_from_file)
        if not handle:
            continue
        _ICON_HANDLES.append(int(handle))
        send_message(wintypes.HWND(hwnd), wm_seticon, icon_kind, int(handle))
        loaded = True
    return loaded


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "_GUID":
        parsed = uuid.UUID(value)
        data = parsed.bytes_le
        return cls(
            int.from_bytes(data[0:4], "little"),
            int.from_bytes(data[4:6], "little"),
            int.from_bytes(data[6:8], "little"),
            (ctypes.c_ubyte * 8).from_buffer_copy(data[8:16]),
        )


class _PROPERTYKEY(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT_VALUE(ctypes.Union):
    _fields_ = [("pwszVal", ctypes.c_void_p), ("uhVal", ctypes.c_uint64)]


class _PROPVARIANT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("value", _PROPVARIANT_VALUE),
    ]


def _set_hwnd_app_user_model_id(hwnd: int) -> bool:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED; already-initialized is fine.

    iid_property_store = _GUID.from_string("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
    store = ctypes.c_void_p()
    getter = shell32.SHGetPropertyStoreForWindow
    getter.argtypes = [wintypes.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    getter.restype = ctypes.c_long
    if getter(wintypes.HWND(hwnd), ctypes.byref(iid_property_store), ctypes.byref(store)) < 0:
        return False

    vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
    set_value = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.POINTER(_PROPERTYKEY),
        ctypes.POINTER(_PROPVARIANT),
    )(vtable[6])
    commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[7])

    app_id_buffer = ctypes.create_unicode_buffer(APP_USER_MODEL_ID)
    value = _PROPVARIANT()
    value.vt = 31  # VT_LPWSTR
    value.pwszVal = ctypes.cast(app_id_buffer, ctypes.c_void_p).value
    key = _PROPERTYKEY(
        _GUID.from_string("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
        5,
    )
    try:
        return set_value(store, ctypes.byref(key), ctypes.byref(value)) >= 0 and commit(store) >= 0
    finally:
        release(store)
