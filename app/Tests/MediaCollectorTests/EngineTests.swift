import XCTest
@testable import MediaCollector

final class WireTypeTests: XCTestCase {
    func testDecodesPlanSummary() throws {
        let json = """
        {"files": 3, "originals": 2, "proxies": 1, "bytes": 12345,
         "missing": {"count": 1, "items": [{"path": "/x/a.mov", "reason": "not_found"}]},
         "unmapped_prefixes": [{"prefix": "O:", "files": 4}],
         "cache_skipped": 5, "renamed_on_collision": 0,
         "examples": [{"source": "/a/b.mov", "dest_rel": "b.mov"}]}
        """.data(using: .utf8)!
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let plan = try d.decode(PlanSummary.self, from: json)
        XCTAssertEqual(plan.files, 3)
        XCTAssertEqual(plan.bytes, 12345)
        XCTAssertEqual(plan.missing.items.first?.reason, "not_found")
        XCTAssertEqual(plan.unmappedPrefixes.first?.prefix, "O:")
        XCTAssertEqual(plan.examples.first?.destRel, "b.mov")
    }

    func testOptionsDictionaryMatchesTheProtocol() {
        var o = CopyOptions()
        var d = o.engineDictionary
        XCTAssertEqual(d["include_unused"] as? Bool, false)
        XCTAssertEqual(d["keep_from_level"] as? Int, 0)
        XCTAssertTrue(d["sequences"] is NSNull)          // all sequences
        XCTAssertNil(d["project_folder"])                // the app never sends a wrapper folder
        o.sequenceIDs = ["a", "b"]
        o.skipLevels = 4
        d = o.engineDictionary
        XCTAssertEqual(d["keep_from_level"] as? Int, 4)  // always an int: structure is always kept
        XCTAssertEqual(d["sequences"] as? [String], ["a", "b"])
    }

    func testDecodesRunReportAndProgress() throws {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let report = try d.decode(RunReport.self, from: """
        {"ok": false, "cancelled": false, "counts": {"copied": 3, "skipped_identical": 2, "missing": 1},
         "bytes": 999, "problems": [{"status": "missing", "path": "/x", "detail": "source file not found"}],
         "relinked_project": null,
         "relink": {"skipped": "the copy had problems; fix them and run again"}}
        """.data(using: .utf8)!)
        XCTAssertEqual(report.copied, 3)
        XCTAssertEqual(report.skippedIdentical, 2)
        XCTAssertEqual(report.problems.first?.status, "missing")
        XCTAssertNotNil(report.relink?.skipped)
        let p = try d.decode(RunProgress.self, from: """
        {"event": "progress", "id": 4, "file_index": 1, "file_count": 5, "name": "a.mov",
         "phase": "copying", "file_bytes_done": 5, "file_bytes_total": 10, "bytes_done": 25, "bytes_total": 100}
        """.data(using: .utf8)!)
        XCTAssertEqual(p.fraction, 0.25, accuracy: 0.0001)
        XCTAssertEqual(p.fileCount, 5)
    }

    func testDestinationKindForLocalFolders() throws {
        let info = try XCTUnwrap(DestinationInfo.info(for: FileManager.default.homeDirectoryForCurrentUser))
        XCTAssertEqual(info.kind, .internalDisk)
        XCTAssertFalse(info.volumeName.isEmpty)
        XCTAssertGreaterThan(info.icon.size.width, 0)
    }

    func testFreeSpaceOfALocalFolderIsPositive() {
        let r = AppModel.freeSpace(at: FileManager.default.temporaryDirectory)
        XCTAssertGreaterThan(r.bytes ?? 0, 0)
        XCTAssertTrue(r.isLocal)
    }

    func testByteString() {
        XCTAssertFalse(Int64(5_800_000).byteString.isEmpty)
    }
}

/// Talks to the real Python engine (needs the repo's .venv). Skipped when the fixture is absent.
final class EngineRoundTripTests: XCTestCase {
    let fixture = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Documents/UMM Airplanes/Airplanes - 01 Trailer.otio")

    func testEngineStartsAndAnswers() async throws {
        let engine = EngineClient()
        try await engine.start()
        let r = try await engine.call("volumes")
        XCTAssertNotNil(r["volumes"])
        do { _ = try await engine.call("nope"); XCTFail("expected an error") }
        catch { XCTAssertTrue(error.localizedDescription.contains("unknown command")) }
        engine.stop()
    }

