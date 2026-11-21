"""
Windows 全局桌面鼠标特效悬浮层 (Windows Desktop Mouse FX Overlay - 240Hz 旗舰版)
---------------------------------------------------------------------------------
依赖安装:
    pip install PyQt6

运行方法:
    python windows_mouse_fx.py

抢救系统指针（被强杀后指针卡在定制样式时）:
    python windows_mouse_fx.py --restore
    打包版等价于 MouseFX.exe --restore，只还原指针、不开界面，执行完立即退出

打包成 exe:
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name MouseFX windows_mouse_fx.py

特性说明:
    - 单实例运行保护：重复双击会自动唤醒已运行实例的控制面板，不会重影双开。
    - 全屏自动避让：玩全屏游戏或全屏看视频时自动暂停特效并恢复原生指针，退出全屏自动恢复。
    - 一键场景预设 + 连续滑动条微调（强度 0.4x~2.5x、蒙版 0%~85%）+ 自定义取色器。
    - 6 种艺术风格 + 6 项可叠加趣味功能（含左右键演示波纹区分）+ 全套 13 种系统指针 + 开机自启。
"""

import atexit
import base64
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import zlib
from PyQt6.QtCore import QPointF, QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QRegion,
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

if sys.platform == "win32":
    import winreg


APP_NAME = "MouseFX"
IPC_SERVER_NAME = "MouseFX_SingleInstance_IPC_v1"
MUTEX_NAME = "MouseFX_SingleInstance_Mutex_v1"


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", ctypes.c_void_p),
        ("hbmColor", ctypes.c_void_p),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def get_config_path() -> Path:
    """获取配置文件路径，保证打包成单文件 exe 后也能稳定读写。"""
    appdata = os.environ.get("APPDATA")
    base_dir = Path(appdata) / APP_NAME if appdata else Path.home() / f".{APP_NAME.lower()}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "config.json"


def load_config() -> dict:
    path = get_config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_config(data: dict) -> None:
    path = get_config_path()
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_startup_command() -> str:
    """生成开机自启命令（兼容打包后的 exe 与直接运行的 .py 脚本）。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else python_exe
    script_path = os.path.abspath(__file__)
    return f'"{runner}" "{script_path}"'


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    """写入或移除 Windows 当前用户开机自启注册表项，返回最终状态。"""
    if sys.platform != "win32":
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return is_autostart_enabled()
    except Exception:
        return is_autostart_enabled()


def enable_windows_click_through(hwnd: int) -> None:
    """使用 Windows API 确保窗口完全穿透鼠标事件且不抢占焦点。"""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        )
    except Exception:
        pass


def apply_windows_topmost(hwnd: int, topmost: bool) -> None:
    """使用 Win32 SetWindowPos 强制置顶，或立即沉底到所有普通窗口之后。"""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        HWND_TOPMOST = ctypes.c_void_p(-1)
        HWND_NOTOPMOST = ctypes.c_void_p(-2)
        HWND_BOTTOM = ctypes.c_void_p(1)
        flags = 0x0002 | 0x0001 | 0x0010  # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        if topmost:
            user32.SetWindowPos(ctypes.c_void_p(hwnd), HWND_TOPMOST, 0, 0, 0, 0, flags)
        else:
            user32.SetWindowPos(ctypes.c_void_p(hwnd), HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            user32.SetWindowPos(ctypes.c_void_p(hwnd), HWND_BOTTOM, 0, 0, 0, 0, flags)
    except Exception:
        pass


def is_mouse_button_down(vk_code: int) -> bool:
    """全局检测指定鼠标按键（0x01 左键 / 0x02 右键）是否按下。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def is_foreground_fullscreen(ignore_hwnds: set[int]) -> bool:
    """精确检测当前前台窗口是否为真正的全屏游戏/视频（不会误判高DPI或普通最大化窗口）。"""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or int(hwnd) in ignore_hwnds:
            return False

        cls_buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, cls_buf, 128)
        if cls_buf.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False

        # 带有常规标题栏的窗口属于普通软件/最大化窗口，不算独占/无边框全屏
        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if (style & WS_CAPTION) == WS_CAPTION:
            return False

        rect = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False

        MONITOR_DEFAULTTONEAREST = 2
        hmon = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return False
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(mi)):
            return False

        m = mi.rcMonitor
        return (
            rect.left <= m.left + 2
            and rect.top <= m.top + 2
            and rect.right >= m.right - 2
            and rect.bottom >= m.bottom - 2
        )
    except Exception:
        return False


def get_foreground_process_name(ignore_hwnds: set[int]) -> str:
    """获取当前前台窗口所属进程名（小写，如 photoshop.exe），失败返回空串。"""
    if sys.platform != "win32":
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or int(hwnd) in ignore_hwnds:
            return ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32.OpenProcess.restype = ctypes.c_void_p
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if kernel32.QueryFullProcessImageNameW(ctypes.c_void_p(hproc), 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(hproc))
    except Exception:
        pass
    return ""


_wheel_hook_handle = None
_wheel_hook_proc = None
_last_wheel_event_time = 0.0
_TYPING_VKS = (0x08, 0x0D, 0x20, *range(0x30, 0x5B))


def is_typing_active() -> bool:
    """轻量检测是否有常规打字按键输入（仅在开启自动让位时轮询）。"""
    if sys.platform != "win32":
        return False
    try:
        get_state = ctypes.windll.user32.GetAsyncKeyState
        for vk in _TYPING_VKS:
            if get_state(vk) & 0x0001:
                return True
    except Exception:
        pass
    return False


def install_wheel_hook() -> None:
    """安装极简全局滚轮时间戳钩子（仅记录滚轮时间，不拦截任何事件）。"""
    global _wheel_hook_handle, _wheel_hook_proc
    if sys.platform != "win32" or _wheel_hook_handle:
        return
    try:
        user32 = ctypes.windll.user32
        WH_MOUSE_LL = 14
        WM_MOUSEWHEEL = 0x020A
        WM_MOUSEHWHEEL = 0x020E
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t

        def _proc(n_code: int, w_param: int, l_param: int) -> int:
            global _last_wheel_event_time
            if n_code >= 0 and w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                _last_wheel_event_time = time.perf_counter()
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        _wheel_hook_proc = HOOKPROC(_proc)
        _wheel_hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, _wheel_hook_proc, None, 0)
    except Exception:
        _wheel_hook_handle = None
        _wheel_hook_proc = None


def uninstall_wheel_hook() -> None:
    global _wheel_hook_handle, _wheel_hook_proc
    if sys.platform != "win32" or not _wheel_hook_handle:
        return
    try:
        ctypes.windll.user32.UnhookWindowsHookEx(ctypes.c_void_p(_wheel_hook_handle))
    except Exception:
        pass
    _wheel_hook_handle = None
    _wheel_hook_proc = None


def restore_system_cursors() -> None:
    """恢复 Windows 默认全套系统鼠标指针。"""
    if sys.platform != "win32":
        return
    try:
        SPI_SETCURSORS = 0x0057
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
    except Exception:
        pass


def get_session_lock_path() -> Path:
    """会话哨兵文件路径：记录当前实例 PID，正常退出时删除。"""
    return get_config_path().with_name("session.lock")


def is_pid_alive(pid: int) -> bool:
    """判断 PID 是否仍是活着的进程（用它区分“残留哨兵”与“另一实例正在运行”）。"""
    if sys.platform != "win32" or pid <= 0:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        try:
            WAIT_TIMEOUT = 0x00000102
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        return False


def read_session_lock_pid() -> int:
    try:
        data = json.loads(get_session_lock_path().read_text(encoding="utf-8"))
        return int(data.get("pid", 0))
    except Exception:
        return 0


def write_session_lock() -> None:
    try:
        get_session_lock_path().write_text(
            json.dumps({"pid": os.getpid(), "since": time.time()}), encoding="utf-8"
        )
    except Exception:
        pass


def clear_session_lock() -> None:
    try:
        get_session_lock_path().unlink(missing_ok=True)
    except Exception:
        pass


def heal_stale_cursor_state() -> bool:
    """上次实例被强杀（来不及还原指针）时，本次启动先还原一次系统指针。

    判据：哨兵文件还在，且其中的 PID 已经不存在。返回是否真的修复过。
    """
    if not get_session_lock_path().exists():
        return False
    pid = read_session_lock_pid()
    if is_pid_alive(pid):
        return False  # 另一个实例还活着，指针是它有意设置的，别去动
    restore_system_cursors()
    clear_session_lock()
    return True


_shutdown_done = False
_instance_mutex_handle = 0


def acquire_single_instance_mutex() -> bool:
    """用 Windows 命名互斥量做原子级的单实例判定。

    比 QLocalServer 探测可靠得多：互斥量在进程刚开始执行时就能定胜负，
    而 IPC 必须等 Qt 初始化完才 listen，那段空窗期足够第二个实例挤进来
    （两个实例会互相覆盖系统指针，谁先退出谁就把另一个的指针冲掉）。
    """
    global _instance_mutex_handle
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.restype = wintypes.DWORD
        handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183
        if not handle:
            return True  # 拿不到互斥量宁可不做限制，也别把用户挡在门外
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return False
        _instance_mutex_handle = int(handle)
        return True
    except Exception:
        return True


def release_single_instance_mutex() -> None:
    global _instance_mutex_handle
    if not _instance_mutex_handle or sys.platform != "win32":
        return
    try:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_instance_mutex_handle))
    except Exception:
        pass
    _instance_mutex_handle = 0


def shutdown_and_restore() -> None:
    """幂等收尾：还原系统指针并清掉哨兵，重复调用无副作用。

    只有真正持有实例锁的进程才允许动系统指针——避免第二实例退出时
    把正在运行实例的定制指针冲成默认。
    """
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    uninstall_wheel_hook()
    if _instance_mutex_handle:
        restore_system_cursors()
        clear_session_lock()
    release_single_instance_mutex()


