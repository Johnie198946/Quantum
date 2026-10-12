import SwiftUI

/// The caller supplies the real pending request and confirms it through APIClient.
struct QuantumWebLoginModal: View {
    let code: String
    let destination: String
    let confirm: () async throws -> Void
    let close: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var expanded = false
    @State private var phase = Phase.ready
    @State private var error: String?
    @State private var confirmationTask: Task<Void, Never>?

    private enum Phase { case ready, loading, success }
    private var validCode: Bool { code.count == 6 && code.utf8.allSatisfy { (48...57).contains($0) } }

    var body: some View {
        ZStack {
            AppTheme.Colors.scrim.ignoresSafeArea().accessibilityHidden(true)
            VStack(spacing: 24) {
                QuantumAvatarView(size: 44)
                VStack(spacing: 8) {
                    Text("网页登录确认").font(.title3.weight(.semibold))
                    Text(destination).font(.subheadline).foregroundStyle(AppTheme.Colors.textSecondary)
                    Text("仅确认你本人刚发起的登录请求")
                        .font(.footnote).foregroundStyle(AppTheme.Colors.textSecondary)
                }
                ZStack {
                    if phase == .ready {
                        HStack(spacing: 8) {
                            ForEach(Array(code.enumerated()), id: \.offset) { _, digit in
                                Text(String(digit))
                                    .font(.system(size: 28, weight: .semibold, design: .monospaced))
                                    .frame(maxWidth: .infinity, minHeight: 54)
                                    .background(AppTheme.Colors.focusRing, in: RoundedRectangle(cornerRadius: 12))
                            }
                        }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("六位验证码，" + code.map(String.init).joined(separator: "，"))
                        .transition(.scale(scale: 0.01, anchor: .center).combined(with: .opacity))
                    } else if phase == .loading {
                        Text("登录中").font(.headline)
                            .accessibilityLabel("正在验证网页登录")
                        TimelineView(.animation(paused: reduceMotion)) { context in
                            Circle().trim(from: 0, to: 0.76)
                                .stroke(AppTheme.Colors.primary, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                                .rotationEffect(.degrees(reduceMotion ? -90 : -context.date.timeIntervalSinceReferenceDate * 240))
                                .frame(width: 112, height: 112)
                                .accessibilityHidden(true)
                        }
                        .transition(.opacity)
                    } else {
                        Circle().fill(AppTheme.Colors.statusCompleted).frame(width: 88, height: 88)
                        LoginCheckmark().trim(from: 0, to: expanded ? 1 : 0)
                            .stroke(.white, style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
                            .frame(width: 40, height: 32)
                            .accessibilityLabel("网页登录验证成功")
                            .transition(.scale(scale: 0.01, anchor: .center).combined(with: .opacity))
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 128)
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.3), value: phase)
                if let error {
                    Text(error).font(.footnote).foregroundStyle(AppTheme.Colors.statusError)
                        .accessibilityLabel("验证失败，" + error)
                }
                if phase == .ready {
                    Button(error == nil ? "确认登录" : "重新验证", action: startConfirmation)
                        .buttonStyle(.borderedProminent).tint(AppTheme.Colors.primary)
                        .disabled(!validCode)
                        .accessibilityIdentifier("quantum.webLogin.confirm")
                }
                Button(phase == .success ? "关闭" : "取消", action: close)
                    .disabled(phase == .loading)
                    .accessibilityIdentifier("quantum.webLogin.close")
            }
            .foregroundStyle(AppTheme.Colors.textPrimary)
            .padding(28)
            .frame(maxWidth: 360)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 30))
            .overlay(RoundedRectangle(cornerRadius: 30).stroke(.white.opacity(0.3)))
            .padding(20)
            .scaleEffect(expanded || reduceMotion ? 1 : 0.01, anchor: .center)
            .opacity(expanded ? 1 : 0)
        }
        .accessibilityAddTraits(.isModal)
        .onAppear { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.3)) { expanded = true } }
        .onDisappear { confirmationTask?.cancel() }
        .onChange(of: code) { _, _ in
            confirmationTask?.cancel()
            phase = .ready
            error = nil
        }
    }

    private func startConfirmation() {
        guard phase == .ready, validCode else { return }
        error = nil
        phase = .loading
        confirmationTask = Task { @MainActor in
            let started = ContinuousClock.now
            do {
                try await confirm()
                let remaining = Duration.seconds(3) - started.duration(to: .now)
                if remaining > .zero { try await Task.sleep(for: remaining) }
                try Task.checkCancellation()
                phase = .success
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                self.error = error.localizedDescription
                phase = .ready
            }
        }
    }
}

private struct LoginCheckmark: Shape {
    func path(in rect: CGRect) -> Path {
        Path { path in
            path.move(to: CGPoint(x: rect.minX, y: rect.midY))
            path.addLine(to: CGPoint(x: rect.width * 0.38, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        }
    }
}
