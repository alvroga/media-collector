import Foundation
import Observation

/// UI state and the glue to the engine. Everything the views show comes from here.
@MainActor
@Observable
final class AppModel {
    enum Phase { case starting, ready, failed(String) }

    var phase: Phase = .starting
    var projectURL: URL?
    var project: ProjectSummary?
    var plan: PlanSummary?
    var isLoadingProject = false
    var isPlanning = false
    var errorMessage: String?

    // Destination and run
    enum RunState { case idle, running, finished(RunReport), failed(String) }
    var destination: URL? = AppModel.savedDestination() {
        didSet { UserDefaults.standard.set(destination?.path, forKey: "destination") }
    }
    var relink = true
    var runState: RunState = .idle
    var progress: RunProgress?
    var isCancelling = false
    /// When the current run began (drives the elapsed-time readout).
    var runStartedAt: Date?
    /// The last few files finished during a run, newest last (for the progress screen).
    var recentFiles: [String] = []
    /// Copy worker count; the best default is still being investigated (see the open issue on copy concurrency).
    var workers = 4

    var options = CopyOptions() {
        didSet { if options != oldValue { schedulePlan() } }
    }
    /// "Entire project" vs "Choose sequences"
    var chooseSequences = false {
        didSet { if chooseSequences != oldValue { updateSequenceSelection() } }
    }
    var selectedSequences: Set<String> = [] {
        didSet { if chooseSequences { updateSequenceSelection() } }
    }

    private(set) var engine: EngineClient?
    private var eventTask: Task<Void, Never>?
    private var planTask: Task<Void, Never>?
    private var planGeneration = 0

