//
//  OnboardingView.swift
//  Organizer
//
//  Created by Carlos Aguilar
//
//  First-launch experience redesigned to feel like modern AI app
//  onboarding (Claude / ChatGPT style):
//  - Steps slide horizontally like a guided flow
//  - Staggered fade-in animations on every screen
//  - Progress dots so the user knows where they are
//  - Animated waving hand, pulsing icon accents
//
//  Apple does not allow apps to auto-execute Terminal commands —
//  we show each command with a Copy button instead (Docker Desktop pattern).

import SwiftUI

// ── Custom button style ───────────────────────────────────────────────────────
// .borderedProminent relies on system vibrancy materials that don't always
// render inside MenuBarExtra windows — this draws its own background/text
// so it always renders correctly.
struct PrimaryButtonStyle: ButtonStyle {
    var disabled: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(disabled ? Color.white.opacity(0.5) : Color.white)
            .frame(minWidth: 140, minHeight: 20)
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(
                disabled
                    ? AnyShapeStyle(Color.gray.opacity(0.4))
                    : AnyShapeStyle(
                        LinearGradient(
                            colors: [
                                Color.orange,
                                Color.orange.opacity(configuration.isPressed ? 0.7 : 0.85)
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            )
            .cornerRadius(10)
            .contentShape(Rectangle())
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

extension View {
    func primaryButton(disabled: Bool = false) -> some View {
        self.buttonStyle(PrimaryButtonStyle(disabled: disabled))
    }
}

enum OnboardingStep: Int, CaseIterable {
    case askName     = 0
    case welcome     = 1
    case setupOllama = 2
    case ready       = 3
}

struct OnboardingView: View {
    @Binding var userName: String
    @Binding var isOnboardingComplete: Bool

    @State private var step: OnboardingStep = .askName
    @State private var nameInput        = ""
    @State private var isCheckingHealth = false
    @State private var ollamaReady      = false
    @State private var copiedCommand    = false
    @State private var statusDetail     = "Waiting for Ollama…"

    // auto-retry every 3s until connected
    private let healthTimer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()
    @FocusState private var nameFieldFocused: Bool

    // staggered entrance animation trigger — reset on each step change
    @State private var appear = false

    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            // subtle warm glow at the top — welcoming without being loud
            RadialGradient(
                colors: [Color.orange.opacity(0.10), .clear],
                center: .top,
                startRadius: 10,
                endRadius: 380
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Group {
                    switch step {
                    case .askName:     askNameView
                    case .welcome:     welcomeView
                    case .setupOllama: setupOllamaView
                    case .ready:       readyView
                    }
                }
                .transition(.asymmetric(
                    insertion: .move(edge: .trailing).combined(with: .opacity),
                    removal:   .move(edge: .leading).combined(with: .opacity)
                ))

                progressDots
                    .padding(.bottom, 22)
            }
        }
        .frame(width: 480, height: 680)
        .animation(.spring(response: 0.45, dampingFraction: 0.85), value: step)
        .onChange(of: step) { _, _ in
            // restart the staggered entrance animation on every step
            appear = false
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                withAnimation { appear = true }
            }
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                withAnimation { appear = true }
            }
        }
    }

    // ── Progress dots ─────────────────────────────────────────────────────────
    private var progressDots: some View {
        HStack(spacing: 8) {
            ForEach(OnboardingStep.allCases, id: \.rawValue) { s in
                Capsule()
                    .fill(s == step ? Color.orange : Color.secondary.opacity(0.25))
                    .frame(width: s == step ? 22 : 7, height: 7)
                    .animation(.spring(response: 0.35, dampingFraction: 0.8), value: step)
            }
        }
    }

    // ── Reusable staggered entrance modifier ─────────────────────────────────
    private func entrance(_ order: Double) -> some ViewModifier {
        EntranceModifier(visible: appear, delay: order * 0.09)
    }


