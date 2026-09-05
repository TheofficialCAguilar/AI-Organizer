//
//  ContentView.swift
//  Organizer
//
//  Created by Carlos Aguilar
//
//  Chat interface redesigned to flow like modern AI chatbots
//  (Claude / ChatGPT / Gemini):
//  - Time-aware centered greeting on the empty state
//  - Auto-scroll to the newest message
//  - Animated "thinking" dots instead of a spinner
//  - Multiline input that grows as you type, send button inside
//  - Smooth spring animations when messages appear

import SwiftUI

// message types for chat history

struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let role: Role
    let text: String

    enum Role {
        case user
        case system
        case error
    }
}

struct ContentView: View {
    @StateObject private var api = APIService.shared

    @AppStorage("userName") private var userName: String = ""
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding: Bool = false

    @State private var inputText      = ""
    @State private var messages: [ChatMessage] = []
    @State private var appState: AppState = .idle
    @State private var currentPreview: CommandResponse? = nil
    @State private var healthStatus: HealthStatus? = nil
    @State private var lastExecuteResult: ExecuteResult? = nil
    @State private var searchResults: [FileItem]? = nil
    @FocusState private var inputFocused: Bool

    var body: some View {
        Group {
            if !hasCompletedOnboarding {
                OnboardingView(
                    userName: $userName,
                    isOnboardingComplete: Binding(
                        get: { hasCompletedOnboarding },
                        set: { hasCompletedOnboarding = $0 }
                    )
                )
            } else {
                mainChatView
            }
        }
    }

   // main chat interface
    
