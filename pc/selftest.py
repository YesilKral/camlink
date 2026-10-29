"""Telefon olmadan çekirdeği doğrular:  python selftest.py"""

import json
import math
import os
import socket
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camlink_core as core  # noqa: E402

PORT, OUT = 19050, 19051
CODE = "TEST-CODE"


def basis(yaw, pitch, roll=0.0):
    y, p = math.radians(yaw), math.radians(pitch)
    f = (math.sin(y) * math.cos(p), math.sin(p), -math.cos(y) * math.cos(p))
    r0 = (math.cos(y), 0.0, math.sin(y))
    u = core.cross(r0, f)
    if roll:
        # roll: sağa yatış (saat yönü) -> sağ vektör aşağı iner
        r = math.radians(roll)
        right = core.cross(f, u)
        nu = tuple(math.cos(r) * u[i] + math.sin(r) * right[i] for i in range(3))
        u = nu
    return f, u


def pose(pos, yaw, pitch, roll=0.0, mv=(0, 0), h=0, rc=0, n=0):
    f, u = basis(yaw, pitch, roll)
    return {"v": 1, "c": CODE, "k": "pose", "n": n, "p": list(pos), "f": list(f),
            "u": list(u), "mv": list(mv), "h": h, "m": "free", "rc": rc, "tr": "normal"}


class Phone:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(1.0)
        self.n = 0

    def send(self, pkt):
        self.n += 1
        pkt["n"] = self.n
        self.s.sendto(json.dumps(pkt).encode(), ("127.0.0.1", PORT))

    def hold(self, pkt, seconds, hz=60):
        for _ in range(int(seconds * hz)):
            self.send(dict(pkt))
            time.sleep(1.0 / hz)


def main():
    cfg = dict(core.DEFAULTS)
    cfg["code"] = CODE
    srv = core.Server(cfg, port=PORT, out_port=OUT, bind="127.0.0.1")
    srv.start()
    ph = Phone()
    fails = []

    def check(name, ok, info=""):
        print(("  OK    " if ok else "  HATA  ") + name + (" -> " + info if info else ""))
        if not ok:
            fails.append(name)

    def last():
        return srv.last_pose

    # 0) hello yanıtı
    ph.send({"v": 1, "c": CODE, "k": "hello"})
    try:
        reply = ph.s.recvfrom(100)[0]
        check("hello'ya yanıt geliyor", b'"ok"' in reply)
    except socket.timeout:
        check("hello'ya yanıt geliyor", False)

    # 1) yanlış kod yok sayılır
    bad = pose((5, 0, 5), 0, 0)
    bad["c"] = "YANLIS"
    n0 = srv.packets
    ph.send(bad)
    time.sleep(0.1)
    check("yanlış kod reddediliyor", srv.packets == n0)

    # 2) ilk paket sıfır noktası olur (telefon 45 derece bakarken bile)
    ph.hold(pose((1.0, 1.4, 2.0), 45, 0), 0.5)
    p = last()
    check("ilk poz = sıfır noktası", all(abs(v) < 0.01 for v in p["pos"]) and abs(p["yaw"]) < 0.5,
          str(p["pos"]) + " yaw=" + str(p["yaw"]))

    # 3) telefon baktığı yöne 1 m ilerlerse z = +1
    f45 = (math.sin(math.radians(45)), 0, -math.cos(math.radians(45)))
    pos = (1.0 + f45[0], 1.4, 2.0 + f45[2])
    ph.hold(pose(pos, 45, 0), 1.5)
    p = last()
    check("1 m ileri -> z=1", abs(p["pos"][2] - 1.0) < 0.05 and abs(p["pos"][0]) < 0.05, str(p["pos"]))

    # 4) 90 derece sağa dön -> yaw=+90
    ph.hold(pose(pos, 135, 0), 1.5)
    check("90° sağa -> yaw=+90", abs(last()["yaw"] - 90) < 1.0, str(last()["yaw"]))

    # 5) 30 derece yukarı bak -> pitch=+30
    ph.hold(pose(pos, 135, 30), 1.5)
    check("30° yukarı -> pitch=+30", abs(last()["pitch"] - 30) < 1.0, str(last()["pitch"]))

    # 6) yaw ±180 sıçraması
    ph.hold(pose(pos, 45 + 179, 0), 1.0)
    a = last()["yaw"]
    ph.hold(pose(pos, 45 - 179, 0), 1.0)  # = 226 -> -134 gibi sarma
    b = last()["yaw"]
    check("yaw sarması düzgün", abs(wrap_diff(a, b)) < 5.0, "%.1f -> %.1f" % (a, b))

    # 7) merkezle
    ph.hold(pose(pos, 45, 0, rc=1), 1.0)
    p = last()
    check("merkezle sıfırlıyor", all(abs(v) < 0.02 for v in p["pos"]) and abs(p["yaw"]) < 1.0,
          str(p["pos"]) + " yaw=" + str(p["yaw"]))

    # 8) joystick ileri 1 sn -> kamera baktığı yöne gider
    ph.hold(pose(pos, 45, 0, mv=(0, 1.0), rc=1), 1.0)
    p = last()
    expect = cfg["move_speed"] * 1.0
    check("joystick ileri ~%.1f m" % expect, 0.6 * expect < p["pos"][2] < 1.05 * expect, str(p["pos"]))

    # 9) yükseklik kaydırıcısı
    ph.hold(pose(pos, 45, 0, h=1.0, rc=1), 1.0)
    check("yükseklik artıyor", last()["pos"][1] > 0.8, str(last()["pos"]))

    srv.stop()
    print()
    if fails:
        print("BAŞARISIZ:", ", ".join(fails))
        sys.exit(1)
    print("Tüm testler geçti.")


def wrap_diff(a, b):
    return core.wrap180(b - a)


if __name__ == "__main__":
    main()
