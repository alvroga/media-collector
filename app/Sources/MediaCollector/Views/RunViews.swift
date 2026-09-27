import SwiftUI

/// Bottom bar on the setup screen: the headline numbers and the Start button.
struct StartBar: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if model.project != nil {
            HStack(spacing: 14) {
                Text(summary).font(.callout).foregroundStyle(.secondary)
                Spacer()
                Button {
                    Task { await model.start() }
                } label: {
                    Text("Start").frame(minWidth: 90)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .keyboardShortcut(.defaultAction)
                .disabled(!model.canStart)
                .help(model.destination == nil ? "Choose a destination first" : "Copy the media")
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(.bar)
            .overlay(alignment: .top) { Divider() }
        }
    }

    private var summary: String {
        guard model.destination != nil else { return "Choose a destination to begin" }
        guard let plan = model.plan else { return "Working out what to copy…" }
        let to = model.destination.map { " → \($0.lastPathComponent)" } ?? ""
        return plan.files == 0 ? "Nothing to copy with these settings" : "\(plan.files) files · \(plan.bytes.byteString)\(to)"
    }
}

/// While copying: one progress bar, what is happening, Cancel.
struct RunningView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 18) {
            Spacer()
            Image(systemName: "arrow.down.doc.fill")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(Color.accentColor)
                .symbolEffect(.pulse, options: .repeating)  // gentle "still working" cue
            Text(model.isCancelling ? "Cancelling…" : "Copying…").font(.title2.weight(.semibold))
            if model.isCancelling {
                Text("Stopping after the current transfer. Files that are only partly copied are removed; finished ones are kept.")
                    .font(.callout).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).frame(maxWidth: 420)
            }
            if let p = model.progress {
                VStack(spacing: 8) {
                    ActivityBar(fraction: p.fraction, active: !model.isCancelling)
                    HStack {
                        Text(p.name).lineLimit(1).truncationMode(.middle)
                        Spacer()
                        Text("\(Int(p.fraction * 100))%").monospacedDigit()
                    }
                    .font(.callout)
                    Text("File \(min(p.fileIndex + 1, p.fileCount)) of \(p.fileCount) · \(phaseText(p.phase))")
                        .font(.caption).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxWidth: 420)
            } else {
                ProgressView().controlSize(.large)
            }
            if let started = model.runStartedAt {
                // Ticks every second, so a long file or a slow network never looks frozen.
                TimelineView(.periodic(from: started, by: 1)) { ctx in
                    Text("Elapsed \(Self.clock(ctx.date.timeIntervalSince(started)))")
                        .font(.callout).monospacedDigit().foregroundStyle(.secondary)
                }
            }
            if !model.recentFiles.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(model.recentFiles.enumerated()), id: \.offset) { _, name in
                        Label(name, systemImage: "checkmark.circle.fill")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .symbolRenderingMode(.multicolor)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                .frame(maxWidth: 420, alignment: .leading)
            }
            Button("Cancel") { model.cancelRun() }
                .disabled(model.isCancelling)
            Spacer()
        }
        .padding(30)
        .frame(maxWidth: .infinity)
    }

    static func clock(_ seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        return s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, s % 3600 / 60, s % 60)
                         : String(format: "%d:%02d", s / 60, s % 60)
    }

    private func phaseText(_ phase: String) -> String {
        switch phase {
        case "copying": "copying"
        case "verifying": "verifying"
        case "checking": "checking existing file"
        default: "working"
        }
    }
}

/// When the copy ends: what happened, what needs attention, and what to do next.
struct ReportView: View {
    @Environment(AppModel.self) private var model
    let report: RunReport

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                Image(systemName: icon).font(.system(size: 46)).foregroundStyle(color)
                Text(headline).font(.title2.weight(.semibold))

                Card {
                    HStack(spacing: 26) {
                        stat("\(report.copied)", "copied")
                        if report.skippedIdentical > 0 { stat("\(report.skippedIdentical)", "already there") }
                        stat(report.bytes.byteString, "total")
                        Spacer()
                    }
                    if let c = report.projectCopy { projectCopyLine(c) }
                    if let r = report.relink { relinkLines(r) }
                }

