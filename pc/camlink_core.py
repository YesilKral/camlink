"""CamLink PC çekirdeği: telefondan gelen UDP paketlerini alır, kamera pozuna çevirir.

Sadece standart kütüphane kullanır (pip kurulumu gerekmez).

Çıkış koordinat sistemi (metre / derece), "merkezle" anındaki telefon konumu ve yönüne göre:
    x = sağ, y = yukarı, z = ileri
    yaw   = sağa dönüş (+), derece
    pitch = yukarı bakış (+), derece
    roll  = saat yönünde yatış (+) (ters gelirse ayarlardan roll_sign = -1 yap)
Bu poz her paketle birlikte 127.0.0.1:OUT_PORT adresine JSON olarak yollanır.
"""

import hmac
import json
import math
import os
import random
import socket
import threading
import time

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DEFAULT_PORT = 9050
DEFAULT_OUT_PORT = 9051

DEFAULTS = {
    "code": "",
    "pos_scale": 1.0,     # telefonun gerçek hareketi x kaç olarak uygulansın
    "move_speed": 2.0,    # joystick hızı (m/s)
    "height_speed": 1.5,  # yükseklik kaydırıcı hızı (m/s)
    "smooth": 0.5,        # 0 = ham, 1 = çok yumuşak
    "roll_sign": 1.0,
    "joy_deadzone": 0.08,
}


def norm_code(text):
    return "".join(ch for ch in str(text).upper() if ch.isalnum())