    // ── Step 1 — Ask for name ────────────────────────────────────────────────
    private var askNameView: some View {
        VStack(spacing: 22) {
            Spacer()

            ZStack {
                Circle()
                    .fill(Color.orange.opacity(0.12))
                    .frame(width: 92, height: 92)
                Image(systemName: "folder.badge.gearshape")
                    .font(.system(size: 42))
                    .foregroundStyle(.orange)
            }
            .modifier(entrance(0))

            VStack(spacing: 8) {
                Text("Welcome to Organizer")
                    .font(.system(size: 24, weight: .bold))

                Text("Your desktop, tidied with a sentence.")
                    .font(.system(size: 13.5))
                    .foregroundStyle(.secondary)
            }
            .modifier(entrance(1))

            VStack(spacing: 14) {
                Text("What should I call you?")
                    .font(.system(size: 13))
                    .foregroundStyle(.secondary)

                TextField("Your name", text: $nameInput)
                    .textFieldStyle(.plain)
                    .font(.system(size: 16))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 11)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .cornerRadius(12)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(
                                nameFieldFocused ? Color.orange.opacity(0.5)
                                                 : Color.primary.opacity(0.08),
                                lineWidth: 1
                            )
                    )
                    .frame(width: 250)
                    .focused($nameFieldFocused)
                    .onSubmit { proceedFromName() }
            }
            .modifier(entrance(2))

            Button("Continue") {
                proceedFromName()
            }
            .primaryButton(disabled: nameInput.trimmingCharacters(in: .whitespaces).isEmpty)
            .disabled(nameInput.trimmingCharacters(in: .whitespaces).isEmpty)
            .modifier(entrance(3))

            Spacer()
            Spacer()
        }
        .padding(32)
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                nameFieldFocused = true
            }
        }
    }

    private func proceedFromName() {
        let trimmed = nameInput.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        userName = trimmed
        DispatchQueue.main.async {
            withAnimation { step = .welcome }
        }
    }


    // ── Step 2 — Welcome with name ───────────────────────────────────────────
    private var welcomeView: some View {
        VStack(spacing: 22) {
            Spacer()

            WavingHand()
                .modifier(entrance(0))

            VStack(spacing: 10) {
                Text("Welcome, \(userName.isEmpty ? nameInput : userName)!")
                    .font(.system(size: 24, weight: .bold))

                Text("Before we start, we need to set up the\nAI that runs on your Mac.")
                    .font(.system(size: 13.5))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
            }
            .modifier(entrance(1))

            HStack(spacing: 8) {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(.green)
                Text("Everything runs locally — your files never leave your computer.")
                    .font(.system(size: 11.5))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(Color.green.opacity(0.08))
            .cornerRadius(10)
            .modifier(entrance(2))

            Spacer()

            Button("Get Started") {
                withAnimation { step = .setupOllama }
            }
            .primaryButton()
            .zIndex(10)
            .modifier(entrance(3))

            Spacer()
        }
        .padding(32)
    }


    // ── Step 3 — Ollama setup ────────────────────────────────────────────────
    private var setupOllamaView: some View {
        VStack(alignment: .leading, spacing: 16) {

            VStack(alignment: .leading, spacing: 6) {
                Text("One-time setup")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.orange)
                    .textCase(.uppercase)
                    .kerning(0.8)

                Text("Install the local AI engine")
                    .font(.system(size: 20, weight: .bold))

                Text("Organizer uses Ollama to understand your commands — entirely on your Mac. Run these three commands in Terminal:")
                    .font(.system(size: 12.5))
                    .foregroundStyle(.secondary)
                    .lineSpacing(2)
            }
            .modifier(entrance(0))

            VStack(spacing: 10) {
                setupStep(number: "1", title: "Install Ollama",
                          command: "brew install ollama")
                    .modifier(entrance(1))
                setupStep(number: "2", title: "Download the AI model",
                          command: "ollama pull llama3.2")
                    .modifier(entrance(2))
                setupStep(number: "3", title: "Start Ollama",
                          command: "brew services start ollama")
                    .modifier(entrance(3))
            }

            Spacer()

            // Connection status
            HStack {
                ZStack {
                    if ollamaReady {
                        Circle().fill(.green).frame(width: 8, height: 8)
                    } else {
                        PulsingDot()
                    }
                }

                Text(ollamaReady ? "Connected — you're all set" : statusDetail)
                    .font(.system(size: 12))
                    .foregroundStyle(ollamaReady ? .primary : .secondary)
                    .lineLimit(2)

                Spacer()

                Button {
                    checkOllamaConnection()
                } label: {
                    if isCheckingHealth {
                        ProgressView().scaleEffect(0.55)
                    } else {
                        Text("Check Again")
                            .font(.system(size: 11.5))
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            .padding(.horizontal, 4)
            .modifier(entrance(4))

            Button("Continue") {
                withAnimation { step = .ready }
            }
            .primaryButton(disabled: !ollamaReady)
            .disabled(!ollamaReady)
            .frame(maxWidth: .infinity)
            .modifier(entrance(5))
        }
        .padding(28)
        .onAppear {
            checkOllamaConnection()
        }
        .onReceive(healthTimer) { _ in
            // keep checking every 3s until connected —
            // picks up the moment the user finishes the setup commands
            if step == .setupOllama && !ollamaReady {
                checkOllamaConnection()
            }
        }
    }

    private func setupStep(number: String, title: String, command: String) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Text(number)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 19, height: 19)
                    .background(Circle().fill(.orange))

                Text(title)
                    .font(.system(size: 13, weight: .medium))
            }

            HStack {
                Text(command)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(.primary.opacity(0.85))
                Spacer()
                copyButton(text: command)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color(nsColor: .controlBackgroundColor))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.primary.opacity(0.06), lineWidth: 1)
            )
        }
    }

    private func copyButton(text: String) -> some View {
        Button {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
            copiedCommand = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                copiedCommand = false
            }
        } label: {
            Image(systemName: copiedCommand ? "checkmark" : "doc.on.doc")
                .font(.system(size: 11))
        }
        .buttonStyle(.plain)
        .foregroundStyle(copiedCommand ? .green : .secondary)
    }

    private func checkOllamaConnection() {
        guard !isCheckingHealth else { return }
        isCheckingHealth = true

        Task {
            do {
                let health = try await APIService.shared.checkHealth()
                await MainActor.run {
                    ollamaReady      = health.isHealthy
                    isCheckingHealth = false
                    if !health.isHealthy {
                        // Server responded but Ollama isn't up yet
                        statusDetail = "Ollama not detected yet — run step 3"
                    }
                }
            } catch {
                await MainActor.run {
                    ollamaReady      = false
                    isCheckingHealth = false
                    // Server itself unreachable — different problem than Ollama
                    statusDetail = "Can't reach Organizer's engine (backend not running)"
                }
            }
        }
    }


    // ── Step 4 — Ready ───────────────────────────────────────────────────────
    private var readyView: some View {
        VStack(spacing: 22) {
            Spacer()

            ZStack {
                Circle()
                    .fill(Color.green.opacity(0.12))
                    .frame(width: 92, height: 92)
                Image(systemName: "checkmark")
                    .font(.system(size: 38, weight: .bold))
                    .foregroundStyle(.green)
            }
            .modifier(entrance(0))

            VStack(spacing: 8) {
                Text("You're all set, \(userName.isEmpty ? nameInput : userName)")
                    .font(.system(size: 24, weight: .bold))

                Text("Organizer is ready to help you\nclean up your Mac.")
                    .font(.system(size: 13.5))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
            }
            .modifier(entrance(1))

            Spacer()

            Button("Start Organizing") {
                isOnboardingComplete = true
            }
            .primaryButton()
            .modifier(entrance(2))

            Spacer()
        }
        .padding(32)
    }
}


