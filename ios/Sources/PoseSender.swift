import Foundation
import ARKit
import Network
import simd

/// ARKit ile telefonun konumunu ve duruşunu okur, UDP ile PC'ye yollar.
final class PoseSender: NSObject, ObservableObject, ARSessionDelegate {
    @Published var connected = false
    @Published var statusText = "Hazır"
    @Published var trackingText = "-"
    @Published var rateText = "0 Hz"

    // Arayüzden gelen girdiler (ana kuyrukta yazılır ve okunur)
    var moveX: Float = 0
    var moveY: Float = 0
    var height: Float = 0
    var mode: String = "free"

    private let session = ARSession()
    private var connection: NWConnection?
    private let netQueue = DispatchQueue(label: "camlink.net")
    private var code = ""
    private var seq = 0
    private var recenterCounter = 0
    private var lastReply = Date.distantPast
    private var lastTracking = "-"
    private var framesSinceTick = 0
    private var timer: Timer?
    private var running = false

    // MARK: - Başlat / durdur

    func start(host: String, code: String) {
        stop()
        let cleanHost = host.trimmingCharacters(in: .whitespaces)
        guard !cleanHost.isEmpty, let port = NWEndpoint.Port(rawValue: 9050) else {
            statusText = "IP adresi boş"
            return
        }
        guard ARWorldTrackingConfiguration.isSupported else {
            statusText = "Bu cihazda ARKit desteklenmiyor"
            return
        }
        self.code = code.trimmingCharacters(in: .whitespaces)
        seq = 0
        lastReply = Date.distantPast

        let conn = NWConnection(host: NWEndpoint.Host(cleanHost), port: port, using: .udp)
        conn.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                guard let self = self, self.running else { return }
                switch state {
                case .failed(let error):
                    self.statusText = "Ağ hatası: \(error.localizedDescription)"
                case .waiting(let error):
                    self.statusText = "Bekleniyor: \(error.localizedDescription)"
                default:
                    break
                }
            }
        }
        conn.start(queue: netQueue)
        connection = conn
        running = true
        receiveLoop(conn)

        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        session.delegate = self
        session.run(config, options: [.resetTracking, .removeExistingAnchors])

        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.tick()
        }
        statusText = "Bağlanıyor…"
    }

    func stop() {
        running = false
        timer?.invalidate()
        timer = nil
        session.pause()
        connection?.cancel()
        connection = nil
        connected = false
        statusText = "Durdu"
        rateText = "0 Hz"
    }

    /// PC tarafında "merkezle" işlemini tetikler (sıfır noktası = şu anki konum ve yön).
    func recenter() {
        recenterCounter += 1
    }

    // MARK: - Ağ

    private func receiveLoop(_ conn: NWConnection) {
        conn.receiveMessage { [weak self] data, _, _, error in
            guard let self = self else { return }
            if let data = data, !data.isEmpty,
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               (obj["ok"] as? Int) == 1 {
                DispatchQueue.main.async { self.lastReply = Date() }
            }
            if error == nil {
                self.receiveLoop(conn)
            } else {
                // PC henüz dinlemiyorsa hata gelebilir; biraz sonra tekrar dene.
                self.netQueue.asyncAfter(deadline: .now() + 1.0) {
                    if self.connection === conn { self.receiveLoop(conn) }
                }
            }
        }
    }

    private func send(_ dict: [String: Any]) {
        guard let conn = connection,
              let data = try? JSONSerialization.data(withJSONObject: dict) else { return }
        conn.send(content: data, completion: .contentProcessed({ _ in }))
    }

    private func tick() {
        guard running else { return }
        let alive = Date().timeIntervalSince(lastReply) < 2.0
        connected = alive
        rateText = "\(framesSinceTick * 2) Hz"
        framesSinceTick = 0
        trackingText = lastTracking
        statusText = alive ? "PC'ye bağlı" : "PC'den yanıt yok (IP, kod, güvenlik duvarı?)"
        send(["v": 1, "c": code, "k": "hello"])
    }

    // MARK: - ARKit

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        guard running else { return }
        framesSinceTick += 1
        seq += 1

        let t = frame.camera.transform
        let p = t.columns.3
        // Kamera uzayında bakış yönü -z'dir. Telefon dik (portrait) tutulduğunda
        // ekranın "yukarı" yönü kamera uzayında -x'tir.
        let f = -t.columns.2
        let u = -t.columns.0
        lastTracking = PoseSender.trackingString(frame.camera.trackingState)

        let packet: [String: Any] = [
            "v": 1,
            "c": code,
            "k": "pose",
            "n": seq,
            "p": [p.x, p.y, p.z],
            "f": [f.x, f.y, f.z],
            "u": [u.x, u.y, u.z],
            "mv": [moveX, moveY],
            "h": height,
            "m": mode,
            "rc": recenterCounter,
            "tr": lastTracking
        ]
        send(packet)
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        DispatchQueue.main.async {
            self.statusText = "ARKit hatası: \(error.localizedDescription)"
        }
    }

    static func trackingString(_ state: ARCamera.TrackingState) -> String {
        switch state {
        case .normal:
            return "normal"
        case .notAvailable:
            return "unavailable"
        case .limited(let reason):
            switch reason {
            case .initializing: return "limited:initializing"
            case .excessiveMotion: return "limited:excessive_motion"
            case .insufficientFeatures: return "limited:insufficient_features"
            case .relocalizing: return "limited:relocalizing"
            @unknown default: return "limited"
            }
        }
    }
}