def _render_normal_cursor_image(
    style_id: str, primary: QColor, secondary: QColor, is_hand: bool = False
) -> tuple[QImage, int, int]:
    """绘制各风格的主指针 / 链接手型指针。"""
    size = 32
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    accent = secondary if is_hand else primary
    hx, hy = 4, 4

    if style_id == "sakura":
        hx, hy = 16, 16
        r_glow = 12.0 if is_hand else 10.0
        glow = QRadialGradient(QPointF(16, 16), r_glow)
        glow.setColorAt(0.0, QColor(255, 241, 242, 230))
        glow.setColorAt(0.45, QColor(249, 168, 212, 185))
        glow.setColorAt(1.0, QColor(244, 114, 182, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(16, 16), r_glow, r_glow)

        r_dot = 6.2 if is_hand else 5.0
        p.setPen(QPen(QColor(76, 5, 25, 165), 2.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(16, 16), r_dot, r_dot)
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.setBrush(QBrush(QColor("#f472b6" if is_hand else "#f9a8d4")))
        p.drawEllipse(QPointF(16, 16), r_dot, r_dot)

    elif style_id == "ink":
        hx, hy = 3, 3
        p.setPen(QPen(QColor("#44403c"), 4.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(15, 15), QPointF(29, 29))

        p.setPen(QPen(QColor("#dc2626"), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(13, 13), QPointF(17, 17))

        nib = QPainterPath(QPointF(3, 3))
        nib.cubicTo(QPointF(5, 13), QPointF(10, 17), QPointF(16, 16))
        nib.cubicTo(QPointF(17, 10), QPointF(13, 5), QPointF(3, 3))
        p.setPen(QPen(QColor(24, 24, 27, 155), 2.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(nib)
        p.setPen(QPen(QColor("#f5f5f4"), 1.2))
        p.setBrush(QBrush(QColor("#b91c1c" if is_hand else "#18181b")))
        p.drawPath(nib)

    elif style_id == "prism":
        hx, hy = 4, 4
        poly = QPolygonF([QPointF(4, 4), QPointF(24, 14), QPointF(14, 16), QPointF(12, 25)])
        grad = QLinearGradient(QPointF(4, 4), QPointF(22, 22))
        grad.setColorAt(0.0, QColor(255, 255, 255, 235))
        grad.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), 185))
        grad.setColorAt(1.0, QColor(secondary.red(), secondary.green(), secondary.blue(), 200))
        p.setPen(
            QPen(QColor(15, 23, 42, 165), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)
        p.setPen(
            QPen(QColor("#ffffff"), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        p.setBrush(QBrush(grad))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(255, 255, 255, 195), 1.0))
        p.drawLine(QPointF(4, 4), QPointF(14, 16))

    elif style_id == "constellation":
        hx, hy = 4, 4
        pts = [QPointF(4, 4), QPointF(22, 13), QPointF(13, 15), QPointF(11, 24)]
        p.setPen(QPen(accent, 1.6))
        p.setBrush(QBrush(QColor(15, 23, 42, 205)))
        p.drawPolygon(QPolygonF(pts))
        p.setPen(Qt.PenStyle.NoPen)
        for idx, pt in enumerate(pts):
            p.setBrush(QColor("#ffffff") if idx == 0 else secondary)
            p.drawEllipse(pt, 2.3 if idx == 0 else 1.8, 2.3 if idx == 0 else 1.8)

    elif style_id == "magnetic":
        hx, hy = 4, 4
        poly = QPolygonF([QPointF(4, 4), QPointF(19, 13), QPointF(11, 14), QPointF(9, 22)])
        p.setPen(
            QPen(QColor(15, 23, 42, 165), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)
        p.setPen(
            QPen(accent, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawPolygon(poly)
        if is_hand:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(4, 4), 3.0, 3.0)

    else:
        hx, hy = 4, 4
        glow = QRadialGradient(QPointF(7, 7), 10)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 175))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(7, 7), 10, 10)

        poly = QPolygonF([QPointF(4, 4), QPointF(20, 13), QPointF(12, 14), QPointF(10, 22)])
        p.setPen(
            QPen(QColor(15, 23, 42, 165), 2.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)
        p.setPen(
            QPen(accent, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawPolygon(poly)

    p.end()
    return img, hx, hy


def _render_utility_cursor_image(
    kind: str, style_id: str, primary: QColor, secondary: QColor
) -> tuple[QImage, int, int]:
    """绘制全套辅助指针（文本输入、十字准星、等待、禁用、四向/双向缩放）。"""
    size = 32
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if style_id == "sakura":
        c1, c2 = QColor("#f9a8d4"), QColor("#f472b6")
    elif style_id == "ink":
        c1, c2 = QColor("#27272a"), QColor("#dc2626")
    else:
        c1, c2 = primary, secondary

    outline = QPen(
        QColor("#ffffff") if style_id != "ink" else QColor("#f5f5f4"),
        3.2,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    fg = QPen(c1, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)

    def _draw_double_arrow(dx: float, dy: float) -> None:
        p1 = QPointF(16 - dx * 9, 16 - dy * 9)
        p2 = QPointF(16 + dx * 9, 16 + dy * 9)
        nx, ny = -dy, dx
        for pen in (outline, fg):
            p.setPen(pen)
            p.drawLine(p1, p2)
            for tip, s in ((p1, 1.0), (p2, -1.0)):
                p.drawLine(
                    tip, QPointF(tip.x() + s * dx * 4 + nx * 3.5, tip.y() + s * dy * 4 + ny * 3.5)
                )
                p.drawLine(
                    tip, QPointF(tip.x() + s * dx * 4 - nx * 3.5, tip.y() + s * dy * 4 - ny * 3.5)
                )

    if kind == "ibeam":
        for pen in (outline, fg):
            p.setPen(pen)
            p.drawLine(QPointF(16, 6), QPointF(16, 26))
            p.drawLine(QPointF(12, 6), QPointF(20, 6))
            p.drawLine(QPointF(12, 26), QPointF(20, 26))

    elif kind == "cross":
        for pen in (outline, fg):
            p.setPen(pen)
            p.drawLine(QPointF(6, 16), QPointF(13, 16))
            p.drawLine(QPointF(19, 16), QPointF(26, 16))
            p.drawLine(QPointF(16, 6), QPointF(16, 13))
            p.drawLine(QPointF(16, 19), QPointF(16, 26))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c2)
        p.drawEllipse(QPointF(16, 16), 2.0, 2.0)

    elif kind == "wait":
        p.setPen(outline)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(16, 16), 9.0, 9.0)
        p.setPen(QPen(c1, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(7, 7, 18, 18), 0, 240 * 16)
        p.setPen(QPen(c2, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(10, 10, 12, 12), 180 * 16, 160 * 16)

    elif kind == "no":
        no_pen_out = QPen(QColor("#ffffff"), 3.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        no_pen_fg = QPen(
            QColor("#ef4444") if style_id != "sakura" else c2,
            2.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        for pen in (no_pen_out, no_pen_fg):
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(16, 16), 8.5, 8.5)
            p.drawLine(QPointF(10, 10), QPointF(22, 22))

    elif kind == "sizewe":
        _draw_double_arrow(1.0, 0.0)
    elif kind == "sizens":
        _draw_double_arrow(0.0, 1.0)
    elif kind == "sizenwse":
        _draw_double_arrow(0.707, 0.707)
    elif kind == "sizenesw":
        _draw_double_arrow(0.707, -0.707)
    elif kind == "sizeall":
        _draw_double_arrow(1.0, 0.0)
        _draw_double_arrow(0.0, 1.0)

    p.end()
    return img, 16, 16


def _set_win32_cursor_from_qimage(img: QImage, hx: int, hy: int, ocr_id: int) -> None:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.CreateIconIndirect.restype = ctypes.c_void_p
    user32.SetSystemCursor.argtypes = [ctypes.c_void_p, wintypes.DWORD]

    w, h = img.width(), img.height()
    bits = img.bits()
    bits.setsize(img.sizeInBytes())
    raw_bytes = bytes(bits)

    hbm_color = gdi32.CreateBitmap(w, h, 1, 32, raw_bytes)
    mask_bytes = bytes((w * h) // 8)
    hbm_mask = gdi32.CreateBitmap(w, h, 1, 1, mask_bytes)

    ii = _ICONINFO()
    ii.fIcon = False
    ii.xHotspot = hx
    ii.yHotspot = hy
    ii.hbmMask = hbm_mask
    ii.hbmColor = hbm_color

    hcursor = user32.CreateIconIndirect(ctypes.byref(ii))
    gdi32.DeleteObject(ctypes.c_void_p(hbm_color))
    gdi32.DeleteObject(ctypes.c_void_p(hbm_mask))

    if hcursor:
        user32.SetSystemCursor(ctypes.c_void_p(hcursor), ocr_id)


def apply_style_cursor(style_id: str, primary: QColor, secondary: QColor) -> None:
    """将全套对应风格的定制指针应用到 Windows 系统指针槽位。"""
    if sys.platform != "win32":
        return
    try:
        norm_img, nx, ny = _render_normal_cursor_image(style_id, primary, secondary, is_hand=False)
        for ocr_id in (32512, 32516, 32650):
            _set_win32_cursor_from_qimage(norm_img, nx, ny, ocr_id)

        hand_img, hx, hy = _render_normal_cursor_image(style_id, primary, secondary, is_hand=True)
        _set_win32_cursor_from_qimage(hand_img, hx, hy, 32649)

        utility_map = {
            32513: "ibeam",
            32514: "wait",
            32515: "cross",
            32642: "sizenwse",
            32643: "sizenesw",
            32644: "sizewe",
            32645: "sizens",
            32646: "sizeall",
            32648: "no",
        }
        for ocr_id, kind in utility_map.items():
            u_img, ux, uy = _render_utility_cursor_image(kind, style_id, primary, secondary)
            _set_win32_cursor_from_qimage(u_img, ux, uy, ocr_id)
    except Exception:
        pass


def blend_color(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


def dt_lerp(factor_60hz: float, dt_scale: float) -> float:
    return 1.0 - (1.0 - factor_60hz) ** dt_scale


def build_sakura_petal_path(size: float) -> QPainterPath:
    path = QPainterPath(QPointF(0.0, size * 0.9))
    path.cubicTo(
        QPointF(-size * 0.95, size * 0.25),
        QPointF(-size * 0.85, -size * 0.75),
        QPointF(-size * 0.18, -size * 0.85),
    )
    path.lineTo(QPointF(0.0, -size * 0.55))
    path.lineTo(QPointF(size * 0.18, -size * 0.85))
    path.cubicTo(
        QPointF(size * 0.85, -size * 0.75),
        QPointF(size * 0.95, size * 0.25),
        QPointF(0.0, size * 0.9),
    )
    path.closeSubpath()
    return path


_SAKURA_UNIT_PATH = build_sakura_petal_path(1.0)


class MouseFXOverlay(QWidget):
    STYLES = {
        "spotlight": "柔光氛围光晕",
        "constellation": "蛛网引力连线",
        "magnetic": "极简磁力光环",
        "ink": "水墨丹青",
        "prism": "光学棱镜",
        "sakura": "唯美落樱",
    }

    PALETTES = {
        "cyber": {
            "name": "赛博青粉",
            "colors": ["#22d3ee", "#e879f9", "#38bdf8", "#a855f7"],
        },
        "sakura_pink": {
            "name": "樱花粉黛",
            "colors": ["#f472b6", "#fbcfe8", "#fb7185", "#e879f9"],
        },
        "sunset": {
            "name": "日落金橙",
            "colors": ["#fbbf24", "#fb7185", "#f97316", "#f43f5e"],
        },
        "matrix": {
            "name": "骇客翠绿",
            "colors": ["#34d399", "#10b981", "#a3e635", "#2dd4bf"],
        },
        "aurora": {
            "name": "流光幻彩 (动态渐变)",
            "colors": ["#22d3ee", "#a855f7", "#f43f5e", "#fbbf24"],
        },
        "mono": {
            "name": "极简银白",
            "colors": ["#ffffff", "#e4e4e7", "#a1a1aa", "#71717a"],
        },
        "custom": {
            "name": "自定义取色",
            "colors": ["#38bdf8", "#f472b6", "#818cf8", "#fb7185"],
        },
    }

    PRESETS = {
        "night_focus": {
            "label": "深夜专注",
            "style_id": "spotlight",
            "palette_id": "cyber",
            "intensity": 1.1,
            "dark_mask_alpha": 155,
            "enable_flashlight": True,
            "enable_ribbon": False,
            "enable_water_wake": False,
            "enable_fireworks": False,
        },
        "spring_desktop": {
            "label": "春日落樱",
            "style_id": "sakura",
            "palette_id": "sakura_pink",
            "intensity": 1.2,
            "dark_mask_alpha": 0,
            "enable_flashlight": False,
            "enable_ribbon": True,
            "enable_water_wake": False,
            "enable_fireworks": True,
        },
        "minimal_work": {
            "label": "极简办公",
            "style_id": "prism",
            "palette_id": "mono",
            "intensity": 1.0,
            "dark_mask_alpha": 0,
            "enable_flashlight": False,
            "enable_ribbon": False,
            "enable_water_wake": False,
            "enable_fireworks": False,
        },
    }

    SAKURA_COLORS = ["#fbcfe8", "#f9a8d4", "#fda4af", "#ffe4e6"]

    def __init__(self) -> None:
        super().__init__()
        self._apply_defaults(load_config())

        self.paused = False
        self.auto_avoiding = False
        self._last_fg_hwnd = 0
        self.fullscreen_check_counter = 0
        self._idle_throttled = False
        self._cached_colors: list[QColor] = []
        self.protected_widget: QWidget | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._sync_virtual_geometry()

        center = QPointF(self.width() / 2, self.height() / 2)
        self.mouse_pos = center
        self.prev_mouse_pos = center
        self.ring_pos = QPointF(center)
        self.echo_ring_pos = QPointF(center)
        self.ring_radius = 18.0
        self.glow_pos = QPointF(center)
        self.glow_lag_pos = QPointF(center)
        self.pet_pos = QPointF(center)
        self.pet_trail: list[QPointF] = []
        self.pet_angle = 0.0
        self.drag_angle = 0.0
        self.prism_angle = 0.0
        self.prism_pulse = 0.0
        self.hue_phase = 0.0
        self.breath_phase = 0.0
        self.mouse_speed = 0.0
        self.sakura_dist_acc = 0.0
        self.is_dragging = False
        self.was_left_down = False
        self.was_right_down = False
        self.was_mid_down = False

        self.vel_angle = 0.0
        self.stretch_factor = 1.0
        self._yield_timer = 0.0
        self.yield_alpha = 1.0
        self._yield_poll_counter = 0
        self._last_seen_wheel_ts = 0.0
        self._shake_flips: list[float] = []
        self._last_shake_sign = 0
        self._shake_cooldown_until = 0.0

        self.idle_seconds = 0.0
        self.idle_alpha = 1.0
        self.last_tick_time = time.perf_counter()

        self.trail: list[dict] = []
        self.ink_strokes: list[dict] = []
        self.ink_blooms: list[dict] = []
        self.cinnabar_dots: list[dict] = []
        self.sakura_petals: list[dict] = []
        self.water_wake_pts: list[dict] = []
        self.water_waves: list[dict] = []
        self.water_droplets: list[dict] = []
        self.ripples: list[dict] = []
        self.sparks: list[dict] = []
        self.laser_points: list[dict] = []
        self.find_halos: list[dict] = []
        self.nodes: list[dict] = []
        self._init_nodes()

        self.refresh_cursor_icon()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(6)

    def _apply_defaults(self, cfg: dict) -> None:
        style_id = cfg.get("style_id", "spotlight")
        migrated_ribbon = False
        if style_id == "ribbon":
            style_id = "spotlight"
            migrated_ribbon = True
        elif style_id == "astrolabe":
            style_id = "prism"
        self.style_id = style_id if style_id in self.STYLES else "spotlight"

        palette_id = cfg.get("palette_id", "cyber")
        self.palette_id = palette_id if palette_id in self.PALETTES else "cyber"

        custom_cols = cfg.get("custom_colors")
        if isinstance(custom_cols, list) and len(custom_cols) >= 2:
            self.custom_colors = [str(custom_cols[0]), str(custom_cols[1])]
        else:
            self.custom_colors = ["#38bdf8", "#f472b6"]

        self.intensity = max(0.4, min(2.5, float(cfg.get("intensity", 1.0))))
        self.dark_mask_alpha = max(0, min(220, int(cfg.get("dark_mask_alpha", 0))))
        self.current_mask_alpha = float(self.dark_mask_alpha)
        self.exclude_taskbar_mask = bool(cfg.get("exclude_taskbar_mask", True))

        self.enable_ribbon = bool(cfg.get("enable_ribbon", migrated_ribbon))
        self.enable_fireworks = bool(cfg.get("enable_fireworks", True))
        self.enable_pet_orb = bool(cfg.get("enable_pet_orb", False))
        self.enable_flashlight = bool(cfg.get("enable_flashlight", False))
        self.enable_water_wake = bool(cfg.get("enable_water_wake", False))
        self.enable_demo_mode = bool(cfg.get("enable_demo_mode", False))
        self.enable_demo_laser = bool(cfg.get("enable_demo_laser", False))
        self.enable_elastic_motion = bool(cfg.get("enable_elastic_motion", True))
        self.enable_auto_yield = bool(cfg.get("enable_auto_yield", False))
        self.enable_shake_find = bool(cfg.get("enable_shake_find", False))
        self.enable_idle_sleep = bool(cfg.get("enable_idle_sleep", True))
        self.enable_fullscreen_avoid = bool(cfg.get("enable_fullscreen_avoid", True))
        self.enable_process_avoid = bool(cfg.get("enable_process_avoid", False))
        raw_procs = cfg.get("avoid_processes", ["photoshop.exe", "blender.exe", "cs2.exe"])
        if isinstance(raw_procs, list):
            self.avoid_processes = [str(x).strip().lower() for x in raw_procs if str(x).strip()]
        else:
            self.avoid_processes = ["photoshop.exe", "blender.exe", "cs2.exe"]
        self._avoid_proc_set = set(self.avoid_processes)
        self.always_on_top_force = bool(cfg.get("always_on_top_force", True))
        self.enable_custom_cursor = bool(cfg.get("enable_custom_cursor", True))
        if self.enable_auto_yield:
            install_wheel_hook()
        else:
            uninstall_wheel_hook()
        self._rebuild_color_cache()

    def reset_to_defaults(self) -> None:
        self._apply_defaults({})
        self._clear_all_particles()
        self.idle_seconds = 0.0
        self.idle_alpha = 1.0
        apply_windows_topmost(int(self.winId()), self.always_on_top_force)
        self.refresh_cursor_icon()
        self.persist_config()
        self.update()

    def apply_preset(self, preset_id: str) -> None:
        p = self.PRESETS.get(preset_id)
        if not p:
            return
        self.style_id = p["style_id"]
        self.palette_id = p["palette_id"]
        self.intensity = float(p["intensity"])
        self.dark_mask_alpha = int(p["dark_mask_alpha"])
        self.enable_flashlight = bool(p["enable_flashlight"])
        self.enable_ribbon = bool(p["enable_ribbon"])
        self.enable_water_wake = bool(p["enable_water_wake"])
        self.enable_fireworks = bool(p["enable_fireworks"])
        self._clear_all_particles()
        self.idle_seconds = 0.0
        self.idle_alpha = 1.0
        self._rebuild_color_cache()
        self.refresh_cursor_icon()
        self.persist_config()
        self.update()

    def _clear_all_particles(self) -> None:
        self.trail.clear()
        self.ink_strokes.clear()
        self.ink_blooms.clear()
        self.cinnabar_dots.clear()
        self.sakura_petals.clear()
        self.water_wake_pts.clear()
        self.water_waves.clear()
        self.water_droplets.clear()
        self.ripples.clear()
        self.sparks.clear()
        self.laser_points.clear()
        self.find_halos.clear()

    def _sync_virtual_geometry(self) -> None:
        primary = QApplication.primaryScreen()
        if primary:
            self.setGeometry(primary.virtualGeometry())

    def on_screen_changed(self, *_args) -> None:
        self._sync_virtual_geometry()
        self._init_nodes()

    def _get_work_area_region(self) -> QRegion:
        region = QRegion()
        for screen in QApplication.screens():
            avail = screen.availableGeometry()
            top_left = self.mapFromGlobal(avail.topLeft())
            region = region.united(QRegion(QRect(top_left, avail.size())))
        return region

    def showEvent(self, event) -> None:
        super().showEvent(event)
        hwnd = int(self.winId())
        enable_windows_click_through(hwnd)
        apply_windows_topmost(hwnd, self.always_on_top_force)

    def closeEvent(self, event) -> None:
        """被 WM_CLOSE 关闭（任务管理器「结束任务」、taskkill 不带 /F）时按正常退出处理。

        旧版只关掉覆盖层却不退出进程，会留下无界面僵尸进程占用 IPC 端口，
        下次启动还会被误判为“已有实例”而直接退出。
        """
        event.accept()
        instance = QApplication.instance()
        if instance is not None:
            instance.quit()

    def refresh_cursor_icon(self) -> None:
        if self.paused or self.auto_avoiding or not self.enable_custom_cursor:
            restore_system_cursors()
            return
        colors = self.get_colors()
        apply_style_cursor(self.style_id, colors[0], colors[1])

    def persist_config(self) -> None:
        save_config(
            {
                "style_id": self.style_id,
                "palette_id": self.palette_id,
                "custom_colors": self.custom_colors,
                "intensity": round(self.intensity, 2),
                "dark_mask_alpha": self.dark_mask_alpha,
                "exclude_taskbar_mask": self.exclude_taskbar_mask,
                "enable_ribbon": self.enable_ribbon,
                "enable_fireworks": self.enable_fireworks,
                "enable_pet_orb": self.enable_pet_orb,
                "enable_flashlight": self.enable_flashlight,
                "enable_water_wake": self.enable_water_wake,
                "enable_demo_mode": self.enable_demo_mode,
                "enable_demo_laser": self.enable_demo_laser,
                "enable_elastic_motion": self.enable_elastic_motion,
                "enable_auto_yield": self.enable_auto_yield,
                "enable_shake_find": self.enable_shake_find,
                "enable_idle_sleep": self.enable_idle_sleep,
                "enable_fullscreen_avoid": self.enable_fullscreen_avoid,
                "enable_process_avoid": self.enable_process_avoid,
                "avoid_processes": self.avoid_processes,
                "always_on_top_force": self.always_on_top_force,
                "enable_custom_cursor": self.enable_custom_cursor,
            }
        )

    def _init_nodes(self) -> None:
        self.nodes.clear()
        w, h = max(800, self.width()), max(600, self.height())
        area_ratio = max(1.0, (w * h) / (1920 * 1080))
        count = min(280, int(150 * area_ratio))
        for _ in range(count):
            depth = random.uniform(0.55, 1.25)
            self.nodes.append(
                {
                    "x": random.uniform(0, w),
                    "y": random.uniform(0, h),
                    "vx": random.uniform(-0.75, 0.75) * depth,
                    "vy": random.uniform(-0.75, 0.75) * depth,
                    "depth": depth,
                }
            )

    def _rebuild_color_cache(self) -> None:
        if self.palette_id == "custom":
            c0 = QColor(self.custom_colors[0])
            c1 = QColor(self.custom_colors[1])
            self._cached_colors = [
                c0,
                c1,
                blend_color(c0, c1, 0.5),
                blend_color(c1, QColor("#ffffff"), 0.3),
            ]
        elif self.palette_id != "aurora":
            self._cached_colors = [QColor(c) for c in self.PALETTES[self.palette_id]["colors"]]

    def get_colors(self) -> list[QColor]:
        if self.palette_id == "aurora":
            return [
                QColor.fromHsvF((self.hue_phase + i * 0.18) % 1.0, 0.82, 1.0)
                for i in range(4)
            ]
        if not self._cached_colors:
            self._rebuild_color_cache()
        return self._cached_colors

    def set_style(self, style_id: str) -> None:
        if style_id in self.STYLES:
            self.style_id = style_id
            self.ink_strokes.clear()
            self.ink_blooms.clear()
            self.cinnabar_dots.clear()
            self.sakura_petals.clear()
            self.ripples.clear()
            self.idle_seconds = 0.0
            self.idle_alpha = 1.0
            self.refresh_cursor_icon()
            self.persist_config()
            self.update()

    def set_palette(self, palette_id: str) -> None:
        if palette_id in self.PALETTES:
            self.palette_id = palette_id
            self._rebuild_color_cache()
            self.refresh_cursor_icon()
            self.persist_config()
            self.update()

    def set_custom_colors(self, primary_hex: str, secondary_hex: str) -> None:
        self.custom_colors = [primary_hex, secondary_hex]
        self.palette_id = "custom"
        self._rebuild_color_cache()
        self.refresh_cursor_icon()
        self.persist_config()
        self.update()

    def set_intensity(self, value: float) -> None:
        self.intensity = max(0.4, min(2.5, float(value)))
        self.persist_config()
        self.update()

    def set_dark_mask(self, alpha: int) -> None:
        self.dark_mask_alpha = max(0, min(220, int(alpha)))
        self.persist_config()
        self.update()

    def set_exclude_taskbar_mask(self, exclude: bool) -> None:
        self.exclude_taskbar_mask = bool(exclude)
        self.persist_config()
        self.update()

    def set_always_on_top_force(self, enabled: bool) -> None:
        self.always_on_top_force = bool(enabled)
        apply_windows_topmost(int(self.winId()), self.always_on_top_force)
        self.persist_config()

    def set_custom_cursor_enabled(self, enabled: bool) -> None:
        self.enable_custom_cursor = bool(enabled)
        self.refresh_cursor_icon()
        self.persist_config()

    def set_fullscreen_avoid(self, enabled: bool) -> None:
        self.enable_fullscreen_avoid = bool(enabled)
        if not self.enable_fullscreen_avoid and not self.enable_process_avoid and self.auto_avoiding:
            self.auto_avoiding = False
            self.refresh_cursor_icon()
            self.update()
        self.persist_config()

    def set_process_avoid(self, enabled: bool, proc_text: str | None = None) -> None:
        self.enable_process_avoid = bool(enabled)
        if proc_text is not None:
            items = [s.strip().lower() for s in proc_text.replace("，", ",").split(",") if s.strip()]
            self.avoid_processes = items
            self._avoid_proc_set = set(items)
        if not self.enable_fullscreen_avoid and not self.enable_process_avoid and self.auto_avoiding:
            self.auto_avoiding = False
            self.refresh_cursor_icon()
            self.update()
        self.persist_config()

    def _snapshot_config(self) -> dict:
        return {
            "style_id": self.style_id,
            "palette_id": self.palette_id,
            "custom_colors": self.custom_colors,
            "intensity": round(self.intensity, 2),
            "dark_mask_alpha": self.dark_mask_alpha,
            "exclude_taskbar_mask": self.exclude_taskbar_mask,
            "enable_ribbon": self.enable_ribbon,
            "enable_fireworks": self.enable_fireworks,
            "enable_pet_orb": self.enable_pet_orb,
            "enable_flashlight": self.enable_flashlight,
            "enable_water_wake": self.enable_water_wake,
            "enable_demo_mode": self.enable_demo_mode,
            "enable_demo_laser": self.enable_demo_laser,
            "enable_elastic_motion": self.enable_elastic_motion,
            "enable_auto_yield": self.enable_auto_yield,
            "enable_shake_find": self.enable_shake_find,
            "enable_idle_sleep": self.enable_idle_sleep,
            "enable_fullscreen_avoid": self.enable_fullscreen_avoid,
            "enable_process_avoid": self.enable_process_avoid,
            "avoid_processes": self.avoid_processes,
            "always_on_top_force": self.always_on_top_force,
            "enable_custom_cursor": self.enable_custom_cursor,
        }

    def export_config_code(self) -> str:
        raw = json.dumps(self._snapshot_config(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token = base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode("ascii")
        return f"MFX1:{token}"

    def import_config_code(self, text: str) -> bool:
        s = text.strip()
        if not s:
            return False
        try:
            if s.startswith("MFX1:"):
                payload = zlib.decompress(base64.urlsafe_b64decode(s[5:].encode("ascii"))).decode("utf-8")
                data = json.loads(payload)
            else:
                data = json.loads(s)
            if not isinstance(data, dict):
                return False
            self._apply_defaults(data)
            self._clear_all_particles()
            self.idle_seconds = 0.0
            self.idle_alpha = 1.0
            self.yield_alpha = 1.0
            apply_windows_topmost(int(self.winId()), self.always_on_top_force)
            self.refresh_cursor_icon()
            self.persist_config()
            self.update()
            return True
        except Exception:
            return False

    def set_fun_option(self, attr: str, enabled: bool) -> None:
        val = bool(enabled)
        setattr(self, attr, val)
        if attr == "enable_ribbon" and not val:
            self.trail.clear()
        if attr == "enable_pet_orb" and not val:
            self.pet_trail.clear()
        if attr == "enable_water_wake" and not val:
            self.water_wake_pts.clear()
            self.water_waves.clear()
            self.water_droplets.clear()
        if attr == "enable_idle_sleep" and not val:
            self.idle_alpha = 1.0
        elif attr == "enable_auto_yield":
            if val:
                install_wheel_hook()
            else:
                uninstall_wheel_hook()
                self._yield_timer = 0.0
                self.yield_alpha = 1.0
        self.persist_config()
        self.update()

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        if self.paused:
            self._clear_all_particles()
            self.update()
        else:
            self.last_tick_time = time.perf_counter()
        self.refresh_cursor_icon()
        return self.paused

    def _spawn_sakura_petal(self, x: float, y: float, burst: bool = False) -> None:
        scale = math.sqrt(self.intensity)
        if burst:
            ang = random.uniform(0, math.pi * 2)
            spd = random.uniform(1.6, 4.6) * scale
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd - 0.8
        else:
            vx = random.uniform(-1.2, 0.9)
            vy = random.uniform(0.6, 1.9)
        self.sakura_petals.append(
            {
                "x": x + random.uniform(-6, 6),
                "y": y + random.uniform(-6, 6),
                "vx": vx,
                "vy": vy,
                "size": random.uniform(4.5, 8.2) * scale,
                "rot": random.uniform(0, 360),
                "vrot": random.uniform(-2.6, 2.6),
                "flip": random.uniform(0, math.pi * 2),
                "vflip": random.uniform(0.05, 0.12),
                "sway_phase": random.uniform(0, math.pi * 2),
                "alpha": 0.95,
                "color": random.choice(self.SAKURA_COLORS),
            }
        )
        if len(self.sakura_petals) > 160:
            self.sakura_petals.pop(0)

    def _spawn_cinnabar_dots(self, x: float, y: float, count: int) -> None:
        for _ in range(count):
            ang = random.uniform(0, math.pi * 2)
            dist = random.uniform(6.0, 34.0) * math.sqrt(self.intensity)
            self.cinnabar_dots.append(
                {
                    "x": x + math.cos(ang) * dist,
                    "y": y + math.sin(ang) * dist,
                    "r": random.uniform(1.8, 4.0) * math.sqrt(self.intensity),
                    "alpha": random.uniform(0.68, 0.96),
                    "is_gold": random.random() < 0.35,
                }
            )
        if len(self.cinnabar_dots) > 85:
            self.cinnabar_dots = self.cinnabar_dots[-85:]

    def _spawn_click_water_wave(self, x: float, y: float) -> None:
        self.water_waves.append(
            {
                "x": x,
                "y": y,
                "r": 8.0,
                "max_r": 210.0 * self.intensity,
                "alpha": 0.95,
                "aspect": random.uniform(0.86, 0.95),
                "tilt": random.uniform(-12.0, 12.0),
            }
        )
        if len(self.water_waves) > 6:
            self.water_waves.pop(0)

        for _ in range(int(10 * self.intensity)):
            ang = random.uniform(0, math.pi * 2)
            spd = random.uniform(1.5, 4.2) * math.sqrt(self.intensity)
            self.water_droplets.append(
                {
                    "x": x,
                    "y": y,
                    "vx": math.cos(ang) * spd,
                    "vy": math.sin(ang) * spd - 1.1,
                    "r": random.uniform(1.4, 2.8) * math.sqrt(self.intensity),
                    "alpha": 0.92,
                }
            )
        if len(self.water_droplets) > 60:
            self.water_droplets = self.water_droplets[-60:]

    def _spawn_click_fx(self, x: float, y: float, is_right: bool = False) -> None:
        colors = self.get_colors()
        if self.enable_demo_mode:
            c_main = QColor("#f43f5e") if is_right else QColor("#22d3ee")
            c_sub = QColor("#fb7185") if is_right else QColor("#38bdf8")
            max_mul = 1.25
        else:
            c_main = colors[1] if is_right else colors[0]
            c_sub = colors[0] if is_right else colors[1]
            max_mul = 1.0

        self.ripples.append(
            {
                "x": x,
                "y": y,
                "r": 6.0,
                "max_r": 95.0 * self.intensity * max_mul,
                "alpha": 0.94,
                "width": 2.6 if self.enable_demo_mode else 2.2,
                "color": c_main,
            }
        )
        self.ripples.append(
            {
                "x": x,
                "y": y,
                "r": 12.0,
                "max_r": 135.0 * self.intensity * max_mul,
                "alpha": 0.48,
                "width": 1.3,
                "color": c_sub,
            }
        )

        if is_right:
            if self.style_id == "ink":
                self._spawn_cinnabar_dots(x, y, int(5 * self.intensity))
            elif self.style_id == "sakura":
                for _ in range(int(6 * self.intensity)):
                    self._spawn_sakura_petal(x, y, burst=True)
            return

        if self.enable_water_wake:
            self._spawn_click_water_wave(x, y)

        if self.style_id == "ink":
            for _ in range(3):
                self.ink_blooms.append(
                    {
                        "x": x + random.uniform(-8, 8),
                        "y": y + random.uniform(-8, 8),
                        "r": 8.0,
                        "max_r": random.uniform(75.0, 118.0) * self.intensity,
                        "alpha": random.uniform(0.50, 0.78),
                    }
                )
            self._spawn_cinnabar_dots(x, y, int(9 * self.intensity))

        elif self.style_id == "prism":
            self.prism_pulse = 1.0

        elif self.style_id == "sakura":
            for _ in range(int(14 * self.intensity)):
                self._spawn_sakura_petal(x, y, burst=True)

        if self.enable_fireworks:
            count = int(20 * self.intensity)
            scale_sqrt = math.sqrt(self.intensity)
            for _ in range(count):
                ang = random.uniform(0, math.pi * 2)
                spd = random.uniform(3.2, 9.4) * scale_sqrt
                self.sparks.append(
                    {
                        "x": x,
                        "y": y,
                        "px": x,
                        "py": y,
                        "vx": math.cos(ang) * spd,
                        "vy": math.sin(ang) * spd - 1.1,
                        "size": random.uniform(1.6, 3.2) * scale_sqrt,
                        "alpha": 1.0,
                        "decay": random.uniform(0.022, 0.036),
                        "twinkle": random.uniform(0.0, math.pi * 2),
                        "color": random.choice(colors),
                    }
                )

        if self.style_id == "constellation":
            blast_radius = 250.0 * math.sqrt(self.intensity)
            for n in self.nodes:
                dx, dy = n["x"] - x, n["y"] - y
                dist = math.hypot(dx, dy) or 1.0
                if dist < blast_radius:
                    force = (1.0 - dist / blast_radius) * 8.5 * self.intensity
                    n["vx"] += (dx / dist) * force
                    n["vy"] += (dy / dist) * force

    def _has_active_animations(self) -> bool:
        return bool(
            self.ripples
            or self.sparks
            or self.trail
            or self.sakura_petals
            or self.ink_strokes
            or self.ink_blooms
            or self.cinnabar_dots
            or self.water_wake_pts
            or self.water_waves
            or self.water_droplets
            or self.laser_points
            or self.find_halos
            or abs(self.dark_mask_alpha - self.current_mask_alpha) >= 0.4
        )

    def _set_idle_throttle(self, throttled: bool) -> None:
        if throttled != self._idle_throttled:
            self._idle_throttled = throttled
            self.timer.setInterval(16 if throttled else 6)
            if not throttled:
                self.last_tick_time = time.perf_counter()

    def on_tick(self) -> None:
        if self.paused:
            return

        # 仅在前台窗口切换瞬间按需重申置顶/沉底，避免无意义系统消息
        if sys.platform == "win32":
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
            if fg_hwnd and fg_hwnd != self._last_fg_hwnd:
                self._last_fg_hwnd = fg_hwnd
                apply_windows_topmost(int(self.winId()), self.always_on_top_force)

        # 全屏与进程白名单自动避让检测（约每 350ms 检查一次）
        if self.enable_fullscreen_avoid or (self.enable_process_avoid and self._avoid_proc_set):
            self.fullscreen_check_counter += 1
            check_limit = 22 if self._idle_throttled else 60
            if self.fullscreen_check_counter >= check_limit:
                self.fullscreen_check_counter = 0
                ignore = {int(self.winId())}
                if self.protected_widget is not None:
                    ignore.add(int(self.protected_widget.winId()))
                fs = self.enable_fullscreen_avoid and is_foreground_fullscreen(ignore)
                proc_hit = (
                    not fs
                    and self.enable_process_avoid
                    and bool(self._avoid_proc_set)
                    and get_foreground_process_name(ignore) in self._avoid_proc_set
                )
                should_avoid = fs or proc_hit
                if should_avoid != self.auto_avoiding:
                    self.auto_avoiding = should_avoid
                    if should_avoid:
                        self._clear_all_particles()
                    self.refresh_cursor_icon()
                    self.update()
        if self.auto_avoiding:
            self._set_idle_throttle(True)
            return

        # 处于休眠态时，仅以 16ms 极轻量化检测鼠标移动或点击以唤醒，完全跳过计算与重绘
        if self._idle_throttled:
            local_pos = self.mapFromGlobal(QCursor.pos())
            left_down = is_mouse_button_down(0x01)
            right_down = is_mouse_button_down(0x02)
            if (
                abs(local_pos.x() - self.mouse_pos.x()) <= 0.6
                and abs(local_pos.y() - self.mouse_pos.y()) <= 0.6
                and not left_down
                and not right_down
                and not self._has_active_animations()
            ):
                return
            self._set_idle_throttle(False)

        now = time.perf_counter()
        dt_sec = max(0.001, min(0.05, now - self.last_tick_time))
        self.last_tick_time = now
        dt_scale = dt_sec / 0.0166667

        self.hue_phase = (self.hue_phase + 0.0025 * dt_scale) % 1.0
        self.breath_phase = (self.breath_phase + 0.045 * dt_scale) % (math.pi * 2)

        mask_diff = self.dark_mask_alpha - self.current_mask_alpha
        if abs(mask_diff) < 0.4:
            self.current_mask_alpha = float(self.dark_mask_alpha)
        else:
            self.current_mask_alpha += mask_diff * dt_lerp(0.12, dt_scale)

        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        self.prev_mouse_pos = QPointF(self.mouse_pos)
        self.mouse_pos = QPointF(local_pos.x(), local_pos.y())

        left_down = is_mouse_button_down(0x01)
        right_down = is_mouse_button_down(0x02)
        self.is_dragging = left_down
        if left_down:
            self.drag_angle = (self.drag_angle + 3.2 * dt_scale) % 360.0

        if left_down and not self.was_left_down:
            self._spawn_click_fx(self.mouse_pos.x(), self.mouse_pos.y(), is_right=False)
        if right_down and not self.was_right_down:
            self._spawn_click_fx(self.mouse_pos.x(), self.mouse_pos.y(), is_right=True)
        self.was_left_down = left_down
        self.was_right_down = right_down

        dx = self.mouse_pos.x() - self.prev_mouse_pos.x()
        dy = self.mouse_pos.y() - self.prev_mouse_pos.y()
        moved = math.hypot(dx, dy)
        inst_speed = moved / max(0.2, dt_scale)
        self.mouse_speed += (min(48.0, inst_speed) - self.mouse_speed) * dt_lerp(0.22, dt_scale)

        if moved > 0.6 or left_down or right_down:
            self.idle_seconds = 0.0
        else:
            self.idle_seconds += dt_sec

        if self.enable_idle_sleep and self.idle_seconds > 2.6:
            self.idle_alpha = max(0.0, self.idle_alpha - 0.025 * dt_scale)
        else:
            self.idle_alpha = min(1.0, self.idle_alpha + 0.14 * dt_scale)

        # 速度弹性形变（沿运动方向轻微拉伸，停下后回弹）
        if self.enable_elastic_motion and moved > 1.0:
            target_ang = math.degrees(math.atan2(dy, dx))
            ang_diff = (target_ang - self.vel_angle + 180.0) % 360.0 - 180.0
            self.vel_angle += ang_diff * dt_lerp(0.32, dt_scale)
            target_stretch = min(1.38, 1.0 + inst_speed * 0.012)
        else:
            target_stretch = 1.0
        self.stretch_factor += (target_stretch - self.stretch_factor) * dt_lerp(0.24, dt_scale)

        # 滚动 / 打字自动让位
        if self.enable_auto_yield:
            self._yield_poll_counter += 1
            if _last_wheel_event_time > self._last_seen_wheel_ts:
                self._last_seen_wheel_ts = _last_wheel_event_time
                self._yield_timer = 0.85
            elif self._yield_poll_counter >= 3:
                self._yield_poll_counter = 0
                if is_typing_active():
                    self._yield_timer = 0.95
            if self._yield_timer > 0.0:
                self._yield_timer = max(0.0, self._yield_timer - dt_sec)
                self.yield_alpha = max(0.0, self.yield_alpha - 0.16 * dt_scale)
            else:
                self.yield_alpha = min(1.0, self.yield_alpha + 0.10 * dt_scale)
        else:
            self.yield_alpha = 1.0

        # 演示激光尾迹（按住鼠标中键拖动）
        mid_down = is_mouse_button_down(0x04)
        if self.enable_demo_laser and mid_down:
            self.idle_seconds = 0.0
            if moved > 0.8 or not self.was_mid_down:
                self.laser_points.append({"x": self.mouse_pos.x(), "y": self.mouse_pos.y(), "life": 1.0})
                if len(self.laser_points) > 95:
                    self.laser_points.pop(0)
        self.was_mid_down = mid_down
        for lp in self.laser_points:
            lp["life"] -= 0.016 * dt_scale
        self.laser_points = [lp for lp in self.laser_points if lp["life"] > 0.02]

        # 摇一摇定位光圈（短时快速折返触发，带防误触冷却）
        if self.enable_shake_find and now >= self._shake_cooldown_until:
            if abs(dx) >= 14.0:
                sign = 1 if dx > 0 else -1
                if self._last_shake_sign != 0 and sign != self._last_shake_sign:
                    self._shake_flips.append(now)
                    self._shake_flips = [t for t in self._shake_flips if now - t <= 0.45]
                    if len(self._shake_flips) >= 5:
                        self._shake_flips.clear()
                        self._shake_cooldown_until = now + 1.8
                        self.find_halos.append({"x": self.mouse_pos.x(), "y": self.mouse_pos.y(), "r": 16.0, "max_r": 165.0 * math.sqrt(self.intensity), "alpha": 1.0})
                        self.find_halos.append({"x": self.mouse_pos.x(), "y": self.mouse_pos.y(), "r": 8.0, "max_r": 110.0 * math.sqrt(self.intensity), "alpha": 0.9})
                self._last_shake_sign = sign
        for fh in self.find_halos:
            fh["r"] += (fh["max_r"] - fh["r"]) * dt_lerp(0.14, dt_scale)
            fh["alpha"] -= 0.024 * dt_scale
        self.find_halos = [fh for fh in self.find_halos if fh["alpha"] > 0.02]

        if self.enable_ribbon:
            max_len = int(52 * self.intensity)
            if moved > 1.0:
                speed_w = max(0.65, min(1.45, 0.65 + inst_speed / 28.0))
                self.trail.append(
                    {"x": self.mouse_pos.x(), "y": self.mouse_pos.y(), "life": 1.0, "w": speed_w}
                )
                while len(self.trail) > max_len:
                    self.trail.pop(0)
            for pt in self.trail:
                pt["life"] -= 0.022 * dt_scale
            self.trail = [pt for pt in self.trail if pt["life"] > 0.03]

        if self.enable_water_wake:
            if moved > 1.2:
                nx = -dy / moved
                ny = dx / moved
                self.water_wake_pts.append(
                    {
                        "x": self.mouse_pos.x(),
                        "y": self.mouse_pos.y(),
                        "nx": nx,
                        "ny": ny,
                        "life": 1.0,
                        "spread": 5.0 * math.sqrt(self.intensity),
                    }
                )
                if len(self.water_wake_pts) > 68:
                    self.water_wake_pts.pop(0)
            for pt in self.water_wake_pts:
                pt["life"] -= 0.013 * dt_scale
                pt["spread"] += 1.85 * math.sqrt(self.intensity) * dt_scale
            self.water_wake_pts = [pt for pt in self.water_wake_pts if pt["life"] > 0.03]

        for ww in self.water_waves:
            ww["r"] += (ww["max_r"] - ww["r"]) * dt_lerp(0.068, dt_scale)
            ww["alpha"] -= 0.012 * dt_scale
        self.water_waves = [ww for ww in self.water_waves if ww["alpha"] > 0.02]

        for wd in self.water_droplets:
            wd["x"] += wd["vx"] * dt_scale
            wd["y"] += wd["vy"] * dt_scale
            wd["vy"] += 0.12 * dt_scale
            wd["vx"] *= 0.96 ** dt_scale
            wd["alpha"] -= 0.022 * dt_scale
        self.water_droplets = [wd for wd in self.water_droplets if wd["alpha"] > 0.02]

        if self.style_id == "spotlight":
            self.glow_pos.setX(
                self.glow_pos.x() + (self.mouse_pos.x() - self.glow_pos.x()) * dt_lerp(0.24, dt_scale)
            )
            self.glow_pos.setY(
                self.glow_pos.y() + (self.mouse_pos.y() - self.glow_pos.y()) * dt_lerp(0.24, dt_scale)
            )
            self.glow_lag_pos.setX(
                self.glow_lag_pos.x()
                + (self.mouse_pos.x() - self.glow_lag_pos.x()) * dt_lerp(0.10, dt_scale)
            )
            self.glow_lag_pos.setY(
                self.glow_lag_pos.y()
                + (self.mouse_pos.y() - self.glow_lag_pos.y()) * dt_lerp(0.10, dt_scale)
            )

        elif self.style_id == "magnetic":
            self.ring_pos.setX(
                self.ring_pos.x() + (self.mouse_pos.x() - self.ring_pos.x()) * dt_lerp(0.22, dt_scale)
            )
            self.ring_pos.setY(
                self.ring_pos.y() + (self.mouse_pos.y() - self.ring_pos.y()) * dt_lerp(0.22, dt_scale)
            )
            self.echo_ring_pos.setX(
                self.echo_ring_pos.x()
                + (self.mouse_pos.x() - self.echo_ring_pos.x()) * dt_lerp(0.10, dt_scale)
            )
            self.echo_ring_pos.setY(
                self.echo_ring_pos.y()
                + (self.mouse_pos.y() - self.echo_ring_pos.y()) * dt_lerp(0.10, dt_scale)
            )
            drag_offset = -3.0 if left_down else 0.0
            target_r = (17.0 + self.mouse_speed * 0.35 + drag_offset) * math.sqrt(self.intensity)
            self.ring_radius += (target_r - self.ring_radius) * dt_lerp(0.22, dt_scale)

        elif self.style_id == "constellation":
            w, h = self.width(), self.height()
            damping = 0.985 ** dt_scale
            for n in self.nodes:
                n["x"] += n["vx"] * dt_scale
                n["y"] += n["vy"] * dt_scale
                n["vx"] *= damping
                n["vy"] *= damping
                if math.hypot(n["vx"], n["vy"]) < 0.35 * n["depth"]:
                    n["vx"] += random.uniform(-0.05, 0.05) * dt_scale
                    n["vy"] += random.uniform(-0.05, 0.05) * dt_scale
                if n["x"] < 0 or n["x"] > w:
                    n["vx"] *= -1
                if n["y"] < 0 or n["y"] > h:
                    n["vy"] *= -1
                n["x"] = max(0.0, min(float(w), n["x"]))
                n["y"] = max(0.0, min(float(h), n["y"]))

        elif self.style_id == "ink":
            max_len = int(58 * self.intensity)
            if moved > 1.2:
                brush_w = max(0.55, min(2.3, 2.25 - inst_speed / 26.0))
                dry_ratio = max(0.0, min(1.0, (inst_speed - 8.0) / 20.0))
                self.ink_strokes.append(
                    {
                        "x": self.mouse_pos.x(),
                        "y": self.mouse_pos.y(),
                        "life": 1.0,
                        "w": brush_w,
                        "dry": dry_ratio,
                        "jx": random.uniform(-2.8, 2.8),
                        "jy": random.uniform(-2.8, 2.8),
                    }
                )
                while len(self.ink_strokes) > max_len:
                    self.ink_strokes.pop(0)
            for st in self.ink_strokes:
                st["life"] -= 0.018 * dt_scale
            self.ink_strokes = [st for st in self.ink_strokes if st["life"] > 0.03]

            for bm in self.ink_blooms:
                bm["r"] += (bm["max_r"] - bm["r"]) * dt_lerp(0.08, dt_scale)
                bm["alpha"] -= 0.012 * dt_scale
            self.ink_blooms = [bm for bm in self.ink_blooms if bm["alpha"] > 0.02]

            for cd in self.cinnabar_dots:
                cd["alpha"] -= 0.011 * dt_scale
            self.cinnabar_dots = [cd for cd in self.cinnabar_dots if cd["alpha"] > 0.02]

        elif self.style_id == "prism":
            self.ring_pos.setX(
                self.ring_pos.x() + (self.mouse_pos.x() - self.ring_pos.x()) * dt_lerp(0.24, dt_scale)
            )
            self.ring_pos.setY(
                self.ring_pos.y() + (self.mouse_pos.y() - self.ring_pos.y()) * dt_lerp(0.24, dt_scale)
            )
            if moved > 0.5:
                target_ang = math.degrees(math.atan2(dy, dx))
                diff = (target_ang - self.prism_angle + 180.0) % 360.0 - 180.0
                self.prism_angle = (self.prism_angle + diff * dt_lerp(0.18, dt_scale)) % 360.0
            else:
                self.prism_angle = (self.prism_angle + 0.25 * dt_scale) % 360.0
            self.prism_pulse = max(0.0, self.prism_pulse - 0.05 * dt_scale)

        elif self.style_id == "sakura":
            if moved > 0.5:
                self.sakura_dist_acc += moved
                step = max(12.0, 26.0 / self.intensity)
                if self.sakura_dist_acc >= step:
                    self.sakura_dist_acc = 0.0
                    self._spawn_sakura_petal(self.mouse_pos.x(), self.mouse_pos.y(), burst=False)

            for p in self.sakura_petals:
                p["sway_phase"] += 0.05 * dt_scale
                p["x"] += (p["vx"] + math.sin(p["sway_phase"]) * 0.65) * dt_scale
                p["y"] += p["vy"] * dt_scale
                p["vx"] *= 0.99 ** dt_scale
                p["vy"] = min(2.6, p["vy"] + 0.02 * dt_scale)
                p["rot"] = (p["rot"] + p["vrot"] * dt_scale) % 360.0
                p["flip"] += p["vflip"] * dt_scale
                p["alpha"] -= 0.0085 * dt_scale
            self.sakura_petals = [p for p in self.sakura_petals if p["alpha"] > 0.02]

        if self.enable_pet_orb:
            self.pet_angle += 0.065 * dt_scale
            orbit_r = 36.0 * math.sqrt(self.intensity)
            target_x = self.mouse_pos.x() + math.cos(self.pet_angle) * orbit_r
            target_y = self.mouse_pos.y() + math.sin(self.pet_angle * 1.3) * (orbit_r * 0.7)
            self.pet_pos.setX(
                self.pet_pos.x() + (target_x - self.pet_pos.x()) * dt_lerp(0.14, dt_scale)
            )
            self.pet_pos.setY(
                self.pet_pos.y() + (target_y - self.pet_pos.y()) * dt_lerp(0.14, dt_scale)
            )
            if not self.pet_trail or math.hypot(
                self.pet_pos.x() - self.pet_trail[-1].x(),
                self.pet_pos.y() - self.pet_trail[-1].y(),
            ) > 1.5:
                self.pet_trail.append(QPointF(self.pet_pos))
                if len(self.pet_trail) > 20:
                    self.pet_trail.pop(0)

        for rp in self.ripples:
            rp["r"] += (rp["max_r"] - rp["r"]) * dt_lerp(0.14, dt_scale)
            rp["alpha"] -= 0.032 * dt_scale
        self.ripples = [rp for rp in self.ripples if rp["alpha"] > 0.02]

        for sp in self.sparks:
            sp["px"] = sp["x"]
            sp["py"] = sp["y"]
            sp["x"] += sp["vx"] * dt_scale
            sp["y"] += sp["vy"] * dt_scale
            drag = 0.935 ** dt_scale
            sp["vx"] *= drag
            sp["vy"] = sp["vy"] * drag + 0.095 * dt_scale
            sp["twinkle"] += 0.35 * dt_scale
            sp["alpha"] -= sp["decay"] * dt_scale
        self.sparks = [sp for sp in self.sparks if sp["alpha"] > 0.02]

        if self.idle_alpha <= 0.01 and not self._has_active_animations():
            self._set_idle_throttle(True)
            self.update()  # 最后一帧确保完全淡出清屏
            return

        self.update()

    def _draw_realistic_water(self, painter: QPainter, scale: float) -> None:
        if not self.water_wake_pts and not self.water_waves and not self.water_droplets:
            return

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        n_pts = len(self.water_wake_pts)
        if n_pts > 2:
            for layer_ratio, alpha_mul, width_mul in ((1.0, 1.0, 1.0), (0.52, 0.58, 0.68)):
                for side in (-1.0, 1.0):
                    for i in range(1, n_pts - 1):
                        p0 = self.water_wake_pts[i - 1]
                        p1 = self.water_wake_pts[i]
                        p2 = self.water_wake_pts[i + 1]

                        sp0 = p0["spread"] * layer_ratio
                        sp1 = p1["spread"] * layer_ratio
                        sp2 = p2["spread"] * layer_ratio

                        x0 = p0["x"] + p0["nx"] * sp0 * side
                        y0 = p0["y"] + p0["ny"] * sp0 * side
                        x1 = p1["x"] + p1["nx"] * sp1 * side
                        y1 = p1["y"] + p1["ny"] * sp1 * side
                        x2 = p2["x"] + p2["nx"] * sp2 * side
                        y2 = p2["y"] + p2["ny"] * sp2 * side

                        mid1 = QPointF((x0 + x1) * 0.5, (y0 + y1) * 0.5)
                        mid2 = QPointF((x1 + x2) * 0.5, (y1 + y2) * 0.5)
                        path = QPainterPath(mid1)
                        path.quadTo(QPointF(x1, y1), mid2)

                        ratio = i / n_pts
                        a = max(0.0, min(1.0, ratio * p1["life"])) * alpha_mul

                        shadow_c = QColor(4, 24, 44, int(85 * a))
                        painter.setPen(
                            QPen(
                                shadow_c,
                                max(1.2, 5.2 * a * width_mul * scale),
                                Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap,
                            )
                        )
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawPath(path)

                        crest_c = QColor(224, 244, 255, int(185 * a))
                        painter.setPen(
                            QPen(
                                crest_c,
                                max(0.8, 2.2 * a * width_mul * scale),
                                Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap,
                            )
                        )
                        painter.drawPath(path)

            for i in range(1, n_pts - 1):
                p0, p1 = self.water_wake_pts[i - 1], self.water_wake_pts[i]
                a = max(0.0, min(1.0, (i / n_pts) * p1["life"]))
                painter.setPen(
                    QPen(
                        QColor(186, 230, 253, int(65 * a)),
                        max(1.5, 6.5 * a * scale),
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                painter.drawLine(QPointF(p0["x"], p0["y"]), QPointF(p1["x"], p1["y"]))

        for ww in self.water_waves:
            cx, cy, r, a = ww["x"], ww["y"], ww["r"], ww["alpha"]
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(ww["tilt"])
            rx, ry = r, r * ww["aspect"]
            rect = QRectF(-rx, -ry, rx * 2, ry * 2)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    QColor(2, 20, 38, int(125 * a)),
                    3.4 * scale,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawArc(rect, 210 * 16, 130 * 16)

            painter.setPen(
                QPen(
                    QColor(255, 255, 255, int(220 * a)),
                    1.8 * scale,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawArc(rect, 32 * 16, 118 * 16)

            if r > 20.0:
                rx2, ry2 = rx * 0.62, ry * 0.62
                rect2 = QRectF(-rx2, -ry2, rx2 * 2, ry2 * 2)
                painter.setPen(
                    QPen(
                        QColor(224, 242, 254, int(130 * a)),
                        1.1 * scale,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                painter.drawArc(rect2, 38 * 16, 100 * 16)
            painter.restore()

        painter.setPen(Qt.PenStyle.NoPen)
        for wd in self.water_droplets:
            pos = QPointF(wd["x"], wd["y"])
            dg = QRadialGradient(pos, wd["r"] * 1.8)
            dg.setColorAt(0.0, QColor(255, 255, 255, int(240 * wd["alpha"])))
            dg.setColorAt(0.55, QColor(125, 211, 252, int(155 * wd["alpha"])))
            dg.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(dg))
            painter.drawEllipse(pos, wd["r"] * 1.8, wd["r"] * 1.8)

    def paintEvent(self, event) -> None:
        if self.paused or self.auto_avoiding:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = self.get_colors()
        scale = math.sqrt(self.intensity)
        vis = self.idle_alpha * self.yield_alpha

        mask_alpha = int(round(self.current_mask_alpha))
        if mask_alpha > 0:
            clip_region = (
                self._get_work_area_region()
                if self.exclude_taskbar_mask
                else QRegion(self.rect())
            )
            if self.protected_widget is not None and self.protected_widget.isVisible():
                fg = self.protected_widget.frameGeometry()
                tl = self.mapFromGlobal(fg.topLeft())
                clip_region = clip_region.subtracted(QRegion(QRect(tl, fg.size())))
            painter.setClipRegion(clip_region)
            painter.fillRect(self.rect(), QColor(0, 0, 0, mask_alpha))

            if self.enable_flashlight and vis > 0.01:
                hole_r = 195.0 * scale * (0.6 + 0.4 * vis)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                hole_grad = QRadialGradient(self.mouse_pos, hole_r)
                hole_grad.setColorAt(0.0, QColor(0, 0, 0, int(255 * vis)))
                hole_grad.setColorAt(0.55, QColor(0, 0, 0, int(185 * vis)))
                hole_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(hole_grad))
                painter.drawEllipse(self.mouse_pos, hole_r, hole_r)

            if self.enable_water_wake and len(self.water_wake_pts) > 2:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                n_pts = len(self.water_wake_pts)
                for side in (-1.0, 1.0):
                    for i in range(1, n_pts):
                        p0, p1 = self.water_wake_pts[i - 1], self.water_wake_pts[i]
                        a = max(0.0, min(1.0, (i / n_pts) * p1["life"]))
                        painter.setPen(
                            QPen(
                                QColor(0, 0, 0, int(105 * a)),
                                4.5 * scale,
                                Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap,
                            )
                        )
                        painter.drawLine(
                            QPointF(
                                p0["x"] + p0["nx"] * p0["spread"] * side,
                                p0["y"] + p0["ny"] * p0["spread"] * side,
                            ),
                            QPointF(
                                p1["x"] + p1["nx"] * p1["spread"] * side,
                                p1["y"] + p1["ny"] * p1["spread"] * side,
                            ),
                        )

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setClipping(False)

        if self.enable_water_wake:
            self._draw_realistic_water(painter, scale)

        if (
            vis <= 0.01
            and not self.ripples
            and not self.sparks
            and not self.trail
            and not self.sakura_petals
            and not self.ink_strokes
            and not self.ink_blooms
            and not self.cinnabar_dots
            and not self.laser_points
            and not self.find_halos
        ):
            return

        if self.style_id == "ink":
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for bm in self.ink_blooms:
                pos = QPointF(bm["x"], bm["y"])
                bg = QRadialGradient(pos, bm["r"])
                c_core = QColor(41, 37, 36, int(78 * bm["alpha"]))
                c_edge = QColor(28, 25, 23, int(148 * bm["alpha"]))
                c_rim = QColor(214, 211, 209, int(62 * bm["alpha"]))
                bg.setColorAt(0.0, QColor(0, 0, 0, 0))
                bg.setColorAt(0.45, c_core)
                bg.setColorAt(0.82, c_edge)
                bg.setColorAt(0.93, c_rim)
                bg.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(bg))
                painter.drawEllipse(pos, bm["r"], bm["r"])

            if len(self.ink_strokes) > 2:
                n_pts = len(self.ink_strokes)
                for i in range(1, n_pts - 1):
                    p0 = self.ink_strokes[i - 1]
                    p1 = self.ink_strokes[i]
                    p2 = self.ink_strokes[i + 1]
                    mid1 = QPointF((p0["x"] + p1["x"]) * 0.5, (p0["y"] + p1["y"]) * 0.5)
                    mid2 = QPointF((p1["x"] + p2["x"]) * 0.5, (p1["y"] + p2["y"]) * 0.5)
                    path = QPainterPath(mid1)
                    path.quadTo(QPointF(p1["x"], p1["y"]), mid2)

                    ratio = i / n_pts
                    a = max(0.0, min(1.0, ratio * p1["life"])) * vis
                    w_val = p1["w"] * self.intensity
                    dry = p1["dry"]

                    wash_c = QColor(168, 162, 158, int(80 * a))
                    wash_pen = QPen(wash_c, max(2.5, ratio * 13.5 * w_val))
                    wash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(wash_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)

                    ink_c = QColor(24, 24, 27, int(230 * a * (1.0 - 0.35 * dry)))
                    ink_pen = QPen(ink_c, max(1.2, ratio * 7.8 * w_val))
                    ink_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(ink_pen)
                    painter.drawPath(path)

                    if dry > 0.25:
                        ox, oy = p1["jx"] * (1.2 + dry), p1["jy"] * (1.2 + dry)
                        dry_path = QPainterPath(QPointF(mid1.x() + ox, mid1.y() + oy))
                        dry_path.quadTo(
                            QPointF(p1["x"] + ox, p1["y"] + oy),
                            QPointF(mid2.x() + ox, mid2.y() + oy),
                        )
                        dry_c = QColor(39, 39, 42, int(160 * a * dry))
                        dry_pen = QPen(dry_c, max(0.8, 1.6 * self.intensity))
                        dry_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                        painter.setPen(dry_pen)
                        painter.drawPath(dry_path)

            painter.setPen(Qt.PenStyle.NoPen)
            for cd in self.cinnabar_dots:
                col = (
                    QColor(245, 158, 11, int(225 * cd["alpha"]))
                    if cd["is_gold"]
                    else QColor(220, 38, 38, int(220 * cd["alpha"]))
                )
                painter.setBrush(col)
                painter.drawEllipse(QPointF(cd["x"], cd["y"]), cd["r"], cd["r"])

        elif self.style_id == "sakura":
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for p in self.sakura_petals:
                painter.save()
                painter.translate(p["x"], p["y"])
                painter.rotate(p["rot"])
                flip_scale = max(0.22, abs(math.cos(p["flip"])))
                painter.scale(1.0, flip_scale)

                painter.scale(p["size"], p["size"])
                c_fill = QColor(p["color"])
                c_fill.setAlphaF(max(0.0, min(1.0, p["alpha"])))
                c_rim = QColor("#ffffff")
                c_rim.setAlphaF(max(0.0, min(1.0, p["alpha"] * 0.65)))
                rim_pen = QPen(c_rim, 0.8)
                rim_pen.setCosmetic(True)
                painter.setPen(rim_pen)
                painter.setBrush(QBrush(c_fill))
                painter.drawPath(_SAKURA_UNIT_PATH)
                painter.restore()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        elif self.style_id == "prism" and vis > 0.01:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            r = (21.0 + self.mouse_speed * 0.28 + self.prism_pulse * 9.0) * scale

            painter.save()
            painter.translate(self.ring_pos)
            if self.enable_elastic_motion and self.stretch_factor > 1.01:
                painter.rotate(self.vel_angle)
                painter.scale(self.stretch_factor, 1.0 / math.sqrt(self.stretch_factor))
                painter.rotate(-self.vel_angle)

            rim_base = QColor(255, 255, 255, int(38 * vis))
            painter.setPen(QPen(rim_base, 1.0 * scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r, r)

            painter.save()
            painter.rotate(self.prism_angle)
            r_arc = QRectF(-r, -r, r * 2, r * 2)

            cool_c = QColor(colors[0])
            cool_c.setAlphaF(0.68 * vis)
            painter.setPen(QPen(cool_c, 1.8 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(r_arc, 25 * 16, 105 * 16)

            warm_c = QColor(colors[1])
            warm_c.setAlphaF(0.45 * vis)
            painter.setPen(QPen(warm_c, 1.4 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(r_arc, 205 * 16, 85 * 16)

            spec_c = QColor(255, 255, 255, int(215 * vis))
            painter.setPen(QPen(spec_c, 1.2 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(r_arc, 45 * 16, 55 * 16)
            painter.restore()
            painter.restore()

            dot_c = QColor(255, 255, 255, int(225 * vis))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_c)
            painter.drawEllipse(self.mouse_pos, 2.4 * scale, 2.4 * scale)

        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

            if self.style_id == "spotlight" and vis > 0.01:
                breath = 1.0 + 0.05 * math.sin(self.breath_phase)
                outer_r = 250.0 * self.intensity * breath
                outer_grad = QRadialGradient(self.glow_lag_pos, outer_r)
                oc0 = QColor(colors[1])
                oc0.setAlphaF(min(0.32, 0.14 * self.intensity) * vis)
                oc1 = QColor(colors[2])
                oc1.setAlphaF(min(0.16, 0.06 * self.intensity) * vis)
                outer_grad.setColorAt(0.0, oc0)
                outer_grad.setColorAt(0.55, oc1)
                outer_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(outer_grad))
                painter.drawEllipse(self.glow_lag_pos, outer_r, outer_r)

                inner_r = 145.0 * self.intensity
                inner_grad = QRadialGradient(self.glow_pos, inner_r)
                ic0 = QColor("#ffffff")
                ic0.setAlphaF(min(0.28, 0.14 * self.intensity) * vis)
                ic1 = QColor(colors[0])
                ic1.setAlphaF(min(0.55, 0.28 * self.intensity) * vis)
                inner_grad.setColorAt(0.0, ic0)
                inner_grad.setColorAt(0.32, ic1)
                inner_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.setBrush(QBrush(inner_grad))
                painter.drawEllipse(self.glow_pos, inner_r, inner_r)

            elif self.style_id == "constellation" and vis > 0.01:
                mx, my = self.mouse_pos.x(), self.mouse_pos.y()
                max_dist = 190.0 * scale
                node_dist = 105.0 * scale
                for i, n in enumerate(self.nodes):
                    p_node = QPointF(n["x"], n["y"])
                    md = math.hypot(mx - n["x"], my - n["y"])
                    near_mouse = md < max_dist

                    if near_mouse:
                        ratio = 1.0 - md / max_dist
                        grad = QLinearGradient(p_node, self.mouse_pos)
                        c_start = QColor(colors[1])
                        c_start.setAlphaF(ratio * 0.52 * vis)
                        c_end = QColor(colors[0])
                        c_end.setAlphaF(min(1.0, ratio * 0.92) * vis)
                        grad.setColorAt(0.0, c_start)
                        grad.setColorAt(1.0, c_end)
                        painter.setPen(QPen(QBrush(grad), (0.8 + ratio * 1.1) * scale))
                        painter.drawLine(p_node, self.mouse_pos)

                    for m in self.nodes[i + 1 :]:
                        nd = math.hypot(m["x"] - n["x"], m["y"] - n["y"])
                        if nd < node_dist:
                            c2 = QColor(colors[1])
                            c2.setAlphaF(min(1.0, (1.0 - nd / node_dist) * 0.34) * vis)
                            painter.setPen(QPen(c2, 0.85 * scale))
                            painter.drawLine(p_node, QPointF(m["x"], m["y"]))

                    dot_r = 2.0 * n["depth"] * scale
                    if near_mouse:
                        halo_r = dot_r * 3.4
                        halo = QRadialGradient(p_node, halo_r)
                        hc = QColor(colors[0])
                        hc.setAlphaF(0.45 * (1.0 - md / max_dist) * vis)
                        halo.setColorAt(0.0, hc)
                        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(halo))
                        painter.drawEllipse(p_node, halo_r, halo_r)

                    dot_c = QColor(colors[0] if near_mouse else colors[2])
                    dot_c.setAlphaF((0.90 if near_mouse else 0.52) * vis)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(dot_c)
                    painter.drawEllipse(p_node, dot_r, dot_r)

            elif self.style_id == "magnetic" and vis > 0.01:
                echo_r = self.ring_radius * 1.38
                echo_c = QColor(colors[1])
                echo_c.setAlphaF(0.32 * vis)
                painter.setPen(QPen(echo_c, 1.2 * scale))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(self.echo_ring_pos, echo_r, echo_r)

                if self.is_dragging:
                    painter.save()
                    painter.translate(self.ring_pos)
                    painter.rotate(self.drag_angle)
                    dash_pen = QPen(QColor(colors[1]), 2.0 * scale, Qt.PenStyle.DashLine)
                    dash_pen.setDashPattern([6.0, 5.0])
                    painter.setPen(dash_pen)
                    painter.drawEllipse(
                        QPointF(0, 0), self.ring_radius * 1.15, self.ring_radius * 1.15
                    )
                    painter.restore()

                painter.save()
                painter.translate(self.ring_pos)
                if self.enable_elastic_motion and self.stretch_factor > 1.01:
                    painter.rotate(self.vel_angle)
                    painter.scale(self.stretch_factor, 1.0 / math.sqrt(self.stretch_factor))
                    painter.rotate(-self.vel_angle)
                glow_c = QColor(colors[0])
                glow_c.setAlphaF(0.28 * vis)
                painter.setPen(QPen(glow_c, 6.0 * scale))
                painter.drawEllipse(QPointF(0, 0), self.ring_radius, self.ring_radius)

                ring_c = QColor(colors[0])
                ring_c.setAlphaF(0.92 * vis)
                painter.setPen(QPen(ring_c, 1.8 * scale))
                painter.drawEllipse(QPointF(0, 0), self.ring_radius, self.ring_radius)
                painter.restore()

                core_glow = QRadialGradient(self.mouse_pos, 10.0 * scale)
                cg0 = QColor(colors[0])
                cg0.setAlphaF(0.6 * vis)
                core_glow.setColorAt(0.0, cg0)
                core_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(core_glow))
                painter.drawEllipse(self.mouse_pos, 10.0 * scale, 10.0 * scale)

                core_dot = QColor("#ffffff")
                core_dot.setAlphaF(vis)
                painter.setBrush(core_dot)
                painter.drawEllipse(self.mouse_pos, 3.2 * scale, 3.2 * scale)

        if self.enable_ribbon and len(self.trail) > 2:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            n_pts = len(self.trail)
            for i in range(1, n_pts - 1):
                p0 = self.trail[i - 1]
                p1 = self.trail[i]
                p2 = self.trail[i + 1]
                mid1 = QPointF((p0["x"] + p1["x"]) * 0.5, (p0["y"] + p1["y"]) * 0.5)
                mid2 = QPointF((p1["x"] + p2["x"]) * 0.5, (p1["y"] + p2["y"]) * 0.5)

                path = QPainterPath(mid1)
                path.quadTo(QPointF(p1["x"], p1["y"]), mid2)

                ratio = i / n_pts
                alpha_base = max(0.0, min(1.0, ratio * p1["life"])) * vis
                base_col = blend_color(colors[1], colors[0], ratio)
                vel_w = p1.get("w", 1.0)

                # 1. 细腻外层柔光晕
                outer_c = QColor(base_col)
                outer_c.setAlphaF(alpha_base * 0.22)
                outer_pen = QPen(outer_c, max(1.5, ratio * 6.8 * vel_w * self.intensity))
                outer_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(outer_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)

                # 2. 纤细高饱和主丝带
                inner_c = blend_color(base_col, QColor("#ffffff"), ratio * 0.35)
                inner_c.setAlphaF(alpha_base * 0.82)
                inner_pen = QPen(inner_c, max(0.8, ratio * 2.1 * vel_w * self.intensity))
                inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(inner_pen)
                painter.drawPath(path)

                # 3. 极细纯白高光丝芯
                if ratio > 0.35:
                    core_c = QColor(255, 255, 255, int(195 * alpha_base * ratio))
                    core_pen = QPen(core_c, max(0.6, ratio * 0.9 * self.intensity))
                    core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(core_pen)
                    painter.drawPath(path)

        if self.enable_pet_orb and self.pet_trail and vis > 0.01:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for i in range(1, len(self.pet_trail)):
                ratio = i / len(self.pet_trail)
                tc = QColor(colors[1])
                tc.setAlphaF(ratio * 0.55 * vis)
                pen = QPen(tc, ratio * 4.5)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(self.pet_trail[i - 1], self.pet_trail[i])

            orb_glow = QRadialGradient(self.pet_pos, 15.0)
            oc = QColor(colors[0])
            oc.setAlphaF(0.92 * vis)
            ow = QColor("#ffffff")
            ow.setAlphaF(vis)
            orb_glow.setColorAt(0.0, ow)
            orb_glow.setColorAt(0.35, oc)
            orb_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(orb_glow))
            painter.drawEllipse(self.pet_pos, 15.0, 15.0)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for rp in self.ripples:
            rc = QColor(rp["color"])
            rc.setAlphaF(max(0.0, min(1.0, rp["alpha"])))
            painter.setPen(QPen(rc, rp["width"] * scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(rp["x"], rp["y"]), rp["r"], rp["r"])

        for sp in self.sparks:
            a = max(0.0, min(1.0, sp["alpha"]))
            flicker = 0.78 + 0.22 * math.sin(sp["twinkle"]) if a < 0.65 else 1.0
            eff_a = a * flicker
            head = QPointF(sp["x"], sp["y"])
            tail = QPointF(
                sp["x"] - sp["vx"] * 2.2,
                sp["y"] - sp["vy"] * 2.2,
            )
            sz = sp["size"] * (0.45 + 0.55 * a)

            outer_c = QColor(sp["color"])
            outer_c.setAlphaF(eff_a * 0.52)
            painter.setPen(QPen(outer_c, max(1.2, sz * 2.2), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(tail, head)

            core_c = blend_color(QColor(sp["color"]), QColor("#ffffff"), 0.55)
            core_c.setAlphaF(eff_a * 0.92)
            painter.setPen(QPen(core_c, max(0.7, sz * 0.85), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(tail, head)

            tip_c = QColor(255, 255, 255, int(245 * eff_a))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tip_c)
            painter.drawEllipse(head, max(0.8, sz * 0.65), max(0.8, sz * 0.65))

        if len(self.laser_points) > 1:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            n_lp = len(self.laser_points)
            for i in range(1, n_lp):
                p0, p1 = self.laser_points[i - 1], self.laser_points[i]
                a = max(0.0, min(1.0, p1["life"] * (0.35 + 0.65 * (i / n_lp))))
                l_glow = QColor("#f43f5e")
                l_glow.setAlphaF(0.45 * a)
                painter.setPen(QPen(l_glow, 7.5 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(p0["x"], p0["y"]), QPointF(p1["x"], p1["y"]))
                l_core = QColor("#ffffff")
                l_core.setAlphaF(0.95 * a)
                painter.setPen(QPen(l_core, 2.2 * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(p0["x"], p0["y"]), QPointF(p1["x"], p1["y"]))

        for fh in self.find_halos:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            fc = QColor(colors[0])
            fc.setAlphaF(max(0.0, min(1.0, fh["alpha"])))
            painter.setPen(QPen(fc, 3.6 * scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(fh["x"], fh["y"]), fh["r"], fh["r"])


class DropdownPanel(QToolButton):
    """点击弹出的下拉面板：内容放在 QMenu 里，展开时不会撑高控制面板。"""

    def __init__(self, title: str, min_width: int = 360, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.setObjectName("DropdownToggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setText(f"{title}  ▾")

        self.menu = QMenu(self)
        self.menu.setMinimumWidth(min_width)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(12, 10, 12, 10)
        self.content.setSpacing(6)

        holder = QWidgetAction(self.menu)
        holder.setDefaultWidget(self.body)
        self.menu.addAction(holder)
        self.setMenu(self.menu)


class ControlPanel(QWidget):
    """独立可视化控制面板（支持场景预设、连续滑动条、自定义取色与全套设置）。"""

    def __init__(self, overlay: MouseFXOverlay, on_sync_tray) -> None:
        super().__init__()
        self.overlay = overlay
        self.on_sync_tray = on_sync_tray

        self.setWindowTitle("MouseFX 控制面板")
        self.setFixedWidth(420)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(
            """
            QWidget {
                background-color: #111115;
                color: #f4f4f5;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QLabel#SectionTitle {
                color: #a1a1aa;
                font-size: 12px;
                font-weight: bold;
                margin-top: 4px;
            }
            QPushButton#SectionToggle {
                text-align: left;
                border: none;
                background: transparent;
                color: #a1a1aa;
                font-size: 12px;
                font-weight: bold;
                padding: 5px 0px;
            }
            QPushButton#SectionToggle:hover {
                color: #e4e4e7;
            }
            QToolButton#DropdownToggle {
                text-align: left;
                border: 1px solid #2e2e38;
                border-radius: 6px;
                background-color: #1a1a20;
                color: #d4d4d8;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 10px;
            }
            QToolButton#DropdownToggle:hover {
                background-color: #232329;
                border-color: #3f3f4e;
            }
            QMenu {
                background-color: #16161c;
                border: 1px solid #2e2e38;
            }
            QComboBox {
                background-color: #1e1e24;
                border: 1px solid #2e2e38;
                border-radius: 6px;
                padding: 5px 10px;
                color: #f4f4f5;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e24;
                color: #f4f4f5;
                selection-background-color: #0891b2;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #27272f;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #22d3ee;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QCheckBox {
                spacing: 8px;
                padding: 2px 0px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #52525b;
                background-color: #1e1e24;
            }
            QCheckBox::indicator:checked {
                background-color: #06b6d4;
                border-color: #22d3ee;
            }
            QPushButton {
                background-color: #1e1e24;
                border: 1px solid #2e2e38;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f4f4f5;
            }
            QPushButton:hover {
                background-color: #27272f;
                border-color: #3f3f4e;
            }
            QPushButton#DangerBtn {
                background-color: #3b1219;
                border-color: #7f1d1d;
                color: #fecaca;
            }
            QPushButton#DangerBtn:hover {
                background-color: #5b1923;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QLabel("MouseFX 桌面鼠标特效 (240Hz)")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #22d3ee;")
        layout.addWidget(header)

        # 快捷场景预设
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for pid, pinfo in overlay.PRESETS.items():
            btn = QPushButton(pinfo["label"])
            btn.clicked.connect(lambda _c=False, target=pid: self._on_preset_clicked(target))
            preset_row.addWidget(btn)
        layout.addLayout(preset_row)

        grid = QGridLayout()
        grid.setSpacing(8)

        self.style_combo = QComboBox()
        for sid, sname in overlay.STYLES.items():
            self.style_combo.addItem(sname, sid)
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)

        palette_row = QHBoxLayout()
        palette_row.setSpacing(6)
        self.palette_combo = QComboBox()
        for pid, pinfo in overlay.PALETTES.items():
            self.palette_combo.addItem(pinfo["name"], pid)
        self.palette_combo.currentIndexChanged.connect(self._on_palette_changed)

        self.custom_color_btn = QPushButton("自选颜色")
        self.custom_color_btn.setFixedWidth(74)
        self.custom_color_btn.clicked.connect(self._on_pick_custom_colors)
        palette_row.addWidget(self.palette_combo, 1)
        palette_row.addWidget(self.custom_color_btn)

        # 连续滑动条：特效强度 (40 -> 250 表示 0.4x ~ 2.5x)
        int_row = QHBoxLayout()
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(40, 250)
        self.intensity_label = QLabel("1.0x")
        self.intensity_label.setFixedWidth(40)
        self.intensity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.intensity_slider.valueChanged.connect(self._on_intensity_slider)
        int_row.addWidget(self.intensity_slider, 1)
        int_row.addWidget(self.intensity_label)

        # 连续滑动条：黑色蒙版 (0 -> 220)
        mask_row = QHBoxLayout()
        self.mask_slider = QSlider(Qt.Orientation.Horizontal)
        self.mask_slider.setRange(0, 220)
        self.mask_label = QLabel("0%")
        self.mask_label.setFixedWidth(40)
        self.mask_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.mask_slider.valueChanged.connect(self._on_mask_slider)
        mask_row.addWidget(self.mask_slider, 1)
        mask_row.addWidget(self.mask_label)

        grid.addWidget(QLabel("特效风格"), 0, 0)
        grid.addWidget(self.style_combo, 0, 1)
        grid.addWidget(QLabel("配色方案"), 1, 0)
        grid.addLayout(palette_row, 1, 1)
        grid.addWidget(QLabel("特效强度"), 2, 0)
        grid.addLayout(int_row, 2, 1)
        grid.addWidget(QLabel("黑色蒙版"), 3, 0)
        grid.addLayout(mask_row, 3, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self.taskbar_cb = QCheckBox("黑色蒙版不遮挡任务栏")
        self.taskbar_cb.toggled.connect(overlay.set_exclude_taskbar_mask)
        layout.addWidget(self.taskbar_cb)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #27272f;")
        layout.addWidget(line)

        fun_dropdown = DropdownPanel("趣味功能", min_width=380)
        self._fun_dropdown = fun_dropdown
        self._fun_cbs: dict[str, QCheckBox] = {}
        fun_grid = QGridLayout()
        fun_grid.setSpacing(4)
        fun_items = (
            ("丝滑流体拖尾", "enable_ribbon"),
            ("水面激荡波纹", "enable_water_wake"),
            ("点击礼花火花", "enable_fireworks"),
            ("环绕跟宠小光灵", "enable_pet_orb"),
            ("手电筒透光蒙版", "enable_flashlight"),
            ("速度弹性形变", "enable_elastic_motion"),
            ("演示模式（左青右粉）", "enable_demo_mode"),
            ("演示中键激光尾迹", "enable_demo_laser"),
            ("静止 2.6 秒休眠", "enable_idle_sleep"),
            ("滚动/打字自动让位", "enable_auto_yield"),
            ("摇一摇定位光圈", "enable_shake_find"),
        )
        for idx, (title, attr) in enumerate(fun_items):
            cb = QCheckBox(title)
            cb.toggled.connect(lambda checked, a=attr: overlay.set_fun_option(a, checked))
            fun_grid.addWidget(cb, idx // 2, idx % 2)
            self._fun_cbs[attr] = cb
        fun_dropdown.content.addLayout(fun_grid)
        layout.addWidget(fun_dropdown)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("color: #27272f;")
        layout.addWidget(line2)

        behavior_dropdown = DropdownPanel("行为与兼容", min_width=380)
        self._behavior_dropdown = behavior_dropdown

        self.cursor_cb = QCheckBox("随风格切换全套专属鼠标指针图标")
        self.cursor_cb.toggled.connect(overlay.set_custom_cursor_enabled)
        behavior_dropdown.content.addWidget(self.cursor_cb)

        self.fs_avoid_cb = QCheckBox("全屏游戏 / 看视频时自动避让暂停")
        self.fs_avoid_cb.toggled.connect(overlay.set_fullscreen_avoid)
        behavior_dropdown.content.addWidget(self.fs_avoid_cb)

        proc_row = QHBoxLayout()
        proc_row.setSpacing(6)
        self.proc_avoid_cb = QCheckBox("进程避让")
        self.proc_avoid_cb.toggled.connect(self._on_proc_avoid_changed)
        self.proc_edit = QLineEdit()
        self.proc_edit.setPlaceholderText("逗号分隔，如 photoshop.exe, cs2.exe")
        self.proc_edit.setStyleSheet(
            "background-color: #1e1e24; border: 1px solid #2e2e38; border-radius: 5px; padding: 3px 8px; color: #f4f4f5;"
        )
        self.proc_edit.editingFinished.connect(self._on_proc_avoid_changed)
        proc_row.addWidget(self.proc_avoid_cb)
        proc_row.addWidget(self.proc_edit, 1)
        behavior_dropdown.content.addLayout(proc_row)

        self.topmost_cb = QCheckBox("特效覆盖所有窗口（强制置于最顶层）")
        self.topmost_cb.toggled.connect(overlay.set_always_on_top_force)
        behavior_dropdown.content.addWidget(self.topmost_cb)

        self.autostart_cb = QCheckBox("Windows 开机自启")
        self.autostart_cb.toggled.connect(self._on_autostart_toggled)
        behavior_dropdown.content.addWidget(self.autostart_cb)

        layout.addWidget(behavior_dropdown)

        share_label = QLabel("配置分享")
        share_label.setObjectName("SectionTitle")
        layout.addWidget(share_label)

        share_row = QHBoxLayout()
        share_row.setSpacing(6)
        export_btn = QPushButton("导出分享码")
        export_btn.clicked.connect(self._on_export_config)
        import_btn = QPushButton("导入配置")
        import_btn.clicked.connect(self._on_import_config)
        share_row.addWidget(export_btn)
        share_row.addWidget(import_btn)
        layout.addLayout(share_row)

        btn_row = QHBoxLayout()
        self.pause_btn = QPushButton("暂停特效")
        self.pause_btn.clicked.connect(self._on_pause_clicked)

        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._on_reset_clicked)

        hide_btn = QPushButton("隐藏")
        hide_btn.clicked.connect(self.hide)

        quit_btn = QPushButton("退出")
        quit_btn.setObjectName("DangerBtn")
        quit_btn.clicked.connect(self._on_quit_clicked)

        btn_row.addWidget(self.pause_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(hide_btn)
        btn_row.addWidget(quit_btn)
        layout.addLayout(btn_row)

        self.sync_from_overlay()

    def sync_from_overlay(self) -> None:
        for w in (
            self.style_combo,
            self.palette_combo,
            self.intensity_slider,
            self.mask_slider,
            self.taskbar_cb,
            self.cursor_cb,
            self.fs_avoid_cb,
            self.proc_avoid_cb,
            self.proc_edit,
            self.topmost_cb,
            self.autostart_cb,
            *self._fun_cbs.values(),
        ):
            w.blockSignals(True)

        self.style_combo.setCurrentIndex(list(self.overlay.STYLES.keys()).index(self.overlay.style_id))
        self.palette_combo.setCurrentIndex(
            list(self.overlay.PALETTES.keys()).index(self.overlay.palette_id)
        )
        self.intensity_slider.setValue(int(round(self.overlay.intensity * 100)))
        self.intensity_label.setText(f"{self.overlay.intensity:.1f}x")
        self.mask_slider.setValue(int(self.overlay.dark_mask_alpha))
        self.mask_label.setText(f"{int(round(self.overlay.dark_mask_alpha / 255 * 100))}%")
        self.taskbar_cb.setChecked(self.overlay.exclude_taskbar_mask)
        for attr, cb in self._fun_cbs.items():
            cb.setChecked(bool(getattr(self.overlay, attr)))
        self.cursor_cb.setChecked(self.overlay.enable_custom_cursor)
        self.fs_avoid_cb.setChecked(self.overlay.enable_fullscreen_avoid)
        self.proc_avoid_cb.setChecked(self.overlay.enable_process_avoid)
        self.proc_edit.setText(", ".join(self.overlay.avoid_processes))
        self.topmost_cb.setChecked(self.overlay.always_on_top_force)
        self.autostart_cb.setChecked(is_autostart_enabled())
        self.pause_btn.setText("恢复特效" if self.overlay.paused else "暂停特效")

        for w in (
            self.style_combo,
            self.palette_combo,
            self.intensity_slider,
            self.mask_slider,
            self.taskbar_cb,
            self.cursor_cb,
            self.fs_avoid_cb,
            self.proc_avoid_cb,
            self.proc_edit,
            self.topmost_cb,
            self.autostart_cb,
            *self._fun_cbs.values(),
        ):
            w.blockSignals(False)


    def _on_preset_clicked(self, preset_id: str) -> None:
        self.overlay.apply_preset(preset_id)
        self.sync_from_overlay()
        self.on_sync_tray()

    def _on_style_changed(self, idx: int) -> None:
        self.overlay.set_style(self.style_combo.itemData(idx))
        self.on_sync_tray()

    def _on_palette_changed(self, idx: int) -> None:
        self.overlay.set_palette(self.palette_combo.itemData(idx))

    def _on_pick_custom_colors(self) -> None:
        c1 = QColorDialog.getColor(QColor(self.overlay.custom_colors[0]), self, "选择主色调")
        if not c1.isValid():
            return
        c2 = QColorDialog.getColor(QColor(self.overlay.custom_colors[1]), self, "选择辅助色调")
        if not c2.isValid():
            c2 = c1
        self.overlay.set_custom_colors(c1.name(), c2.name())
        self.sync_from_overlay()

    def _on_intensity_slider(self, val: int) -> None:
        f_val = val / 100.0
        self.intensity_label.setText(f"{f_val:.1f}x")
        self.overlay.set_intensity(f_val)

    def _on_mask_slider(self, val: int) -> None:
        self.mask_label.setText(f"{int(round(val / 255 * 100))}%")
        self.overlay.set_dark_mask(val)

    def _on_autostart_toggled(self, checked: bool) -> None:
        actual = set_autostart(checked)
        self.autostart_cb.blockSignals(True)
        self.autostart_cb.setChecked(actual)
        self.autostart_cb.blockSignals(False)

    def _on_pause_clicked(self) -> None:
        paused = self.overlay.toggle_pause()
        self.pause_btn.setText("恢复特效" if paused else "暂停特效")
        self.on_sync_tray()

    def _on_reset_clicked(self) -> None:
        self.overlay.reset_to_defaults()
        self.sync_from_overlay()
        self.on_sync_tray()

    def _on_proc_avoid_changed(self, *_args) -> None:
        self.overlay.set_process_avoid(self.proc_avoid_cb.isChecked(), self.proc_edit.text())

    def _on_export_config(self) -> None:
        code = self.overlay.export_config_code()
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(code)
        QMessageBox.information(self, "导出成功", "当前配置分享码已复制到剪贴板，可直接发给朋友或贴入导入框。")

    def _on_import_config(self) -> None:
        text, ok = QInputDialog.getText(self, "导入配置", "请粘贴 MouseFX 配置分享码 (MFX1:...) 或 JSON：")
        if not ok or not text.strip():
            return
        if self.overlay.import_config_code(text):
            self.sync_from_overlay()
            self.on_sync_tray()
        else:
            QMessageBox.warning(self, "导入失败", "配置格式无效，请检查是否完整复制。")

    def _on_quit_clicked(self) -> None:
        shutdown_and_restore()
        QApplication.instance().quit()

    def show_near_tray(self) -> None:
        self.sync_from_overlay()
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = screen.right() - self.width() - 18
        y = screen.bottom() - self.height() - 18
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


def create_tray_icon() -> QIcon:
    """托盘图标：优先复用 exe 内嵌的应用图标（与文件管理器里看到的一致）。

    打包后从 exe 资源里取；源码运行时读 assets/icon.ico；
    两者都取不到（例如只拷贝了 .py 文件）才退回手绘圆点。
    """
    try:
        if getattr(sys, "frozen", False):
            icon = QIcon(sys.executable)
            if not icon.isNull():
                return icon
        else:
            asset = Path(__file__).resolve().parent / "assets" / "icon.ico"
            if asset.exists():
                icon = QIcon(str(asset))
                if not icon.isNull():
                    return icon
    except Exception:
        pass

    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#22d3ee"))
    p.drawEllipse(4, 4, 24, 24)
    p.setBrush(QColor("#09090b"))
    p.drawEllipse(11, 11, 10, 10)
    p.end()
    return QIcon(pix)


def notify_existing_instance(retries: int = 6, interval: float = 0.15) -> bool:
    """若已有实例在运行，发送唤醒信号并退出当前重复启动。

    带重试：互斥量比 IPC 服务器就绪得早，新实例可能要等对方 listen 完才连得上。
    """
    for _ in range(max(1, retries)):
        sock = QLocalSocket()
        sock.connectToServer(IPC_SERVER_NAME)
        if sock.waitForConnected(300):
            sock.write(b"SHOW")
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return True
        sock.abort()
        time.sleep(interval)
    return False


def main() -> None:
    # 一键还原：`MouseFX.exe --restore` 只还原系统指针后立即退出，不开界面。
    # 用于进程被强杀、指针卡在定制样式时的手动补救。
    # 若已有实例在运行，指针是它有意设置的，这里什么都不做（不能冲掉它）。
    if "--restore" in sys.argv:
        if acquire_single_instance_mutex():
            restore_system_cursors()
            clear_session_lock()
            release_single_instance_mutex()
        return

    # 先抢实例锁再初始化 Qt：互斥量是原子的，把双开窗口压到最小
    owns_instance = acquire_single_instance_mutex()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not owns_instance:
        notify_existing_instance()  # 唤醒已运行实例的控制面板
        sys.exit(0)

    # 上一轮若被强杀，这里先把残留的定制指针还原掉，避免“越攒越乱”
    healed_stale_state = heal_stale_cursor_state()
    write_session_lock()

    atexit.register(shutdown_and_restore)
    app.aboutToQuit.connect(shutdown_and_restore)

    QLocalServer.removeServer(IPC_SERVER_NAME)
    ipc_server = QLocalServer(app)
    ipc_server.listen(IPC_SERVER_NAME)

    overlay = MouseFXOverlay()
    overlay.show()

    tray = QSystemTrayIcon(create_tray_icon(), app)
    tray.setToolTip("MouseFX (左键点击打开控制面板)")

    menu = QMenu()
    keep_refs: list[object] = [ipc_server]
    style_actions: dict[str, tuple[QAction, str]] = {}

    def _sync_tray_labels() -> None:
        for k, (a, title) in style_actions.items():
            a.setText(f"✓  {title}" if k == overlay.style_id else f"    {title}")
        pause_act.setText("✓  暂停特效" if overlay.paused else "    暂停特效")

    panel = ControlPanel(overlay, _sync_tray_labels)
    overlay.protected_widget = panel

    app.screenAdded.connect(overlay.on_screen_changed)
    app.screenRemoved.connect(overlay.on_screen_changed)
    if QApplication.primaryScreen():
        QApplication.primaryScreen().virtualGeometryChanged.connect(overlay.on_screen_changed)

    def _on_ipc_connection() -> None:
        conn = ipc_server.nextPendingConnection()
        if conn:
            conn.close()
        panel.show_near_tray()

    ipc_server.newConnection.connect(_on_ipc_connection)
    keep_refs.append(_on_ipc_connection)

    open_act = QAction("⚙  打开控制面板...", menu)
    open_act.triggered.connect(panel.show_near_tray)
    menu.addAction(open_act)
    menu.addSeparator()

    for sid, sname in overlay.STYLES.items():
        act = QAction(f"✓  {sname}" if sid == overlay.style_id else f"    {sname}", menu)

        def _make_style_handler(target_id: str):
            def _handler():
                overlay.set_style(target_id)
                _sync_tray_labels()
                panel.sync_from_overlay()
            return _handler

        fn = _make_style_handler(sid)
        act.triggered.connect(fn)
        menu.addAction(act)
        style_actions[sid] = (act, sname)
        keep_refs.extend([act, fn])

    menu.addSeparator()

    pause_act = QAction("    暂停特效", menu)

    def _on_pause():
        overlay.toggle_pause()
        _sync_tray_labels()
        panel.sync_from_overlay()

    pause_act.triggered.connect(_on_pause)
    menu.addAction(pause_act)

    quit_act = QAction("    退出", menu)

    def _on_quit():
        shutdown_and_restore()
        app.quit()

    quit_act.triggered.connect(_on_quit)
    menu.addAction(quit_act)

    keep_refs.extend([open_act, pause_act, _on_pause, quit_act, panel])

    def _on_tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if panel.isVisible():
                panel.hide()
            else:
                panel.show_near_tray()

    tray.activated.connect(_on_tray_activated)
    tray.setContextMenu(menu)
    tray.show()

    if healed_stale_state:
        tray.showMessage(
            "MouseFX",
            "上次未正常退出，已自动还原系统指针。",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()