    private var mainChatView: some View {
        VStack(spacing: 0) {

            headerView

            Divider()

            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {

                        if messages.isEmpty && currentPreview == nil {
                            welcomeView
                        }

                        ForEach(messages) { message in
                            MessageBubble(message: message)
                                .transition(.asymmetric(
                                    insertion: .move(edge: .bottom)
                                        .combined(with: .opacity),
                                    removal: .opacity
                                ))
                        }

                        if let preview = currentPreview {
                            PreviewCard(
                                preview: preview,
                                onConfirm: { confirmExecute(preview) },
                                onCancel:  { cancelPreview() }
                            )
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                        }

                        if let result = lastExecuteResult {
                            ResultCard(result: result, onUndo: { performUndo() })
                                .transition(.move(edge: .bottom).combined(with: .opacity))
                        }

                        if let results = searchResults {
                            SearchResultsCard(files: results)
                                .transition(.move(edge: .bottom).combined(with: .opacity))
                        }

                        if case .thinking = appState {
                            TypingIndicator()
                                .transition(.opacity)
                        }
                        if case .executing = appState {
                            TypingIndicator(label: "Organizing…")
                                .transition(.opacity)
                        }

                        // Invisible anchor to scroll to
                        Color.clear
                            .frame(height: 1)
                            .id("bottom")
                    }
                    .padding(16)
                    .animation(.spring(response: 0.35, dampingFraction: 0.8),
                               value: messages)
                }
                .onChange(of: messages) { _, _ in
                    scrollToBottom(proxy)
                }
                .onChange(of: currentPreview != nil) { _, _ in
                    scrollToBottom(proxy)
                }
                .onChange(of: lastExecuteResult != nil) { _, _ in
                    scrollToBottom(proxy)
                }
            }

    
            inputBar
        }
        .frame(minWidth: 440, idealWidth: 480, minHeight: 560, idealHeight: 680)
        .background(Color(nsColor: .windowBackgroundColor))
        .task {
            await checkHealth()
        }
        .onAppear {
            // Focus the input when the window opens —
            // MenuBarExtra windows don't auto-focus.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                inputFocused = true
            }
        }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.25)) {
            proxy.scrollTo("bottom", anchor: .bottom)
        }
    }

    // ── Header ────────────────────────────────────────────────────────────────
    private var headerView: some View {
        HStack {
            Image(systemName: "folder.badge.gearshape")
                .font(.system(size: 15))
                .foregroundStyle(.orange)

            Text("Organizer")
                .font(.system(size: 13, weight: .semibold))

            Spacer()

            Circle()
                .fill(healthStatusColor)
                .frame(width: 7, height: 7)

            Text(healthStatusText)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var healthStatusColor: Color {
        guard let health = healthStatus else { return .gray }
        return health.isHealthy ? .green : .red
    }

    private var healthStatusText: String {
        healthStatus?.isHealthy == true ? "Ready" : (healthStatus?.statusMessage ?? "Checking…")
    }

    // ── Welcome view — centered, time-aware, chatbot style ───────────────────
    private var timeGreeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<12:  return "Good morning"
        case 12..<17: return "Good afternoon"
        case 17..<22: return "Good evening"
        default:      return "Hello"
        }
    }

    private var welcomeView: some View {
        VStack(spacing: 22) {
            Spacer(minLength: 60)

            Image(systemName: "folder.badge.gearshape")
                .font(.system(size: 34))
                .foregroundStyle(.orange.opacity(0.85))

            VStack(spacing: 6) {
                Text("\(timeGreeting), \(userName.isEmpty ? "there" : userName)")
                    .font(.system(size: 22, weight: .semibold))

                Text("What would you like to organize today?")
                    .font(.system(size: 13.5))
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 8) {
                suggestionChip(icon: "rectangle.3.group",
                               text: "organize my desktop")
                suggestionChip(icon: "camera.viewfinder",
                               text: "move screenshots to their own folder")
                suggestionChip(icon: "doc.on.doc",
                               text: "find duplicate files on my desktop")
                suggestionChip(icon: "magnifyingglass",
                               text: "find all pdfs on my desktop")
            }
            .frame(maxWidth: 320)

            Spacer(minLength: 40)
        }
        .frame(maxWidth: .infinity)
    }

    private func suggestionChip(icon: String, text: String) -> some View {
        Button {
            inputText = text
            sendCommand()
        } label: {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundStyle(.orange.opacity(0.8))
                    .frame(width: 16)

                Text(text)
                    .font(.system(size: 12.5))
                    .foregroundStyle(.primary.opacity(0.85))

                Spacer()

                Image(systemName: "arrow.up.right")
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary.opacity(0.5))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color(nsColor: .controlBackgroundColor))
            .cornerRadius(10)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.primary.opacity(0.06), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    // ── Input bar — grows with text, send button inside ──────────────────────
    private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Message Organizer…", text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .lineLimit(1...5)                    // grows up to 5 lines
                .focused($inputFocused)
                .onSubmit { sendCommand() }
                .disabled(isBusy)

            Button {
                sendCommand()
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(canSend ? Color.orange : Color.secondary.opacity(0.4))
                    .animation(.easeInOut(duration: 0.15), value: canSend)
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(
                    inputFocused ? Color.orange.opacity(0.45)
                                 : Color.primary.opacity(0.08),
                    lineWidth: 1
                )
        )
        .padding(12)
    }

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespaces).isEmpty && !isBusy
    }

    private var isBusy: Bool {
        switch appState {
        case .thinking, .executing: return true
        default: return false
        }
    }


    // ── Actions ───────────────────────────────────────────────────────────────

    private func checkHealth() async {
        do {
            healthStatus = try await api.checkHealth()
        } catch {
            healthStatus = HealthStatus(
                server: "unreachable", ollama: "unknown",
                model: "llama3", version: "?"
            )
        }
    }

    private func sendCommand() {
        let command = inputText.trimmingCharacters(in: .whitespaces)
        guard !command.isEmpty, !isBusy else { return }

        withAnimation {
            messages.append(ChatMessage(role: .user, text: command))
            lastExecuteResult = nil
            searchResults     = nil
        }
        inputText = ""
        appState = .thinking

        Task {
            do {
                let response = try await api.sendCommand(command: command)

                await MainActor.run {
                    if response.action == "undo" {
                        performUndo()
                        return
                    }

                    // Unsupported command
                    if response.action == "unknown" {
                        withAnimation {
                            appState = .idle
                            messages.append(ChatMessage(
                                role: .system,
                                text: response.explanation.isEmpty
                                    ? "I can organize and move files, but I can't do that yet."
                                    : response.explanation
                            ))
                        }
                        return
                    }

                    // Search / duplicates-with-no-results — show list, no confirm
                    if response.action == "search" {
                        withAnimation {
                            appState = .idle
                            messages.append(ChatMessage(
                                role: .system,
                                text: response.summary
                            ))
                            if let files = response.files, !files.isEmpty {
                                searchResults = files
                            }
                        }
                        return
                    }

                    withAnimation {
                        appState = .preview
                        currentPreview = response
                    }
                }
            } catch {
                await MainActor.run {
                    withAnimation {
                        appState = .error(error.localizedDescription)
                        messages.append(ChatMessage(
                            role: .error,
                            text: error.localizedDescription
                        ))
                    }
                }
            }
        }
    }

    private func confirmExecute(_ preview: CommandResponse) {
        // Route to trash if this is a delete action
        if preview.action == "trash" {
            confirmTrash(preview)
            return
        }
        // Route to zip if this is a compress action
        if preview.action == "zip" {
            confirmZip(preview)
            return
        }

        withAnimation {
            appState = .executing
            currentPreview = nil
        }

        Task {
            do {
                let result = try await api.execute(
                    operations: preview.operations,
                    command: messages.last(where: { $0.role == .user })?.text ?? ""
                )

                await MainActor.run {
                    withAnimation {
                        appState = .done
                        lastExecuteResult = result
                        messages.append(ChatMessage(
                            role: .system,
                            text: result.summary
                        ))
                    }
                }
            } catch {
                await MainActor.run {
                    withAnimation {
                        appState = .error(error.localizedDescription)
                        messages.append(ChatMessage(
                            role: .error,
                            text: error.localizedDescription
                        ))
                    }
                }
            }
        }
    }

    private func confirmTrash(_ preview: CommandResponse) {
        withAnimation {
            appState = .executing
            currentPreview = nil
        }

        Task {
            do {
                let result = try await api.trash(
                    operations: preview.operations,
                    command: messages.last(where: { $0.role == .user })?.text ?? ""
                )

                await MainActor.run {
                    withAnimation {
                        appState = .done
                        lastExecuteResult = result
                        messages.append(ChatMessage(
                            role: .system,
                            text: result.summary + " — recoverable from Finder's Trash"
                        ))
                    }
                }
            } catch {
                await MainActor.run {
                    withAnimation {
                        appState = .error(error.localizedDescription)
                        messages.append(ChatMessage(
                            role: .error,
                            text: error.localizedDescription
                        ))
                    }
                }
            }
        }
    }

    private func confirmZip(_ preview: CommandResponse) {
        withAnimation {
            appState = .executing
            currentPreview = nil
        }

        Task {
            do {
                let result = try await api.zip(
                    operations: preview.operations,
                    command: messages.last(where: { $0.role == .user })?.text ?? ""
                )

                await MainActor.run {
                    withAnimation {
                        appState = .done
                        messages.append(ChatMessage(
                            role: .system,
                            text: result.summary + " — originals untouched"
                        ))
                    }
                }
            } catch {
                await MainActor.run {
                    withAnimation {
                        appState = .error(error.localizedDescription)
                        messages.append(ChatMessage(
                            role: .error,
                            text: error.localizedDescription
                        ))
                    }
                }
            }
        }
    }

    private func cancelPreview() {
        withAnimation {
            currentPreview = nil
            appState = .idle
            messages.append(ChatMessage(role: .system, text: "Cancelled"))
        }
    }

    private func performUndo() {
        withAnimation { appState = .executing }

        Task {
            do {
                let result = try await api.undo()
                await MainActor.run {
                    withAnimation {
                        appState = .idle
                        lastExecuteResult = nil
                        let text = result.message ?? "Reversed \(result.reversed) file(s)"
                        messages.append(ChatMessage(role: .system, text: text))
                    }
                }
            } catch {
                await MainActor.run {
                    withAnimation {
                        appState = .error(error.localizedDescription)
                        messages.append(ChatMessage(
                            role: .error,
                            text: error.localizedDescription
                        ))
                    }
                }
            }
        }
    }
}


