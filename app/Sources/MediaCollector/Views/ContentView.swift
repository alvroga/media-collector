import SwiftUI

struct ContentView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Group {
            switch model.phase {
            case .starting:
                VStack(spacing: 10) { ProgressView(); Text("Starting…").foregroundStyle(.secondary) }
            case .failed(let message):
                ContentUnavailableView("Can't start the engine", systemImage: "exclamationmark.triangle",
                                       description: Text(message))
            case .ready:
                switch model.runState {
                case .idle: setup
                case .running: RunningView()
                case .finished(let report): ReportView(report: report)
                case .failed(let message):
                    VStack(spacing: 14) {
                        ContentUnavailableView("The copy failed", systemImage: "xmark.octagon", description: Text(message))
                        Button("Back") { model.finishRun() }
                    }
                }
            }
        }
        .frame(minWidth: 560, minHeight: 480)
        .background(Theme.window(scheme))
        .background(WindowReader { window = $0 })
        .onPreferenceChange(SetupHeightKey.self) { setupHeight = $0; fitWindow() }
        .onPreferenceChange(BarHeightKey.self) { barHeight = $0; fitWindow() }
    }

    /// Slack below the content so the scroll bar does not appear when everything fits.
    private static let spareRoom: CGFloat = 40

    @State private var window: NSWindow?
    @State private var setupHeight: CGFloat = 0
    @State private var barHeight: CGFloat = 0

    /// Grows the window (never shrinks it) so the whole setup screen is visible without scrolling,
    /// as far as the screen allows; the top edge stays where it is. The ScrollView is only the fallback.
    private func fitWindow() {
        guard let window, setupHeight > 0, case .idle = model.runState else { return }
        let missing = setupHeight + barHeight + Self.spareRoom - window.contentLayoutRect.height
        guard missing > 1 else { return }
        let room = (window.screen?.visibleFrame.height ?? 900) - window.frame.height
        let grow = min(missing, max(0, room))
        guard grow > 0 else { return }
        var f = window.frame
        f.size.height += grow
        f.origin.y -= grow  // keep the top edge fixed
        if let visible = window.screen?.visibleFrame, f.origin.y < visible.minY { f.origin.y = visible.minY }
        window.setFrame(f, display: true, animate: true)
    }

    private var setup: some View {
        ScrollView {
            VStack(spacing: 14) {
                ProjectCard()
                DestinationCard()
                SequencesCard()
                OptionsCard()
                SummaryCard()
                Text("Media Collector \(appVersion)")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .padding(.top, 4)
            }
            .padding(20)
            .background(GeometryReader { Color.clear.preference(key: SetupHeightKey.self, value: $0.size.height) })
        }
        .safeAreaInset(edge: .bottom) {
            StartBar()
                .background(GeometryReader { Color.clear.preference(key: BarHeightKey.self, value: $0.size.height) })
        }
    }
}

private struct SetupHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

private struct BarHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

/// Hands the hosting NSWindow to SwiftUI.
private struct WindowReader: NSViewRepresentable {
    let onWindow: (NSWindow?) -> Void
    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async { onWindow(v.window) }
        return v
    }
    func updateNSView(_ v: NSView, context: Context) {
        DispatchQueue.main.async { onWindow(v.window) }
    }
}
