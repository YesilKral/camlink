"""CamLink PC programı.

Çalıştır:   python camlink_pc.py            (pencere ile)
            python camlink_pc.py --no-gui   (sadece konsol)
"""

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camlink_core as core  # noqa: E402

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camlink_config.json")


def run_console(server, cfg, ips):
    print("=" * 56)
    print(" CamLink PC")
    print(" Telefona gir ->  IP  :", " veya ".join(ips))
    print("                  Kod :", cfg["code"])
    print(" Port:", server.port, " | Poz çıkışı: 127.0.0.1:%d" % server.out_addr[1])
    print(" Çıkmak için Ctrl+C")
    print("=" * 56)
    try:
        while True:
            time.sleep(1.0)
            p = server.last_pose
            if server.is_connected() and p:
                print("\r[bağlı %3.0f Hz] x=%+.2f y=%+.2f z=%+.2f  yaw=%+6.1f pitch=%+6.1f roll=%+6.1f  %s   "
                      % (server.rate, p["pos"][0], p["pos"][1], p["pos"][2],
                         p["yaw"], p["pitch"], p["roll"], p["tracking"]), end="")
            elif time.time() - server.bad_code_seen < 3:
                print("\r[!] Telefon bağlanmayı denedi ama KOD yanlış.                         ", end="")
            else:
                print("\r[telefon bekleniyor…]                                                  ", end="")
    except KeyboardInterrupt:
        print()