// ── Search results card ───────────────────────────────────────────────────────
struct SearchResultsCard: View {
    let files: [FileItem]
    private let maxShown = 12

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(files.prefix(maxShown))) { file in
                HStack(spacing: 8) {
                    Image(systemName: icon(for: file.category))
                        .font(.system(size: 11))
                        .foregroundStyle(.orange.opacity(0.8))
                        .frame(width: 15)

                    Text(file.name)
                        .font(.system(size: 12))
                        .lineLimit(1)
                        .truncationMode(.middle)

                    Spacer()

                    Text(file.sizeLabel)
                        .font(.system(size: 10.5))
                        .foregroundStyle(.secondary)
                }
            }

            if files.count > maxShown {
                Text("+ \(files.count - maxShown) more")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .padding(.top, 2)
            }
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(12)
    }

    private func icon(for category: String) -> String {
        switch category {
        case "screenshot":   return "camera.viewfinder"
        case "image":        return "photo"
        case "document":     return "doc.text"
        case "spreadsheet":  return "tablecells"
        case "presentation": return "rectangle.on.rectangle"
        case "video":        return "film"
        case "audio":        return "music.note"
        case "code":         return "chevron.left.forwardslash.chevron.right"
        case "archive":      return "doc.zipper"
        default:             return "doc"
        }
    }
}


