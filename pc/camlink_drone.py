"""Map CamLink's six-degree pose stream to FH6's native Drone Mode controls.

FH6 remains responsible for rendering its own free-flying drone camera. This
module presents the phone as a software Xbox controller; no physical pad is
needed and no game DLL hook is used.
"""

import math
import threading
import time


class DroneBridge:
    def __init__(self, server, cfg, max_turn_speed=60.0):
        self.server = server
        self.cfg = cfg
        self.max_move_speed = cfg.get("move_speed", 2.0)
        self.max_height_speed = cfg.get("height_speed", 1.5)
        self.max_turn_speed = max_turn_speed
        self.status = "Drone kontrolü: telefon FREECAM modunu bekliyor"
        self._stop = threading.Event()
        self._thread = None
        self._gamepad = None
        self._vg = None
        self._error = None
        self._prev_pose = None
        self._prev_time = None
        self._last_active = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="CamLinkDrone", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._neutral_and_disconnect()

    @staticmethod
    def _wrap_angle(delta):
        return (delta + 180.0) % 360.0 - 180.0

    @staticmethod
    def _shape(value, deadzone=0.04):
        value = max(-1.0, min(1.0, value))
        a = abs(value)
        if a <= deadzone:
            return 0.0
        return math.copysign((a - deadzone) / (1.0 - deadzone), value)

    @staticmethod
    def _game_is_foreground():
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            size = user32.GetWindowTextLengthW(hwnd)
            if size <= 0:
                return False
            title = ctypes.create_unicode_buffer(size + 1)
            user32.GetWindowTextW(hwnd, title, size + 1)
            return "forza horizon 6" in title.value.lower()
        except Exception:
            return False

    def _connect_gamepad(self):
        if self._gamepad:
            return True
        if self._error:
            return False
        try:
            import vgamepad as vg
            self._vg = vg
            self._gamepad = vg.VX360Gamepad()
            self._gamepad.reset()
            self._gamepad.update()
            return True
        except Exception as exc:
            self._error = str(exc)
            self.status = "Sanal gamepad kullanılamıyor: vgamepad/ViGEmBus gerekli"
            return False

    def _neutral_and_disconnect(self):
        if self._gamepad:
            try:
                self._gamepad.reset()
                self._gamepad.update()
                del self._gamepad
            except Exception:
                pass
            self._gamepad = None
        self._prev_pose = None
        self._prev_time = None
        self._last_active = False

    def _apply_pose(self, pose, now):
        pos = pose.get("pos") or [0.0, 0.0, 0.0]
        yaw = float(pose.get("yaw", 0.0))
        pitch = float(pose.get("pitch", 0.0))
        values = [float(pos[i]) for i in range(3)] + [yaw, pitch]
        if not all(math.isfinite(v) for v in values):
            return

        if self._prev_pose is None or self._prev_time is None:
            self._prev_pose = (values[0], values[1], values[2], yaw, pitch)
            self._prev_time = now
            self._send_axes(0.0, 0.0, 0.0, 0.0, 0.0)
            return

        dt = max(0.008, min(0.10, now - self._prev_time))
        old = self._prev_pose
        vx = (values[0] - old[0]) / dt
        vy = (values[1] - old[1]) / dt
        vz = (values[2] - old[2]) / dt
        yaw_rate = self._wrap_angle(yaw - old[3]) / dt
        pitch_rate = (pitch - old[4]) / dt
        self._prev_pose = (values[0], values[1], values[2], yaw, pitch)
        self._prev_time = now

        lx = self._shape(vx / self.max_move_speed)
        ly = self._shape(vz / self.max_move_speed)
        rx = self._shape(yaw_rate / self.max_turn_speed)
        ry = self._shape(pitch_rate / self.max_turn_speed)
        # FH6 Drone Mode: right trigger climbs; left trigger descends.
        climb = self._shape(vy / self.max_height_speed)
        self._send_axes(lx, ly, rx, ry, climb)

    def _send_axes(self, lx, ly, rx, ry, climb):
        if not self._gamepad:
            return
        self._gamepad.left_joystick_float(x_value_float=lx, y_value_float=ly)
        self._gamepad.right_joystick_float(x_value_float=rx, y_value_float=ry)
        self._gamepad.right_trigger_float(value_float=max(0.0, climb))
        self._gamepad.left_trigger_float(value_float=max(0.0, -climb))
        self._gamepad.update()

    def _run(self):
        while not self._stop.is_set():
            now = time.monotonic()
            self.max_move_speed = max(0.1, float(self.cfg.get("move_speed", 2.0)))
            self.max_height_speed = max(0.1, float(self.cfg.get("height_speed", 1.5)))
            pose = self.server.last_pose
            active = bool(self.server.is_connected() and pose and pose.get("mode") == "free")

            if active and self._game_is_foreground():
                if not self._connect_gamepad():
                    self._stop.wait(0.05)
                    continue
                if not self._last_active:
                    self._prev_pose = None
                    self._prev_time = None
                self._apply_pose(pose, now)
                self.status = "Telefon kontrolü etkin · FH6 Drone Mode açık olmalı"
                self._last_active = True
            else:
                if self._gamepad:
                    self._send_axes(0.0, 0.0, 0.0, 0.0, 0.0)
                self._prev_pose = None
                self._prev_time = None
                self._last_active = False
                if self._error:
                    self.status = "Sanal gamepad kullanılamıyor: vgamepad/ViGEmBus gerekli"
                elif not self.server.is_connected():
                    self.status = "Drone kontrolü: telefon bağlantısı bekleniyor"
                elif pose and pose.get("mode") != "free":
                    self.status = "Drone kontrolü: telefonda FREECAM seç"
                else:
                    self.status = "Hazır · FH6'yı öne alıp Drone Mode'u aç"
            self._stop.wait(1.0 / 60.0)