                if !report.problems.isEmpty {
                    Card(title: "Needs attention") {
                        ForEach(report.problems) { p in
                            VStack(alignment: .leading, spacing: 1) {
                                Label(p.status.capitalized, systemImage: "exclamationmark.triangle.fill")
                                    .foregroundStyle(Color.orange).font(.callout.weight(.medium))
                                Text(p.path).font(.system(.caption, design: .monospaced))
                                    .foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                                if !p.detail.isEmpty { Text(p.detail).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                    }
                }

                HStack(spacing: 10) {
                    if let dest = model.destination {
                        Button("Reveal in Finder") { NSWorkspace.shared.activateFileViewerSelecting([dest]) }
                    }
                    if let project = report.relinkedProject {
                        Button("Show Relinked Project") {
                            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: project)])
                        }
                    }
                    Spacer()
                    Button("Done") { model.finishRun() }
                        .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                }
            }
            .padding(20)
        }
    }

    private var icon: String {
        report.cancelled ? "xmark.circle.fill" : report.ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
    }
    private var color: Color { report.cancelled ? .secondary : report.ok ? .green : .orange }
    private var headline: String {
        report.cancelled ? "Cancelled — files already copied were kept" : report.ok ? "Copy complete" : "Copied with problems"
    }

    @ViewBuilder private func projectCopyLine(_ c: ProjectCopy) -> some View {
        let name = URL(fileURLWithPath: c.path).lastPathComponent
        if c.status == "copied" {
            Label("Original project copied: \(name)" + (c.detail.isEmpty ? "" : " (\(c.detail))"), systemImage: "doc.on.doc")
                .font(.callout).foregroundStyle(.secondary)
        } else {
            Label("Original project not copied (\(c.detail.isEmpty ? c.status : c.detail)): \(name)", systemImage: "doc.on.doc")
                .font(.callout).foregroundStyle(.orange)
        }
    }

    @ViewBuilder private func relinkLines(_ r: RelinkSummary) -> some View {
        if let n = r.relinked, let total = r.mediaObjects {
            Label("Project relinked: \(n) of \(total) media references now point at the copies",
                  systemImage: "link").font(.callout)
            if (r.leftUnchanged ?? 0) > 0 {
                Label("\(r.leftUnchanged ?? 0) references were not copied and still point at their original location"
                      + leftBehindReason, systemImage: "info.circle").font(.callout).foregroundStyle(.secondary)
            }
        }
        if let why = r.skipped { Label("Project not relinked: \(why)", systemImage: "link.badge.plus").font(.callout).foregroundStyle(.orange) }
        if let e = r.error { Label("Project not relinked: \(e)", systemImage: "link.badge.plus").font(.callout).foregroundStyle(.orange) }
        ForEach(r.notes ?? [], id: \.self) { Label($0, systemImage: "info.circle").font(.callout).foregroundStyle(.secondary) }
    }

    /// Why some references stayed behind, when we can tell from the settings that were used.
    private var leftBehindReason: String {
        let proxies = model.project?.proxies ?? 0
        if proxies > 0 && !model.options.includeProxies { return " — the project has \(proxies) proxies; turn on “Include proxies” to copy them" }
        if !model.options.includeUnused { return " (media the timelines don't use is skipped unless you choose “All media”)" }
        return ""
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.system(size: 24, weight: .semibold, design: .rounded)).monospacedDigit()
            Text(label).font(.callout).foregroundStyle(.secondary)
        }
    }
}

/// A progress bar that visibly "hums" while a copy runs, even when the percentage sits still (one huge file,
/// a slow network share): the filled part breathes, and a soft band of light blue travels along the whole track,
/// so there is motion at 2% just as at 90%.
struct ActivityBar: View {
    var fraction: Double
    var active: Bool
    /// Light blue, so the moving band reads as part of the blue bar rather than a white flash.
    private static let glow = Color(red: 0.55, green: 0.82, blue: 1.0)

    var body: some View {
        GeometryReader { geo in
            TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: !active)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate
                let width = geo.size.width
                let filled = max(16, width * fraction)
                let breathe = active ? 0.8 + 0.2 * sin(t * 2 * .pi / 1.2) : 1.0
                let sweep = t.truncatingRemainder(dividingBy: 1.8) / 1.8  // 0...1, then starts over
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.primary.opacity(0.1))
                    Capsule().fill(Color.accentColor).frame(width: filled).opacity(breathe)
                    if active {
                        LinearGradient(colors: [.clear, Self.glow.opacity(0.75), .clear],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: 110)
                            .offset(x: sweep * (width + 110) - 110)
                    }
                }
                .clipShape(Capsule())
                .animation(.easeOut(duration: 0.25), value: filled)
            }
        }
        .frame(height: 10)
        .accessibilityElement()
        .accessibilityLabel("Copy progress")
        .accessibilityValue("\(Int(fraction * 100)) percent")
    }
}