def run_gui(server, cfg, ips):
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("CamLink PC")
    root.configure(bg="#14161a")
    root.geometry("760x520")

    bg, fg, dim = "#14161a", "#e8eaed", "#8b9098"
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TFrame", background=bg)
    style.configure("TButton", padding=6)

    left = ttk.Frame(root)
    left.pack(side="left", fill="both", expand=True, padx=14, pady=14)
    right = ttk.Frame(root)
    right.pack(side="right", fill="y", padx=(0, 14), pady=14)

    # --- bağlantı bilgisi
    tk.Label(left, text="Telefona gir", bg=bg, fg=dim, font=("Segoe UI", 9)).pack(anchor="w")
    tk.Label(left, text="IP:  " + "   veya   ".join(ips), bg=bg, fg=fg,
             font=("Consolas", 14, "bold")).pack(anchor="w")
    tk.Label(left, text="KOD: " + cfg["code"], bg=bg, fg="#7fd1ff",
             font=("Consolas", 20, "bold")).pack(anchor="w", pady=(0, 6))
    status = tk.Label(left, text="Telefon bekleniyor…", bg=bg, fg="#ff7b72", font=("Segoe UI", 11, "bold"))
    status.pack(anchor="w")
    readout = tk.Label(left, text="", bg=bg, fg=fg, font=("Consolas", 11), justify="left")
    readout.pack(anchor="w", pady=(4, 8))
    game_status = tk.Label(left, text="Oyun kancası: CamLink verisi 127.0.0.1:9051 adresine gönderilir",
                           bg=bg, fg="#d29922",
                           font=("Segoe UI", 10, "bold"), wraplength=420, justify="left")
    game_status.pack(anchor="w", pady=(0, 6))

    canvas = tk.Canvas(left, width=380, height=330, bg="#0d0f12", highlightthickness=0)
    canvas.pack(anchor="w")

    # --- ayarlar
    def add_slider(label, key, lo, hi, fmt):
        ttk.Label(right, text=label).pack(anchor="w", pady=(10, 0))
        var = tk.DoubleVar(value=cfg[key])
        val = ttk.Label(right, text=fmt % cfg[key])

        def on_change(_=None):
            cfg[key] = round(var.get(), 3)
            val.config(text=fmt % cfg[key])

        ttk.Scale(right, from_=lo, to=hi, variable=var, command=on_change, length=210).pack(anchor="w")
        val.pack(anchor="w")

    add_slider("Konum çarpanı (gerçek hareket x ?)", "pos_scale", 0.25, 10.0, "%.2f x")
    add_slider("Yumuşatma", "smooth", 0.0, 1.0, "%.2f")
    add_slider("Joystick hızı (m/s)", "move_speed", 0.5, 12.0, "%.1f")
    add_slider("Yükseklik hızı (m/s)", "height_speed", 0.25, 8.0, "%.1f")

    ttk.Button(right, text="Merkezle (PC'den)", command=server.recenter).pack(anchor="w", pady=(18, 4))

    roll_var = tk.IntVar(value=1 if cfg["roll_sign"] >= 0 else 0)

    def flip_roll():
        cfg["roll_sign"] = 1.0 if roll_var.get() else -1.0

    chk = tk.Checkbutton(right, text="Roll yönü normal", variable=roll_var, command=flip_roll,
                         bg=bg, fg=fg, selectcolor="#2a2f36", activebackground=bg, activeforeground=fg)
    chk.pack(anchor="w", pady=(6, 0))
    tk.Label(right, text="Poz çıkışı:\n127.0.0.1:%d (UDP, JSON)" % server.out_addr[1],
             bg=bg, fg=dim, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(18, 0))

    trail = []
    PPM = 40.0  # piksel / metre
    cx, cy = 190, 190

    def draw():
        canvas.delete("all")
        for gx in range(-4, 5):
            canvas.create_line(cx + gx * PPM, 0, cx + gx * PPM, 330, fill="#1b1f25")
        for gy in range(-4, 5):
            canvas.create_line(0, cy + gy * PPM, 380, cy + gy * PPM, fill="#1b1f25")
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, outline="#3a4048")
        canvas.create_text(8, 8, anchor="nw", fill="#4a5058", text="üstten görünüm (ileri = yukarı)",
                           font=("Segoe UI", 8))
        p = server.last_pose
        if server.is_connected() and p:
            px = cx + p["pos"][0] * PPM
            py = cy - p["pos"][2] * PPM
            trail.append((px, py))
            del trail[:-300]
            if len(trail) > 2:
                canvas.create_line(*[c for pt in trail for c in pt], fill="#2f6f8f")
            th = math.radians(p["yaw"])
            tip = (px + math.sin(th) * 16, py - math.cos(th) * 16)
            l = (px + math.sin(th + 2.5) * 9, py - math.cos(th + 2.5) * 9)
            r = (px + math.sin(th - 2.5) * 9, py - math.cos(th - 2.5) * 9)
            canvas.create_polygon(*tip, *l, *r, fill="#7fd1ff", outline="")
            status.config(text="Bağlı · %.0f Hz · %s" % (server.rate, p["mode"].upper()), fg="#56d364")
            readout.config(text="x %+6.2f  y %+6.2f  z %+6.2f m\nyaw %+7.1f  pitch %+7.1f  roll %+7.1f °\ntakip: %s"
                           % (p["pos"][0], p["pos"][1], p["pos"][2], p["yaw"], p["pitch"], p["roll"],
                              p["tracking"]))
        else:
            if time.time() - server.bad_code_seen < 3:
                status.config(text="Telefon denedi ama KOD yanlış!", fg="#f0883e")
            else:
                status.config(text="Telefon bekleniyor… (aynı Wi-Fi, IP ve kod doğru mu?)", fg="#ff7b72")
        if server.is_connected() and p and p.get("mode") == "free":
            game_status.config(text="FREECAM verisi gönderiliyor · 127.0.0.1:9051",
                               fg="#56d364")
        elif server.is_connected():
            game_status.config(text="Oyuna kamera verisi için telefonda FREECAM seç",
                               fg="#d29922")
        else:
            game_status.config(text="Oyun kancası: CamLink verisi 127.0.0.1:9051 adresine gönderilir",
                               fg="#d29922")
        root.after(33, draw)

    def on_close():
        core.save_config(CONFIG_PATH, cfg)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    draw()
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=core.DEFAULT_PORT)
    ap.add_argument("--out-port", type=int, default=core.DEFAULT_OUT_PORT)
    ap.add_argument("--no-gui", action="store_true")
    ap.add_argument("--new-code", action="store_true", help="yeni eşleşme kodu üret")
    args = ap.parse_args()

    cfg = core.load_config(CONFIG_PATH)
    if args.new_code:
        cfg["code"] = core.make_code()
    core.save_config(CONFIG_PATH, cfg)

    try:
        server = core.Server(cfg, port=args.port, out_port=args.out_port)
    except OSError as e:
        print("Port %d açılamadı (%s). Program zaten açık olabilir." % (args.port, e))
        input("Kapatmak için Enter'a bas…")
        return
    server.start()
    ips = core.local_ips()
    try:
        if args.no_gui:
            run_console(server, cfg, ips)
        else:
            try:
                run_gui(server, cfg, ips)
            except ImportError:
                print("Pencere (tkinter) bulunamadı, konsol moduna geçiliyor.")
                run_console(server, cfg, ips)
    finally:
        core.save_config(CONFIG_PATH, cfg)
        server.stop()


if __name__ == "__main__":
    main()
