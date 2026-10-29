import SwiftUI

/// Yön joystick'i. value: x sağ(+), y aşağı(+) olacak şekilde -1...1
struct JoystickView: View {
    @Binding var value: CGSize
    let size: CGFloat
    @State private var drag: CGSize = .zero

    private var travel: CGFloat { size / 2 - size * 0.2 }

    var body: some View {
        ZStack {
            Circle()
                .fill(Color.white.opacity(0.12))
                .frame(width: size, height: size)
            Circle()
                .stroke(Color.white.opacity(0.25), lineWidth: 1)
                .frame(width: size, height: size)
            Circle()
                .fill(Color.white.opacity(0.85))
                .frame(width: size * 0.4, height: size * 0.4)
                .offset(drag)
        }
        .frame(width: size, height: size)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { g in
                    var dx = g.translation.width
                    var dy = g.translation.height
                    let len = (dx * dx + dy * dy).squareRoot()
                    if len > travel {
                        dx = dx / len * travel
                        dy = dy / len * travel
                    }
                    drag = CGSize(width: dx, height: dy)
                    value = CGSize(width: dx / travel, height: dy / travel)
                }
                .onEnded { _ in
                    drag = .zero
                    value = .zero
                }
        )
    }
}

/// Dikey yükseklik kaydırıcısı. Bırakınca ortaya döner. value: yukarı(+) -1...1
struct HeightPad: View {
    @Binding var value: Double
    let height: CGFloat
    @State private var knob: CGFloat = 0

    private var travel: CGFloat { height / 2 - 26 }

    var body: some View {
        ZStack {
            Capsule()
                .fill(Color.white.opacity(0.12))
                .frame(width: 60, height: height)
            VStack {
                Image(systemName: "chevron.up")
                Spacer()
                Image(systemName: "chevron.down")
            }
            .foregroundColor(Color.white.opacity(0.5))
            .padding(.vertical, 10)
            .frame(width: 60, height: height)
            Circle()
                .fill(Color.white.opacity(0.85))
                .frame(width: 46, height: 46)
                .offset(y: knob)
        }
        .frame(width: 60, height: height)
        .contentShape(Capsule())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { g in
                    let y = max(-travel, min(travel, g.translation.height))
                    knob = y
                    value = Double(-y / travel)
                }
                .onEnded { _ in
                    knob = 0
                    value = 0
                }
        )
    }
}
