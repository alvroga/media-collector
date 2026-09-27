import SwiftUI
import UniformTypeIdentifiers

/// Empty state: one big drop target. Loaded state: the project's name and headline counts.
struct ProjectCard: View {
    @Environment(AppModel.self) private var model
    @State private var isTargeted = false
    @State private var showImporter = false

    var body: some View {
        Group {
            if let project = model.project {
                loaded(project)
            } else {
                dropZone
            }
        }
        .fileImporter(isPresented: $showImporter, allowedContentTypes: [.item, .folder]) { result in
            if case .success(let url) = result { Task { await model.open(url) } }
        }
    }

    private var dropZone: some View {
        VStack(spacing: 14) {
            if model.isLoadingProject { ProgressView().controlSize(.large) }
            Text(model.isLoadingProject ? "Reading project…" : "Drop a project here")
                .font(.title3.weight(.medium))
            FormatRow().padding(.vertical, 2)
            Button("Choose File…") { showImporter = true }
                .disabled(model.isLoadingProject)
                .padding(.top, 2)
            if let error = model.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(Color.orange)
                    .multilineTextAlignment(.leading)
                    .padding(.horizontal, 24)
                    .frame(maxWidth: 520)
            }
        }
        .padding(.vertical, 30)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [7, 5]))
                .foregroundStyle(isTargeted ? Color.accentColor : Color.secondary.opacity(0.5))
        )
        .background(isTargeted ? Color.accentColor.opacity(0.06) : .clear, in: RoundedRectangle(cornerRadius: 14))
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first else { return false }
            Task { await model.open(url) }
            return true
        } isTargeted: { isTargeted = $0 }
    }

    private func loaded(_ project: ProjectSummary) -> some View {
        Card {
            HStack(alignment: .center, spacing: 14) {
                if let f = ProjectFormat(engineName: project.format) {
                    FormatBadge(format: f, size: 46)
                } else {
                    Image(systemName: "film.stack.fill").font(.system(size: 30)).foregroundStyle(Color.accentColor)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(model.projectURL?.deletingPathExtension().lastPathComponent ?? "Project")
                        .font(.title3.weight(.semibold))
                        .lineLimit(1)
                    Text(formatName(project.format)
                         + (project.sequences.isEmpty ? "" : " · \(project.sequences.count) sequence\(project.sequences.count == 1 ? "" : "s")")
                         + " · \(project.originals) media files"
                         + (project.proxies > 0 ? " · \(project.proxies) proxies" : ""))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Change…") { model.closeProject() }
            }
        }
    }
}
