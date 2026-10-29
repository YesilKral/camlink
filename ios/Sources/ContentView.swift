import SwiftUI
import UIKit

struct ContentView: View {
    @StateObject private var sender = PoseSender()
    @AppStorage("camlink_host") private var host = ""
    @AppStorage("camlink_code") private var code = ""
    @State private var running = false
    @State private var mode = "free"
    @State private var joy: CGSize = .zero
    @State private var heightValue: Double = 0

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if running {
                controlView
            } else {
                setupView
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Bağlantı ekranı

    private var setupView: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("CamLink")
                .font(.system(size: 34, weight: .bold))
            Text("PC programındaki IP adresini ve kodu gir. Telefon ve PC aynı Wi-Fi ağında olmalı.")
                .font(.callout)
                .foregroundColor(.gray)

            VStack(alignment: .leading, spacing: 6) {
                Text("PC IP adresi").font(.caption).foregroundColor(.gray)
                TextField("örn. 192.168.1.10", text: $host)
                    .keyboardType(.numbersAndPunctuation)
                    .autocorrectionDisabled(true)
                    .textInputAutocapitalization(.never)
                    .padding(12)
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(10)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Eşleşme kodu").font(.caption).foregroundColor(.gray)
                TextField("örn. K7P2-9QXM", text: $code)
                    .autocorrectionDisabled(true)
                    .textInputAutocapitalization(.characters)
                    .padding(12)
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(10)
            }

            Button(action: connect) {
                Text("Bağlan")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(14)
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }

            Text(sender.statusText)
                .font(.footnote)
                .foregroundColor(.gray)
            Spacer()
        }
        .padding(24)
    }

    // MARK: - Kontrol ekranı

    private var controlView: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Circle()
                            .fill(sender.connected ? Color.green : Color.red)
                            .frame(width: 10, height: 10)
                        Text(sender.statusText)
                            .font(.footnote.weight(.semibold))
                    }
                    Text("Takip: \(sender.trackingText) · \(sender.rateText)")
                        .font(.caption)
                        .foregroundColor(.gray)
                }
                Spacer()
                Button("Durdur") { disconnect() }
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.white.opacity(0.12))
                    .cornerRadius(8)
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)

            Spacer()

            Text("Telefonu taşıyarak kamerayı hareket ettir.\nKamera merceğini (arka) kapatma.")
                .font(.footnote)
                .multilineTextAlignment(.center)
                .foregroundColor(.gray)
                .padding(.bottom, 16)

            Picker("Mod", selection: $mode) {
                Text("CAR VIEW").tag("car")
                Text("FREECAM").tag("free")
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 60)
            .padding(.bottom, 20)

            HStack(alignment: .bottom) {
                JoystickView(value: $joy, size: 150)
                Spacer()
                Button(action: { sender.recenter() }) {
                    VStack(spacing: 4) {
                        Image(systemName: "scope")
                            .font(.system(size: 26))
                        Text("Merkezle")
                            .font(.caption.weight(.semibold))
                    }
                    .frame(width: 84, height: 84)
                    .background(Color.white.opacity(0.14))
                    .clipShape(Circle())
                }
                .foregroundColor(.white)
                Spacer()
                VStack(spacing: 6) {
                    Text("YÜKSEKLİK").font(.system(size: 9, weight: .semibold)).foregroundColor(.gray)
                    HeightPad(value: $heightValue, height: 170)
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
        .onChange(of: joy) { newValue in
            sender.moveX = Float(newValue.width)
            sender.moveY = Float(-newValue.height)
        }
        .onChange(of: heightValue) { newValue in
            sender.height = Float(newValue)
        }
        .onChange(of: mode) { newValue in
            sender.mode = newValue
        }
    }

    // MARK: - İşlemler

    private func connect() {
        guard !host.trimmingCharacters(in: .whitespaces).isEmpty else {
            sender.statusText = "Önce IP adresini gir"
            return
        }
        sender.mode = mode
        sender.start(host: host, code: code)
        UIApplication.shared.isIdleTimerDisabled = true
        running = true
    }

    private func disconnect() {
        sender.stop()
        UIApplication.shared.isIdleTimerDisabled = false
        running = false
    }
}
