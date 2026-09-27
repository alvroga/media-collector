import Foundation

struct EngineError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// Serialises long engine jobs (the engine runs one at a time and answers `busy` otherwise).
private actor Mutex {
    private var locked = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    func lock() async {
        if !locked { locked = true; return }
        await withCheckedContinuation { waiters.append($0) }
    }
    func unlock() {
        if waiters.isEmpty { locked = false } else { waiters.removeFirst().resume() }
    }
}

/// Launches `python -m media_collector serve` and speaks the JSON-lines protocol over its stdin/stdout.
final class EngineClient: @unchecked Sendable {
    typealias Message = [String: Any]

    private let process = Process()
    private let stdinPipe = Pipe()
    private let stdoutPipe = Pipe()
    private let lock = NSLock()
    private var pending: [Int: CheckedContinuation<Message, Error>] = [:]
    private var nextID = 1
    private var readyContinuation: CheckedContinuation<Void, Error>?
    private var isReady = false
    private var finished = false
    private let longJobs = Mutex()
    /// Events streamed by the engine during `run` (progress, file), and unsolicited errors.
    let events: AsyncStream<Message>
    private let eventSink: AsyncStream<Message>.Continuation

    /// Dev default: the repository's virtualenv, found relative to this source file.
    static func repoRoot() -> URL {
        if let r = ProcessInfo.processInfo.environment["MEDIA_COLLECTOR_REPO"] { return URL(fileURLWithPath: r) }
        var u = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { u.deleteLastPathComponent() }  // Engine, MediaCollector, Sources, app, <repo>
        return u
    }

    /// The Python runtime shipped inside a packaged app (Contents/Resources/engine), if present.
    static func bundledLaunch() -> (python: URL, environment: [String: String], cwd: URL)? {
        guard let res = Bundle.main.resourceURL else { return nil }
        let python = res.appendingPathComponent("engine/python/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: python.path) else { return nil }
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = res.appendingPathComponent("engine/site-packages").path
        env["PYTHONNOUSERSITE"] = "1"        // ignore anything installed on the user's Mac
        env["PYTHONDONTWRITEBYTECODE"] = "1" // never write into the (signed) app bundle
        return (python, env, FileManager.default.homeDirectoryForCurrentUser)
    }

    init(pythonPath: String? = nil, repo: URL? = nil) {
        var cont: AsyncStream<Message>.Continuation!
        events = AsyncStream { cont = $0 }
        eventSink = cont
        let overridden = pythonPath ?? ProcessInfo.processInfo.environment["MEDIA_COLLECTOR_PYTHON"]
        if overridden == nil, repo == nil, let b = Self.bundledLaunch() {
            process.executableURL = b.python
            process.environment = b.environment
            process.currentDirectoryURL = b.cwd
        } else {
            let repo = repo ?? Self.repoRoot()
            process.executableURL = URL(
                fileURLWithPath: overridden ?? repo.appendingPathComponent(".venv/bin/python").path)
            process.currentDirectoryURL = repo
        }
        process.arguments = ["-u", "-m", "media_collector", "serve"]
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = Self.logHandle()
        process.terminationHandler = { [weak self] _ in self?.engineEnded() }
    }

    /// Engine stderr (Python tracebacks) goes to ~/Library/Logs/Media Collector/engine.log so a
    /// crash leaves something to report. Restarted when it grows past 1 MB; falls back to discarding.
    static func logHandle() -> FileHandle {
        let fm = FileManager.default
        guard let lib = fm.urls(for: .libraryDirectory, in: .userDomainMask).first else { return .nullDevice }
        let dir = lib.appendingPathComponent("Logs/Media Collector")
        let file = dir.appendingPathComponent("engine.log")
        do {
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
            let size = (try? fm.attributesOfItem(atPath: file.path)[.size] as? Int) ?? 0
            if size > 1_000_000 { try? fm.removeItem(at: file) }
            if !fm.fileExists(atPath: file.path) { fm.createFile(atPath: file.path, contents: nil) }
            let h = try FileHandle(forWritingTo: file)
            try h.seekToEnd()
            return h
        } catch { return .nullDevice }
    }

    func start() async throws {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            lock.lock()
            readyContinuation = c
            lock.unlock()
            do { try process.run() } catch {
                lock.lock(); readyContinuation = nil; lock.unlock()
                c.resume(throwing: EngineError(message: "Could not start the engine: \(error.localizedDescription)"))
                return
            }
            // Blocking pipe reads must not run on Swift's cooperative pool (each engine would pin a
            // pool thread forever); a dedicated thread reads and splits the JSON lines.
            let reader = Thread { [self] in
                let fh = stdoutPipe.fileHandleForReading
                var buffer = Data()
                // availableData returns as soon as any bytes arrive (read(upToCount:) would wait for a full block)
                while true {
                    let chunk = fh.availableData
                    if chunk.isEmpty { break }  // EOF: the engine exited
                    buffer.append(chunk)
                    while let nl = buffer.firstIndex(of: 0x0A) {
                        let lineData = buffer[buffer.startIndex..<nl]
                        buffer.removeSubrange(buffer.startIndex...nl)
                        if let line = String(data: lineData, encoding: .utf8) { handle(line: line) }
                    }
                }
                engineEnded()
            }
            reader.name = "mc-engine-reader"
            reader.start()
        }
    }