    func startEngine() async {
        guard engine == nil else { return }
        let e = EngineClient()
        engine = e
        do {
            try await e.start()
            phase = .ready
            listenForProgress(e)
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }

    func open(_ url: URL) async {
        guard let engine, case .ready = phase else { return }
        errorMessage = nil
        isLoadingProject = true
        plan = nil
        defer { isLoadingProject = false }
        do {
            let summary = try await engine.call("open_project", ["path": url.path], as: ProjectSummary.self)
            projectURL = url
            project = summary
            var fresh = CopyOptions()
            fresh.includeProxies = summary.proxies > 0  // a project's proxies are part of the project
            options = fresh
            relink = summary.canRelink  // on by default, and off (and locked) where relinking isn't possible
            chooseSequences = false
            selectedSequences = Set(summary.sequences.map(\.id))
            schedulePlan(immediately: true)
        } catch {
            project = nil
            errorMessage = error.localizedDescription
        }
    }

    private static func savedDestination() -> URL? {
        guard let path = UserDefaults.standard.string(forKey: "destination"),
              FileManager.default.fileExists(atPath: path) else { return nil }
        return URL(fileURLWithPath: path)
    }

    private func listenForProgress(_ e: EngineClient) {
        eventTask = Task { [weak self] in
            for await ev in e.events {
                let kind = ev["event"] as? String
                if kind == "file", let status = ev["status"] as? String,
                   status == "copied" || status == "skipped_identical", let dest = ev["dest"] as? String {
                    self?.noteFinished(URL(fileURLWithPath: dest).lastPathComponent)
                    continue
                }
                guard kind == "progress", let data = try? JSONSerialization.data(withJSONObject: ev) else { continue }
                let dec = JSONDecoder()
                dec.keyDecodingStrategy = .convertFromSnakeCase
                if let p = try? dec.decode(RunProgress.self, from: data) { self?.progress = p }
            }
        }
    }

    /// Free space on the destination volume, if it can be determined reliably.
    var freeSpace: Int64? { destination.flatMap { Self.freeSpace(at: $0).bytes } }

    /// Whether the destination volume is a local disk (network servers report free space unreliably).
    var destinationIsLocal: Bool { destination.map { Self.freeSpace(at: $0).isLocal } ?? true }

    var notEnoughSpace: Bool {
        guard let free = freeSpace, let plan else { return false }
        return plan.bytes > free
    }

    /// Only a local disk's reading is trusted enough to stop the copy; on a network volume a low
    /// reading is shown as a warning but Start stays available (the copy itself reports a full disk).
    private var spaceBlocksStart: Bool { notEnoughSpace && destinationIsLocal }

    /// Free bytes at `url` and whether the volume is local. Asks the system three ways and takes the
    /// largest answer: "important usage" capacity alone is often 0 on SMB/NFS shares. A reading of 0 on a
    /// network volume means "unknown", not "full" (nil).
    nonisolated static func freeSpace(at url: URL) -> (bytes: Int64?, isLocal: Bool) {
        let keys: Set<URLResourceKey> = [
            .volumeAvailableCapacityForImportantUsageKey, .volumeAvailableCapacityKey, .volumeIsLocalKey,
        ]
        let values = try? url.resourceValues(forKeys: keys)
        let isLocal = values?.volumeIsLocal ?? true
        var readings: [Int64] = []
        if let v = values?.volumeAvailableCapacityForImportantUsage { readings.append(v) }
        if let v = values?.volumeAvailableCapacity { readings.append(Int64(v)) }
        var st = statfs()
        if statfs(url.path, &st) == 0 { readings.append(Int64(st.f_bavail) * Int64(st.f_bsize)) }
        guard let best = readings.max() else { return (nil, isLocal) }
        if best <= 0 && !isLocal { return (nil, isLocal) }
        return (best, isLocal)
    }

    var canStart: Bool {
        guard case .idle = runState, project != nil, destination != nil,
              let plan, plan.files > 0, !isPlanning, !spaceBlocksStart else { return false }
        return true
    }

    func start() async {
        guard canStart, let engine, let destination else { return }
        runState = .running
        runStartedAt = Date()
        progress = nil
        recentFiles = []
        isCancelling = false
        let args: [String: Any] = [
            "dest": destination.path, "options": options.engineDictionary,
            "workers": workers, "relink": relink && (project?.canRelink ?? false),
        ]
        do {
            runState = .finished(try await engine.call("run", args, as: RunReport.self))
        } catch {
            runState = .failed(error.localizedDescription)
        }
    }

    private func noteFinished(_ name: String) {
        recentFiles.append(name)
        if recentFiles.count > 4 { recentFiles.removeFirst(recentFiles.count - 4) }
    }

    func cancelRun() {
        guard let engine else { return }
        isCancelling = true
        Task { _ = try? await engine.call("cancel") }
    }

    func finishRun() {
        runState = .idle
        runStartedAt = nil
        progress = nil
    }

    /// Stops the engine process (also happens automatically when the client is released).
    func shutdown() {
        planTask?.cancel()
        eventTask?.cancel()
        engine?.stop()
        engine = nil
    }

    func closeProject() {
        planTask?.cancel()
        project = nil
        projectURL = nil
        plan = nil
        errorMessage = nil
    }

    private func updateSequenceSelection() {
        guard let project else { return }
        let all = Set(project.sequences.map(\.id))
        if chooseSequences && selectedSequences != all {
            options.sequenceIDs = project.sequences.map(\.id).filter(selectedSequences.contains)
        } else {
            options.sequenceIDs = nil
        }
    }

    /// Debounced: option changes (e.g. holding the stepper) collapse into one engine call.
    func schedulePlan(immediately: Bool = false) {
        planTask?.cancel()
        planGeneration += 1
        let generation = planGeneration
        let opts = options.engineDictionary
        planTask = Task { [weak self] in
            if !immediately { try? await Task.sleep(for: .milliseconds(250)) }
            guard !Task.isCancelled, let self, let engine = self.engine else { return }
            self.isPlanning = true
            defer { if generation == self.planGeneration { self.isPlanning = false } }
            do {
                let result = try await engine.call("plan", ["options": opts], as: PlanSummary.self)
                if generation == self.planGeneration { self.plan = result; self.errorMessage = nil }
            } catch {
                if generation == self.planGeneration { self.errorMessage = error.localizedDescription }
            }
        }
    }
}

extension Int64 {
    var byteString: String { ByteCountFormatter.string(fromByteCount: self, countStyle: .file) }
}