def make_code():
    raw = "".join(random.SystemRandom().choice(ALPHABET) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def load_config(path):
    cfg = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if not norm_code(cfg.get("code", "")):
        cfg["code"] = make_code()
        save_config(path, cfg)
    return cfg


def save_config(path, cfg):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def local_ips():
    """Bu bilgisayarın yerel ağ IP adreslerini döndürür (telefona girilecek)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # paket gönderilmez, sadece rota seçilir
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["(bulunamadı)"]


# ---------------------------------------------------------------- matematik

def wrap180(a):
    while a > 180.0:
        a -= 360.0
    while a < -180.0:
        a += 360.0
    return a


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def angles_from_basis(f, u, roll_sign=1.0):
    """İleri (f) ve yukarı (u) vektörlerinden yaw/pitch/roll (derece).

    ARKit dünyası: y yukarı, başlangıçta bakış yönü -z. Yaw sağa dönüşte artar.
    """
    yaw = math.degrees(math.atan2(f[0], -f[2]))
    pitch = math.degrees(math.asin(clamp(f[1], -1.0, 1.0)))
    right = cross(f, u)
    roll = roll_sign * math.degrees(math.asin(clamp(right[1], -1.0, 1.0)))
    return yaw, pitch, roll


class OneEuro:
    """Yavaş harekette sarsıntıyı keser, hızlı harekette gecikmesiz kalır."""

    def __init__(self):
        self.x = None
        self.dx = 0.0

    def reset(self):
        self.x = None
        self.dx = 0.0

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, dt, mincutoff, beta, dcutoff=1.0):
        if self.x is None:
            self.x = x
            self.dx = 0.0
            return x
        dx = (x - self.x) / dt
        self.dx += self._alpha(dcutoff, dt) * (dx - self.dx)
        cutoff = mincutoff + beta * abs(self.dx)
        self.x += self._alpha(cutoff, dt) * (x - self.x)
        return self.x


# ---------------------------------------------------------------- kamera

class Rig:
    """Telefon pozunu (ARKit) oyun kamerası pozuna çevirir."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.recenter_flag = True
        self.rc_seen = None
        self.ref_pos = [0.0, 0.0, 0.0]
        self.ref_yaw = 0.0
        self.ref_pitch = 0.0
        self.ref_roll = 0.0
        self.offset = [0.0, 0.0, 0.0]
        self.last_t = None
        self.f_pos = [OneEuro() for _ in range(3)]
        self.f_ang = [OneEuro() for _ in range(3)]
        self.yaw_prev = None
        self.yaw_unwrapped = 0.0

    def request_recenter(self):
        self.recenter_flag = True

    def _reset_filters(self):
        for f in self.f_pos + self.f_ang:
            f.reset()
        self.yaw_prev = None

    def update(self, pkt, now):
        cfg = self.cfg
        p, f, u = pkt["p"], pkt["f"], pkt["u"]
        yaw, pitch, roll = angles_from_basis(f, u, cfg["roll_sign"])

        rc = int(pkt.get("rc", 0))
        if self.rc_seen is None or rc != self.rc_seen:
            self.recenter_flag = True
        self.rc_seen = rc

        if self.recenter_flag:
            self.recenter_flag = False
            self.ref_pos = [p[0], p[1], p[2]]
            self.ref_yaw = yaw
            self.ref_pitch = pitch
            self.ref_roll = roll
            self.offset = [0.0, 0.0, 0.0]
            self._reset_filters()
            self.last_t = None

        dt = 1.0 / 60.0 if self.last_t is None else clamp(now - self.last_t, 0.001, 0.1)
        self.last_t = now

        # Telefonun başlangıç yönüne göre yerel koordinatlar
        psi = math.radians(self.ref_yaw)
        right = (math.cos(psi), 0.0, math.sin(psi))
        fwd = (math.sin(psi), 0.0, -math.cos(psi))
        d = (p[0] - self.ref_pos[0], p[1] - self.ref_pos[1], p[2] - self.ref_pos[2])
        scale = cfg["pos_scale"]
        x = scale * (d[0] * right[0] + d[2] * right[2])
        z = scale * (d[0] * fwd[0] + d[2] * fwd[2])
        y = scale * d[1]
        theta = wrap180(yaw - self.ref_yaw)

        # Ekran joystick'i ve yükseklik: kameranın baktığı yöne göre ilerler
        mv = pkt.get("mv", [0.0, 0.0])
        mx = self._shape(mv[0])
        my = self._shape(mv[1])
        h = self._shape(pkt.get("h", 0.0))
        th = math.radians(theta)
        rx, rz = math.cos(th), -math.sin(th)
        fx, fz = math.sin(th), math.cos(th)
        sp = cfg["move_speed"] * dt
        self.offset[0] += (rx * mx + fx * my) * sp
        self.offset[2] += (rz * mx + fz * my) * sp
        self.offset[1] += h * cfg["height_speed"] * dt

        pos = [x + self.offset[0], y + self.offset[1], z + self.offset[2]]

        # Yaw'ı ±180 sıçramasına karşı açık (unwrapped) tut
        if self.yaw_prev is None:
            self.yaw_unwrapped = theta
        else:
            self.yaw_unwrapped += wrap180(theta - self.yaw_prev)
        self.yaw_prev = theta

        s = clamp(cfg["smooth"], 0.0, 1.0)
        pos_min = 0.4 + 6.0 * (1.0 - s)
        ang_min = 0.6 + 8.0 * (1.0 - s)
        pos_f = [self.f_pos[i](pos[i], dt, pos_min, 8.0) for i in range(3)]
        yaw_f = self.f_ang[0](self.yaw_unwrapped, dt, ang_min, 0.05)
        pitch_f = self.f_ang[1](wrap180(pitch - self.ref_pitch), dt, ang_min, 0.05)
        roll_f = self.f_ang[2](wrap180(roll - self.ref_roll), dt, ang_min, 0.05)

        return {
            "t": now,
            "seq": pkt.get("n", 0),
            "pos": [round(v, 5) for v in pos_f],
            "yaw": round(wrap180(yaw_f), 4),
            "pitch": round(pitch_f, 4),
            "roll": round(roll_f, 4),
            "mode": pkt.get("m", "free"),
            "tracking": pkt.get("tr", "?"),
        }

    def _shape(self, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.0
        dz = self.cfg["joy_deadzone"]
        a = abs(v)
        if a < dz:
            return 0.0
        a = (a - dz) / (1.0 - dz)
        return math.copysign(a ** 1.6, v)  # merkez civarında ince kontrol


# ---------------------------------------------------------------- sunucu

class Server:
    def __init__(self, cfg, port=DEFAULT_PORT, out_port=DEFAULT_OUT_PORT, bind="0.0.0.0"):
        self.cfg = cfg
        self.port = port
        self.out_addr = ("127.0.0.1", out_port)
        self.rig = Rig(cfg)
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind, port))
        self.sock.settimeout(0.5)
        self.out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = False
        self.thread = None
        # Durum (arayüz için)
        self.phone_addr = None
        self.last_seen = 0.0
        self.last_pose = None
        self.bad_code_seen = 0.0
        self.bad_code_addr = None
        self.packets = 0
        self._rate_count = 0
        self._rate_t = time.time()
        self.rate = 0.0

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.5)
        self.sock.close()
        self.out_sock.close()

    def recenter(self):
        with self.lock:
            self.rig.request_recenter()

    def is_connected(self):
        return time.time() - self.last_seen < 2.0

    def _loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                self._update_rate()
                continue
            except OSError:
                break
            self._handle(data, addr)
            self._update_rate()

    def _update_rate(self):
        now = time.time()
        if now - self._rate_t >= 1.0:
            self.rate = self._rate_count / (now - self._rate_t)
            self._rate_count = 0
            self._rate_t = now

    def _handle(self, data, addr):
        try:
            pkt = json.loads(data.decode("utf-8"))
            kind = pkt.get("k")
        except (ValueError, AttributeError, UnicodeDecodeError):
            return
        want = norm_code(self.cfg["code"])
        got = norm_code(pkt.get("c", ""))
        if not hmac.compare_digest(want.encode(), got.encode()):
            self.bad_code_seen = time.time()
            self.bad_code_addr = addr
            return

        now = time.time()
        self.phone_addr = addr
        self.last_seen = now
        if kind == "hello":
            try:
                self.sock.sendto(b'{"ok":1}', addr)
            except OSError:
                pass
            return
        if kind != "pose":
            return
        try:
            with self.lock:
                out = self.rig.update(pkt, now)
        except (KeyError, TypeError, ValueError, IndexError):
            return
        self.packets += 1
        self._rate_count += 1
        self.last_pose = out
        try:
            self.out_sock.sendto(json.dumps(out).encode("utf-8"), self.out_addr)
        except OSError:
            pass