// ── Staggered entrance modifier ───────────────────────────────────────────────
struct EntranceModifier: ViewModifier {
    let visible: Bool
    let delay: Double

    func body(content: Content) -> some View {
        content
            .opacity(visible ? 1 : 0)
            .offset(y: visible ? 0 : 14)
            .animation(
                .spring(response: 0.5, dampingFraction: 0.85).delay(delay),
                value: visible
            )
    }
}


// ── Waving hand animation ─────────────────────────────────────────────────────
struct WavingHand: View {
    @State private var waving = false

    var body: some View {
        Text("👋")
            .font(.system(size: 52))
            .rotationEffect(.degrees(waving ? 18 : -8), anchor: .bottomTrailing)
            .animation(
                .easeInOut(duration: 0.5)
                    .repeatCount(5, autoreverses: true),
                value: waving
            )
            .onAppear {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                    waving = true
                }
            }
    }
}


// ── Pulsing dot for the "waiting" state ───────────────────────────────────────
struct PulsingDot: View {
    @State private var pulsing = false

    var body: some View {
        Circle()
            .fill(Color.orange)
            .frame(width: 8, height: 8)
            .opacity(pulsing ? 0.35 : 1.0)
            .animation(
                .easeInOut(duration: 0.8).repeatForever(autoreverses: true),
                value: pulsing
            )
            .onAppear { pulsing = true }
    }
}


#Preview("Onboarding") {
    OnboardingView(userName: .constant(""), isOnboardingComplete: .constant(false))
}
