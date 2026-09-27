import SwiftUI

@main
struct MediaCollectorApp: App {
    @State private var model = AppModel()

    init() {
        // A SwiftUI app launched from `swift run` needs to become a regular foreground app.
        NSApplication.shared.setActivationPolicy(.regular)
        // Packaged app: the icon comes from Info.plist. Dev builds (`swift run`): read it from the repo.
        if let icon = Self.devIcon() { NSApplication.shared.applicationIconImage = icon }
    }

    private static func devIcon() -> NSImage? {
        if Bundle.main.bundleURL.pathExtension == "app" { return nil }
        var u = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 { u.deleteLastPathComponent() }  // MediaCollector, Sources, app
        return NSImage(contentsOf: u.appendingPathComponent("Branding/AppIcon.png"))
    }

    var body: some Scene {
        WindowGroup("Media Collector") {
            ContentView()
                .environment(model)
                .onOpenURL { url in Task { await model.open(url) } }  // Finder / Dock: open with
                .task {
                    await model.startEngine()
                    NSApplication.shared.activate(ignoringOtherApps: true)
                }
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 640, height: 720)
    }
}
