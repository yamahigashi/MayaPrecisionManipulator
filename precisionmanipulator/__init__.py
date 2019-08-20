# -*- coding: utf-8 -*-
import atexit
import ctypes
from logging import getLogger, WARN, DEBUG, INFO

from ctypes import wintypes
from ctypes import WINFUNCTYPE
from ctypes import c_int
from ctypes import Structure

###############################################################################
# ctypes shortcuts
###############################################################################
logger = getLogger(__name__)
logger.setLevel(WARN)

WH_KEYDOWN = 0x0100
WH_KEYUP = 0x0101
WH_SYSKEYDOWN = 0x0104
WH_SYSKEYUP = 0x0105
WH_KEYBOARD = 2
WH_KEYBOARD_LL = 13

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020e

GetModuleHandleA = ctypes.windll.kernel32.GetModuleHandleA
GetModuleHandleA.restype = wintypes.HMODULE
GetModuleHandleA.argtypes = [wintypes.LPCWSTR]

SetWindowsHookExA = ctypes.windll.user32.SetWindowsHookExA
SetWindowsHookExA.restype = c_int
SetWindowsHookExA.argtypes = [c_int, WINFUNCTYPE(c_int, c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM), wintypes.HINSTANCE, wintypes.DWORD]

SystemParametersInfoA = ctypes.windll.user32.SystemParametersInfoA
SystemParametersInfoA.restype = ctypes.c_bool

CallNextHookEx = ctypes.windll.user32.CallNextHookEx

UnhookWindowsHookEx = ctypes.windll.user32.UnhookWindowsHookEx

GetCurrentProcessId = ctypes.windll.kernel32.GetCurrentProcessId
GetCurrentProcessId.restype = ctypes.c_ulong

GetActiveWindow = ctypes.windll.user32.GetForegroundWindow
GetActiveWindow.restype = ctypes.wintypes.HWND

GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
GetWindowThreadProcessId .restype = ctypes.c_ulong


class POINT(Structure):
    _fields_ = [
        ("x", ctypes.wintypes.DWORD),
        ("y", ctypes.wintypes.DWORD),
    ]


class MSLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.wintypes.DWORD),
    ]


class KYLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.wintypes.ULONG)
    ]


class MouseInfo(ctypes.Structure):
    _fields_ = [("threshold_x", ctypes.c_int),
                ("threshold_y", ctypes.c_int),
                ("acceleration", ctypes.c_int)]


class MouseSpeed(ctypes.Structure):
    _fields_ = [("value", ctypes.c_int)]


