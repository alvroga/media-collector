import SwiftUI

/// What to copy and how far up the folder tree to trim. Everything here re-plans live.
/// The folder structure itself is always kept (no flatten switch, by design).
struct OptionsCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        if let project = model.project {
            Card(title: "Options", symbol: "slider.horizontal.3") {
                Picker("Media", selection: $model.options.includeUnused) {
                    Text("Used media").tag(false)
                    Text("All media").tag(true)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: .infinity)
                .help("Used media is only what the timelines use. All media also includes clips that were imported but never edited in.")

                if project.proxies > 0 {
                    Toggle(isOn: $model.options.includeProxies) {
                        Label("Include proxies", systemImage: "square.stack.3d.down.right")
                    }
                }

                Divider()

                Stepper(value: $model.options.skipLevels, in: 0...30) {
                    Text("Keep folders, skipping the first **\(model.options.skipLevels)** \(model.options.skipLevels == 1 ? "level" : "levels")")
                }
                examplePreview

                Divider()

                Toggle(isOn: $model.relink) {
                    Label("Relink the project to the copied files", systemImage: "link")
                }
                .disabled(!project.canRelink)
                .help("Also writes a new copy of the project, with every media path pointing at the copied files. The original project is never changed.")
                if !project.canRelink {
                    Text("Relinking isn't available for \(formatName(project.format)) projects.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .padding(.leading, 26)
                }
            }
        }
    }

    /// A real path from this project, as it will land: folders disappear from the front as the number of
    /// skipped levels goes up.
    private var examplePreview: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("Example")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "folder").foregroundStyle(.secondary)
                Text(exampleText)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                    .truncationMode(.head)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var exampleText: String {
        guard let rel = model.plan?.examples.first?.destRel else { return "—" }
        return (model.destination.map { $0.lastPathComponent + "/" } ?? "") + rel
    }
}
