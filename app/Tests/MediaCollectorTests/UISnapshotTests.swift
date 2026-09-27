import SwiftUI
import XCTest
@testable import MediaCollector

/// Renders the real views offscreen to PNG files so the layout can be reviewed without a screen.
/// Runs only when MEDIA_COLLECTOR_SNAPSHOT_DIR is set:  MEDIA_COLLECTOR_SNAPSHOT_DIR=/tmp/shots swift test --filter UISnapshotTests
@MainActor
final class UISnapshotTests: XCTestCase {
    private var dir: URL? {
        ProcessInfo.processInfo.environment["MEDIA_COLLECTOR_SNAPSHOT_DIR"].map { URL(fileURLWithPath: $0) }
    }

    private func render<V: View>(_ view: V, name: String, width: CGFloat = 640, height: CGFloat = 900,
                                 dark: Bool = true) throws {
        guard let dir else { throw XCTSkip("set MEDIA_COLLECTOR_SNAPSHOT_DIR to render snapshots") }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let host = NSHostingView(rootView: view.frame(width: width, height: height)
            .background(Color(nsColor: .windowBackgroundColor)))
        host.frame = NSRect(x: 0, y: 0, width: width, height: height)
        let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))  // let SwiftUI settle
        let rep = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d
    }

    private func loadedModel() throws -> AppModel {
        let m = AppModel()
        m.phase = .ready
        m.projectURL = URL(fileURLWithPath: "/Users/example/Documents/Airplanes/Airplanes - 01 Trailer.prproj")
        m.project = try decoder().decode(ProjectSummary.self, from: """
        {"path": "/x/Airplanes - 01 Trailer.prproj", "format": "premiere",
         "sequences": [{"id": "a", "name": "Airplanes - 01 Trailer", "originals": 14},
                       {"id": "b", "name": "Airplanes - 02 Alternative Trailer", "originals": 12}],
         "files": 24, "originals": 14, "proxies": 10, "unused": 0, "cache": 0, "non_file_skipped": 0,
         "warnings": [], "can_relink": true, "unmapped_prefixes": []}
        """.data(using: .utf8)!)
        m.plan = try decoder().decode(PlanSummary.self, from: """
        {"files": 24, "originals": 14, "proxies": 10, "bytes": 559600000,
         "missing": {"count": 0, "items": []}, "unmapped_prefixes": [], "cache_skipped": 0,
         "renamed_on_collision": 0,
         "examples": [{"source": "/Users/example/Documents/Airplanes/MediaFiles/Audio/INT_01.aif",
                       "dest_rel": "MediaFiles/Audio/INT_01.aif"}]}
        """.data(using: .utf8)!)
        m.options.includeProxies = true
        m.options.skipLevels = 4
        m.recentFiles = ["A001_C001.mov", "A001_C001_Proxy.mp4", "DRONE_001.mov"]
        m.destination = URL(fileURLWithPath: "/Users/example/Desktop/Copy")
        return m
    }

    func testEmptyState() throws {
        let m = AppModel(); m.phase = .ready
        try render(ContentView().environment(m), name: "1-empty", height: 460)
    }

    func testEmptyWithError() throws {
        let m = AppModel(); m.phase = .ready
        m.errorMessage = "This is a Final Cut Pro library. In Final Cut choose File > Export XML and open that file instead."
        try render(ContentView().environment(m), name: "1b-empty-error", height: 520)
    }

    func testAfterEffectsProject() throws {
        let m = try loadedModel()
        m.projectURL = URL(fileURLWithPath: "/Users/example/Documents/Airplanes/Airplanes.aep")
        m.project = try decoder().decode(ProjectSummary.self, from: """
        {"path": "/x/Airplanes.aep", "format": "aep", "sequences": [],
         "files": 10, "originals": 10, "proxies": 0, "unused": 0, "cache": 0, "non_file_skipped": 0,
         "warnings": [],
         "can_relink": false, "unmapped_prefixes": []}
        """.data(using: .utf8)!)
        m.relink = false
        m.options.includeProxies = false
        try render(ContentView().environment(m), name: "2d-setup-aep", height: 900)
    }

    func testNetworkDestination() throws {
        let m = try loadedModel()
        m.destination = URL(fileURLWithPath: "/Volumes/media")
        try render(ContentView().environment(m), name: "2c-setup-network", height: 900)
    }

    func testLoadedSetup() throws {
        let m = try loadedModel()
        try render(ContentView().environment(m), name: "2-setup", height: 1000)
        m.chooseSequences = true
        try render(ContentView().environment(m), name: "2b-setup-choose", height: 1040)
    }

    func testRunning() throws {
        let m = try loadedModel()
        m.runState = .running
        m.progress = try decoder().decode(RunProgress.self, from: """
        {"file_index": 8, "file_count": 24, "name": "HAWAIIAN_LANDING.mov", "phase": "copying",
         "file_bytes_done": 10, "file_bytes_total": 40, "bytes_done": 190000000, "bytes_total": 1119200000}
        """.data(using: .utf8)!)
        try render(ContentView().environment(m), name: "3-running", height: 560)
    }

    func testReports() throws {
        let m = try loadedModel()
        let ok = try decoder().decode(RunReport.self, from: """
        {"ok": true, "cancelled": false, "counts": {"copied": 24}, "bytes": 559600000, "problems": [],
         "relinked_project": "/Users/example/Desktop/Copy/Airplanes - 01 Trailer.prproj",
         "relink": {"relinked": 24, "media_objects": 24, "left_unchanged": 0, "missing_after": [], "notes": []}}
        """.data(using: .utf8)!)
        m.runState = .finished(ok)
        try render(ContentView().environment(m), name: "4-report-ok", height: 560)
        let bad = try decoder().decode(RunReport.self, from: """
        {"ok": false, "cancelled": false, "counts": {"copied": 12, "missing": 2}, "bytes": 300000000,
         "problems": [{"status": "missing", "path": "/Volumes/Media/Shoot/A001_C003.mov", "detail": "source file not found"},
                      {"status": "missing", "path": "O:\\\\Shoot\\\\b.mov", "detail": "no path mapping for this drive/share"}],
         "relinked_project": null, "relink": {"skipped": "the copy had problems; fix them and run again"}}
        """.data(using: .utf8)!)
        m.runState = .finished(bad)
        try render(ContentView().environment(m), name: "5-report-problems", height: 640)
    }

    func testBadges() throws {
        struct Badges: View {
            var body: some View {
                VStack(spacing: 20) {
                    FormatRow()
                    HStack(spacing: 20) { ForEach(ProjectFormat.allCases) { FormatBadge(format: $0, size: 92) } }
                }.padding(30).background(Color(nsColor: .windowBackgroundColor))
            }
        }
        try render(Badges(), name: "6-badges", width: 640, height: 260)
    }
}