// ── Typing indicator — three bouncing dots like Claude/ChatGPT ──────────────
struct TypingIndicator: View {
    var label: String = "Thinking"
    @State private var animating = false

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(Color.secondary.opacity(0.55))
                        .frame(width: 6, height: 6)
                        .offset(y: animating ? -3 : 1)
                        .animation(
                            .easeInOut(duration: 0.5)
                                .repeatForever(autoreverses: true)
                                .delay(Double(i) * 0.15),
                            value: animating
                        )
                }
            }

            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(12)
        .onAppear { animating = true }
    }
}


// ── Message bubble ────────────────────────────────────────────────────────────
struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 50) }

            Text(message.text)
                .font(.system(size: 13))
                .foregroundStyle(textColor)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(backgroundColor)
                .cornerRadius(14)

            if message.role != .user { Spacer(minLength: 50) }
        }
    }

    private var backgroundColor: Color {
        switch message.role {
        case .user:   return .orange
        case .system: return Color(nsColor: .controlBackgroundColor)
        case .error:  return .red.opacity(0.15)
        }
    }

    private var textColor: Color {
        switch message.role {
        case .user:   return .white
        case .system: return .primary
        case .error:  return .red
        }
    }
}


// ── Preview card ──────────────────────────────────────────────────────────────
struct PreviewCard: View {
    let preview: CommandResponse
    let onConfirm: () -> Void
    let onCancel:  () -> Void

    private var isTrash: Bool  { preview.action == "trash" }
    private var isZip: Bool    { preview.action == "zip" }
    private var isRename: Bool { preview.action == "rename" }

    private var confirmLabel: String {
        if isTrash  { return "Move \(preview.totalFiles) files to Trash" }
        if isZip    { return "Zip \(preview.totalFiles) files" }
        if isRename { return "Rename \(preview.totalFiles) files" }
        return "Confirm — Move \(preview.totalFiles) files"
    }

    private var rowIcon: String {
        if isTrash  { return "trash.fill" }
        if isZip    { return "doc.zipper" }
        if isRename { return "pencil" }
        return "folder.fill"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {

            // Trash warning banner
            if isTrash {
                HStack(spacing: 8) {
                    Image(systemName: "trash.fill")
                        .font(.system(size: 12))
                        .foregroundStyle(.red)
                    Text("Files will be moved to Trash — recoverable from Finder")
                        .font(.system(size: 11.5))
                        .foregroundStyle(.red.opacity(0.85))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Color.red.opacity(0.08))
                .cornerRadius(7)
            }

            Text(preview.explanation)
                .font(.system(size: 13, weight: .medium))

            VStack(alignment: .leading, spacing: 4) {
                ForEach(preview.folders.sorted(by: { $0.key < $1.key }), id: \.key) { folder, count in
                    HStack {
                        Image(systemName: rowIcon)
                            .font(.system(size: 11))
                            .foregroundStyle(isTrash ? .red : .orange)
                        Text(folder)
                            .font(.system(size: 12))
                        Spacer()
                        Text("\(count) file\(count == 1 ? "" : "s")")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(10)
            .background(Color(nsColor: .controlBackgroundColor))
            .cornerRadius(8)

            if !preview.validation.warnings.isEmpty {
                ForEach(preview.validation.warnings, id: \.self) { warning in
                    Text("⚠️ \(warning)")
                        .font(.system(size: 11))
                        .foregroundStyle(.orange)
                }
            }

            HStack(spacing: 8) {
                Button("Cancel", action: onCancel)
                    .buttonStyle(.bordered)

                Button(confirmLabel, action: onConfirm)
                .buttonStyle(.borderedProminent)
                .tint(isTrash ? .red : .orange)
                .disabled(!preview.validation.valid)
            }
        }
        .padding(12)
        .background(Color(nsColor: .windowBackgroundColor))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(
                    isTrash ? Color.red.opacity(0.3) : Color.orange.opacity(0.3),
                    lineWidth: 1
                )
        )
        .cornerRadius(12)
    }
}


// ── Result card ───────────────────────────────────────────────────────────────
struct ResultCard: View {
    let result: ExecuteResult
    let onUndo: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Text(result.summary)
                    .font(.system(size: 13, weight: .medium))
            }

            if !result.errors.isEmpty {
                ForEach(result.errors, id: \.self) { error in
                    Text("⚠️ \(error)")
                        .font(.system(size: 11))
                        .foregroundStyle(.orange)
                }
            }

            Button("Undo", action: onUndo)
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(12)
        .background(Color.green.opacity(0.08))
        .cornerRadius(12)
    }
}


#Preview {
    ContentView()
}