    func stop() {
        // EOF makes the engine cancel the running job, clean up partial files and exit by itself;
        // only if it has not done so after a grace period is it terminated.
        try? stdinPipe.fileHandleForWriting.close()
        let p = process
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) { if p.isRunning { p.terminate() } }
    }

    deinit { stop() }

    // MARK: protocol

    private func handle(line: String) {
        guard let data = line.data(using: .utf8),
              let msg = (try? JSONSerialization.jsonObject(with: data)) as? Message else { return }
        if let event = msg["event"] as? String {
            if event == "ready" {
                lock.lock(); isReady = true; let c = readyContinuation; readyContinuation = nil; lock.unlock()
                c?.resume()
            } else {
                eventSink.yield(msg)
            }
            return
        }
        guard let id = msg["id"] as? Int else { return }
        lock.lock(); let c = pending.removeValue(forKey: id); lock.unlock()
        if (msg["ok"] as? Bool) == true {
            c?.resume(returning: (msg["result"] as? Message) ?? [:])
        } else {
            c?.resume(throwing: EngineError(message: (msg["error"] as? String) ?? "Unknown engine error"))
        }
    }

    private func engineEnded() {
        lock.lock()
        if finished { lock.unlock(); return }
        finished = true
        let waiting = pending; pending = [:]
        let ready = readyContinuation; readyContinuation = nil
        lock.unlock()
        let err = EngineError(message: "The engine stopped unexpectedly.")
        ready?.resume(throwing: err)
        for (_, c) in waiting { c.resume(throwing: err) }
        eventSink.finish()
    }

    /// Sends one request and awaits its reply. Long commands are queued one at a time.
    func call(_ cmd: String, _ args: [String: Any] = [:]) async throws -> Message {
        let isLong = ["open_project", "plan", "run"].contains(cmd)
        if isLong { await longJobs.lock() }
        defer { if isLong { Task { await longJobs.unlock() } } }
        return try await send(cmd, args)
    }

    private func send(_ cmd: String, _ args: [String: Any]) async throws -> Message {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Message, Error>) in
            lock.lock()
            if finished { lock.unlock(); c.resume(throwing: EngineError(message: "The engine is not running.")); return }
            let id = nextID; nextID += 1
            pending[id] = c
            lock.unlock()
            var req = args
            req["id"] = id
            req["cmd"] = cmd
            guard var data = try? JSONSerialization.data(withJSONObject: req) else {
                lock.lock(); pending.removeValue(forKey: id); lock.unlock()
                c.resume(throwing: EngineError(message: "Could not encode the request."))
                return
            }
            data.append(0x0A)
            do { try stdinPipe.fileHandleForWriting.write(contentsOf: data) } catch {
                lock.lock(); pending.removeValue(forKey: id); lock.unlock()
                c.resume(throwing: EngineError(message: "Could not talk to the engine."))
            }
        }
    }

    /// Typed convenience: decode the reply's `result` into a Codable wire type.
    func call<T: Decodable>(_ cmd: String, _ args: [String: Any] = [:], as type: T.Type) async throws -> T {
        let result = try await call(cmd, args)
        let data = try JSONSerialization.data(withJSONObject: result)
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(T.self, from: data)
    }
}
