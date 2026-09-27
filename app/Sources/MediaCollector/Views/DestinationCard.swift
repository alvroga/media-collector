import SwiftUI

/// Where the copy goes. Sits right under the project so the flow reads top to bottom.
struct DestinationCard: View {
    @Environment(AppModel.self) private var model
    @State private var isTargeted = false

    var body: some View {
        if model.project != nil {
            Card(title: "Copy to", symbol: "externaldrive") {
                HStack(spacing: 12) {
                    icon
                    VStack(alignment: .leading, spacing: 2) {
                        if let dest = model.destination {
                            Text(dest.lastPathComponent).font(.headline).lineLimit(1)
                            Text(subtitle(for: dest))
                                .font(.caption).foregroundStyle(.secondary)
                                .lineLimit(1).truncationMode(.middle)
                        } else {
                            Text("Choose a destination folder").font(.headline)
                            Text("or drop a folder here").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Button(model.destination == nil ? "Choose…" : "Change…", action: choose)
                }
                if let free = model.freeSpace {
                    Text("\(free.byteString) free" + (model.notEnoughSpace ? " — not enough space for this copy" : ""))
                        .font(.callout)
                        .foregroundStyle(model.notEnoughSpace ? Color.orange : .secondary)
                }
            }
            .overlay(
                RoundedRectangle(cornerRadius: 12).strokeBorder(Color.accentColor, lineWidth: isTargeted ? 2 : 0)
            )
            .dropDestination(for: URL.self) { urls, _ in
                guard let url = urls.first,
                      (try? url.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory == true else { return false }
                model.destination = url
                return true
            } isTargeted: { isTargeted = $0 }
        }
    }

    /// The macOS icon of the destination's volume (drive, NAS, internal disk), or a plain folder badge.
    @ViewBuilder private var icon: some View {
        if let dest = model.destination, let info = DestinationInfo.info(for: dest) {
            Image(nsImage: info.icon).resizable().interpolation(.high).frame(width: 40, height: 40)
        } else {
            Image(systemName: "folder.badge.plus").font(.title).foregroundStyle(.secondary).frame(width: 40, height: 40)
        }
    }

    private func subtitle(for dest: URL) -> String {
        guard let info = DestinationInfo.info(for: dest) else { return dest.deletingLastPathComponent().path }
        return "\(info.kind.label) · \(info.volumeName)"
    }

    private func choose() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Choose"
        panel.message = "Choose where to copy the media"
        if panel.runModal() == .OK { model.destination = panel.url }
    }
}