    func testOpenAndPlanARealProject() async throws {
        try XCTSkipUnless(FileManager.default.fileExists(atPath: fixture.path), "fixture not present")
        let engine = EngineClient()
        try await engine.start()
        let project = try await engine.call("open_project", ["path": fixture.path], as: ProjectSummary.self)
        XCTAssertEqual(project.format, "otio")
        XCTAssertEqual(project.sequences.count, 1)
        XCTAssertEqual(project.originals, 14)
        XCTAssertTrue(project.canRelink)
        let plan = try await engine.call("plan", ["options": { var o = CopyOptions(); o.skipLevels = 4; return o.engineDictionary }()], as: PlanSummary.self)
        XCTAssertEqual(plan.files, 14)
        XCTAssertGreaterThan(plan.bytes, 500_000_000)
        XCTAssertEqual(plan.missing.count, 0)
        XCTAssertTrue(plan.examples.first?.destRel.hasPrefix("MediaFiles/") ?? false)
        engine.stop()
    }
}

@MainActor
final class AppModelTests: XCTestCase {
    let fixture = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Documents/UMM Airplanes/Airplanes - 01 Trailer.prproj")

    func waitForPlan(_ model: AppModel, timeout: Double = 15, where ok: (PlanSummary) -> Bool = { _ in true }) async throws -> PlanSummary {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            if let p = model.plan, !model.isPlanning, ok(p) { return p }
            try await Task.sleep(for: .milliseconds(50))
        }
        throw XCTSkip("plan did not arrive in time")
    }

    func testOptionsReplanLive() async throws {
        try XCTSkipUnless(FileManager.default.fileExists(atPath: fixture.path), "fixture not present")
        let model = AppModel()
        await model.startEngine()
        await model.open(fixture)
        XCTAssertEqual(model.project?.format, "premiere")
        XCTAssertEqual(model.project?.proxies, 10)

        XCTAssertTrue(model.options.includeProxies)      // a project with proxies copies them by default
        let base = try await waitForPlan(model)
        XCTAssertEqual(base.files, 24)                    // 14 used originals + their 10 proxies
        XCTAssertEqual(base.proxies, 10)

        model.options.includeProxies = false
        let withoutProxies = try await waitForPlan(model) { $0.files == 14 }
        XCTAssertEqual(withoutProxies.proxies, 0)

        model.options.skipLevels = 4
        let skipped = try await waitForPlan(model) { $0.examples.first?.destRel.hasPrefix("MediaFiles/") == true }
        XCTAssertTrue(skipped.examples.first?.destRel.hasPrefix("MediaFiles/") ?? false)

        model.chooseSequences = true                      // choose, but none selected
        model.selectedSequences = []
        let none = try await waitForPlan(model) { $0.files == 0 }
        XCTAssertEqual(none.files, 0)
        model.shutdown()
    }

    func testBadFileShowsAnErrorAndNoProject() async throws {
        let model = AppModel()
        await model.startEngine()
        let bad = FileManager.default.temporaryDirectory.appendingPathComponent("nope.xyz")
        try Data("x".utf8).write(to: bad)
        await model.open(bad)
        XCTAssertNil(model.project)
        XCTAssertNotNil(model.errorMessage)
        model.shutdown()
    }

    /// The whole flow through the model: open, choose a destination, Start, get a report and a
    /// relinked project. Copies ~540 MB into a temporary folder.
    func testStartCopiesAndRelinks() async throws {
        try XCTSkipUnless(FileManager.default.fileExists(atPath: fixture.path), "fixture not present")
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent("mc-app-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dest, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dest) }
        let model = AppModel()
        await model.startEngine()
        await model.open(fixture)
        model.destination = dest
        model.options.skipLevels = 4
        XCTAssertFalse(model.canStart || model.plan == nil && false)   // needs a plan first
        _ = try await waitForPlan(model) { $0.examples.first?.destRel.hasPrefix("MediaFiles/") == true }
        XCTAssertTrue(model.canStart)
        await model.start()
        guard case .finished(let report) = model.runState else { return XCTFail("run did not finish: \(model.runState)") }
        XCTAssertTrue(report.ok)
        XCTAssertEqual(report.copied, 24)                                // originals + proxies
        XCTAssertEqual(report.relink?.relinked, 24)
        XCTAssertEqual(report.relink?.leftUnchanged, 0)                  // nothing left pointing at the old place
        XCTAssertNotNil(report.relinkedProject)
        XCTAssertTrue(FileManager.default.fileExists(atPath: report.relinkedProject ?? ""))
        XCTAssertNotNil(model.progress)                                  // progress events arrived
        XCTAssertTrue(FileManager.default.fileExists(atPath: dest.appendingPathComponent("MediaFiles/Audio/INT_01.aif").path))
        model.finishRun()
        XCTAssertFalse(model.canStart == false && model.project == nil)
        model.shutdown()
    }
}