PMSLLHOOKSTRUCT = ctypes.POINTER(MSLLHOOKSTRUCT)
PKYLLHOOKSTRUCT = ctypes.POINTER(KYLLHOOKSTRUCT)
LOWLEVELKEYPROC = WINFUNCTYPE(c_int, c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
LOWLEVELMOUSEPROC = WINFUNCTYPE(c_int, c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

###############################################################################
# https://docs.microsoft.com/ja-jp/windows/win32/api/winuser/nf-winuser-systemparametersinfoa
#
# BOOL SystemParametersInfoA(
#   UINT  uiAction,
#   UINT  uiParam,
#   PVOID pvParam,
#   UINT  fWinIni
# );
#
# Retrieves the current mouse speed. The mouse speed determines how far the pointer
# will move based on the distance the mouse moves. The pvParam parameter must point
# to an integer that receives a value which ranges between 1 (slowest) and
# 20 (fastest). A value of 10 is the default. The value can be set by an end-user
# using the mouse control panel application or by an application using SPI_SETMOUSESPEED.
SPI_GETMOUSESPEED = 0x0070

# Sets the current mouse speed. The pvParam parameter is an integer between 1 (slowest)
# and 20 (fastest). A value of 10 is the default. This value is typically set using
# the mouse control panel application.
SPI_SETMOUSESPEED = 0x0071

# Retrieves the two mouse threshold values and the mouse acceleration. The pvParam
# parameter must point to an array of three integers that receives these values.
# See mouse_event for further information.
SPI_GETMOUSE = 0x0003

# Sets the two mouse threshold values and the mouse acceleration. The pvParam
# parameter must point to an array of three integers that specifies these values.
# See mouse_event for further information.
SPI_SETMOUSE = 0x0004
###############################################################################


class _Hook(object):

    is_tool_available = False
    is_shift_down = False
    is_ctrl_down = False

    is_l_button_down = False
    is_m_button_down = False
    is_r_button_down = False

    AFFECTS_CONTEXTS = [
        "manipMoveContext",
        "RotateSuperContext",
        "moveSuperContext",
        "scaleSuperContext",
    ]

    @property
    def is_any_button_pressed(self):
        # type: () -> bool
        return self.is_l_button_down or self.is_m_button_down or self.is_r_button_down

    def __init__(self):
        # type: () -> None

        try:
            import maya.cmds as cmds
            import maya.mel as mel

        except ImportError:
            logger.error("maya not running? precision maniplator cancel hooking.")
            raise

        if not cmds.about(q=True, batch=True):
            self.pid = int(mel.eval("""getpid;"""))
            self.install_maya_tool_changed_hook()
            self.install_proc_hook()
            self.store_speed()

        else:
            logger.warn("maya seems not start with gui, mouse hook does not injected.")

    def __tool_changed_callback__(self):
        # type: () -> None
        """Invoked from maya, set/unset flag by maya's tool context."""
        import maya.mel as mel

        context = mel.eval("currentCtx;")
        if context in self.AFFECTS_CONTEXTS:
            logger.debug("hello")
            self.is_tool_available = True
        else:
            logger.debug("bye")
            self.is_tool_available = False

    def install_maya_tool_changed_hook(self):
        import maya.cmds as cmds

        self.job_handle = cmds.scriptJob(event=("ToolChanged", self.__tool_changed_callback__))
        logger.info("precision maniplator tool changed callback is registered as job id: {}".format(self.job_handle))

    def install_proc_hook(self):

        self.mouse_watchdog = LOWLEVELMOUSEPROC(self.mouse_proc_callback)
        self.mouse_proc_handle = SetWindowsHookExA(
            WH_MOUSE_LL,
            self.mouse_watchdog,
            GetModuleHandleA(None),
            0
        )
        if self.mouse_proc_handle:
            atexit.register(UnhookWindowsHookEx, self.mouse_proc_handle)
            logger.info("successfully hook into mouse events")
        else:
            logger.warn("Can't hook into mouse events - %s" % ctypes.WinError())

        self.key_watchdog = LOWLEVELKEYPROC(self.key_proc_callback)
        self.key_proc_handle = SetWindowsHookExA(
            WH_KEYBOARD_LL,
            self.key_watchdog,
            GetModuleHandleA(None),
            0
        )
        if self.key_proc_handle:
            atexit.register(UnhookWindowsHookEx, self.key_proc_handle)
            logger.info("successfully hook into mouse events")
        else:
            logger.warn("Can't hook into mouse events - %s" % ctypes.WinError())

    def mouse_proc_callback(self, nCode, wparam, lparam):
        # type: (c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM) -> c_int

        try:
            # ms_struct = ctypes.cast(lparam, PMSLLHOOKSTRUCT)
            if int(wparam) < WM_LBUTTONDOWN:
                return CallNextHookEx(self.key_proc_handle, nCode, ctypes.c_int(wparam),  ctypes.c_int(lparam))
            if WM_MBUTTONUP < int(wparam):
                return CallNextHookEx(self.key_proc_handle, nCode, ctypes.c_int(wparam),  ctypes.c_int(lparam))

            prev = self.is_any_button_pressed

            # button pressed
            if int(wparam) == WM_LBUTTONDOWN:
                self.is_l_button_down = True

            elif int(wparam) == WM_MBUTTONDOWN:
                self.is_m_button_down = True

            elif int(wparam) == WM_RBUTTONDOWN:
                self.is_r_button_down = True

            # button released
            if int(wparam) == WM_LBUTTONUP:
                self.is_l_button_down = False

            elif int(wparam) == WM_MBUTTONUP:
                self.is_m_button_down = False

            elif int(wparam) == WM_RBUTTONUP:
                self.is_r_button_down = False

            curr = self.is_any_button_pressed

            if prev != curr:
                self.set_speed()

        except Exception:
            import traceback
            traceback.print_exc()

        finally:
            return CallNextHookEx(self.key_proc_handle, nCode, ctypes.c_int(wparam),  ctypes.c_int(lparam))

        return CallNextHookEx(self.mouse_proc_handle, nCode, c_int(wparam),  c_int(lparam))

    def key_proc_callback(self, nCode, wparam, lparam):
        # type: (c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM) -> c_int

        try:
            changed = False
            if (int(wparam) == WH_KEYDOWN) or (int(wparam) == WH_SYSKEYDOWN):
                ky_struct = ctypes.cast(lparam, PKYLLHOOKSTRUCT)
                if 160 == ky_struct[0].vkCode:
                    changed += not self.is_shift_down
                    self.is_shift_down = True

                elif 162 == ky_struct[0].vkCode:
                    changed += not self.is_ctrl_down
                    self.is_ctrl_down = True

            elif (int(wparam) == WH_KEYUP) or (int(wparam) == WH_SYSKEYUP):
                ky_struct = ctypes.cast(lparam, PKYLLHOOKSTRUCT)
                if 160 == ky_struct[0].vkCode:
                    changed += self.is_shift_down
                    self.is_shift_down = False

                elif 162 == ky_struct[0].vkCode:
                    changed += self.is_ctrl_down
                    self.is_ctrl_down = False

            else:
                ky_struct = ctypes.cast(lparam, PKYLLHOOKSTRUCT)
                alt = 0b00100000
                flags = ky_struct[0].flags
                is_alt_down = ((alt & flags) == alt)

            if self.is_tool_available and changed:
                self.set_speed()

        except Exception:
            import traceback
            traceback.print_exc()

        finally:
            return CallNextHookEx(self.key_proc_handle, nCode, ctypes.c_int(wparam),  ctypes.c_int(lparam))

    def store_speed(self):
        # type: () -> None

        self.mouse_info = MouseInfo()
        SystemParametersInfoA.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.POINTER(MouseInfo), ctypes.c_int)
        SystemParametersInfoA(SPI_GETMOUSE, 0, self.mouse_info, 0)
        self.original_threshold_x = self.mouse_info.threshold_x
        self.original_threshold_y = self.mouse_info.threshold_y
        self.original_is_accel = self.mouse_info.acceleration

        self.speed_info = MouseSpeed()
        SystemParametersInfoA.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.POINTER(MouseSpeed), ctypes.c_int)
        SystemParametersInfoA(SPI_GETMOUSESPEED, 0, self.speed_info, 0)

        self.original_mouse_speed = self.speed_info.value

        logger.info("store original mouse setting: tx {}, ty {}, accel {}, speed {}".format(
            self.original_threshold_x,
            self.original_threshold_y,
            self.original_is_accel,
            self.original_mouse_speed
        ))

    def set_speed(self):
        # type: () -> None
        hwnd = GetActiveWindow()
        active_pid = c_int()
        GetWindowThreadProcessId(hwnd, ctypes.pointer(active_pid))

        if self.pid != active_pid.value:
            self.restore_speed()
            return

        if not self.is_tool_available:
            self.restore_speed()
            return

        logger.debug("L: {}, M: {}, R: {}, SHIFT: {}, CTRL: {}".format(
            self.is_l_button_down,
            self.is_m_button_down,
            self.is_r_button_down,
            self.is_shift_down,
            self.is_ctrl_down
        ))

        if self.is_any_button_pressed and self.is_shift_down and self.is_ctrl_down:
            self._set_speed(0, 0, 0, 1)

        elif self.is_any_button_pressed and self.is_shift_down:
            self._set_speed(0, 0, 1, 1)

        elif self.is_any_button_pressed and self.is_ctrl_down:
            self._set_speed(0, 0, 0, self.original_mouse_speed / 2)

        else:
            self.restore_speed()

    def _set_speed(self, tx, ty, accel, speed):
        # type: (int, int, int, int) -> None

        self.mouse_info.threshold_x = ctypes.c_int(tx)
        self.mouse_info.threshold_y = ctypes.c_int(ty)
        self.mouse_info.acceleration = ctypes.c_int(accel)

        ctypes.windll.user32.SystemParametersInfoA.restype = ctypes.c_bool
        ctypes.windll.user32.SystemParametersInfoA.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.POINTER(MouseInfo), ctypes.c_int)
        ctypes.windll.user32.SystemParametersInfoA(SPI_SETMOUSE, 0, self.mouse_info, 0)

        ctypes.windll.user32.SystemParametersInfoA.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.POINTER(MouseSpeed), ctypes.c_int)
        ctypes.windll.user32.SystemParametersInfoA.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
        ctypes.windll.user32.SystemParametersInfoA(SPI_SETMOUSESPEED, 0, ctypes.c_int(speed), 0)

    def restore_speed(self):
        # type: () -> None
        self._set_speed(
            self.original_threshold_x,
            self.original_threshold_y,
            self.original_is_accel,
            self.original_mouse_speed
        )

        logger.info("restore original mouse setting: tx {}, ty {}, accel {}, speed {}".format(
            self.original_threshold_x,
            self.original_threshold_y,
            self.original_is_accel,
            self.original_mouse_speed
        ))

    def remove(self):
        # type: () -> None

        try:
            import maya.cmds as cmds
            if self.job_handle and cmds.scriptJob(exists=self.job_handle):
                cmds.scriptJob(kill=self.job_handle)
        except ImportError:
            if self.job_handle:
                logger.warn("import maya error, could not kill script job: {}.".format(self.job_handle))

        if self.mouse_proc_handle:
            self.restore_speed()
            UnhookWindowsHookEx(self.mouse_proc_handle)

        if self.key_proc_handle:
            self.restore_speed()
            UnhookWindowsHookEx(self.key_proc_handle)


__hook = None


def hook():
    # type: () -> _Hook
    global __hook
    __hook = _Hook()

    return __hook


def set_debug():
    # type: () -> None
    logger.setLevel(DEBUG)


def set_info():
    # type: () -> None
    logger.setLevel(INFO)


if __name__ == '__main__':

    import precisionmanipulator as pm
    # pm.hook()
    print(pm.__hook.is_shift_down)
    print(pm.__hook.is_ctrl_down)
    # logger.setLevel(DEBUG)
