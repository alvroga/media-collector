import SwiftUI

/// The numbers: always visible so every option change has a visible effect.
struct SummaryCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if model.project != nil {
            Card {
                if let plan = model.plan {
                    HStack(alignment: .firstTextBaseline, spacing: 22) {
                        stat("\(plan.files)", "files")
                        stat(plan.bytes.byteString, "to copy")
                        if plan.proxies > 0 { stat("\(plan.proxies)", "proxies") }
                        Spacer()
                        if model.isPlanning { ProgressView().controlSize(.small) }
                    }
                    if plan.missing.count > 0 { missing(plan) }
                    if plan.cacheSkipped > 0 {
                        note("\(plan.cacheSkipped) cache files (previews, media cache) are never copied", "shippingbox")
                    }
                    if plan.renamedOnCollision > 0 {
                        note("\(plan.renamedOnCollision) files share a name and get a _2 suffix", "doc.on.doc")
                    }
                    if (plan.unusable ?? 0) > 0 {
                        note("\(plan.unusable ?? 0) references have no usable file name and are left out", "questionmark.folder", warn: true)
                    }
                    ForEach(plan.unmappedPrefixes) { p in
                        note("\(p.prefix) (\(p.files) files) needs a location on this Mac", "externaldrive.badge.questionmark", warn: true)
                    }
                } else if model.isPlanning {
                    HStack { ProgressView().controlSize(.small); Text("Working out what to copy…").foregroundStyle(.secondary) }
                }
                if let n = model.project?.nonFileSkipped, n > 0 {
                    note("\(n) references in the project are not files on disk (web links, generated media) and are ignored", "link")
                }
                ForEach(model.project?.warnings ?? [], id: \.self) { note($0, "exclamationmark.triangle", warn: true) }
                if let error = model.errorMessage {
                    note(error, "xmark.octagon", warn: true)
                }
            }
        }
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.system(size: 26, weight: .semibold, design: .rounded)).monospacedDigit()
            Text(label).font(.callout).foregroundStyle(.secondary)
        }
    }

    private func note(_ text: String, _ symbol: String, warn: Bool = false) -> some View {
        Label(text, systemImage: symbol)
            .font(.callout)
            .foregroundStyle(warn ? Color.orange : .secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func missing(_ plan: PlanSummary) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 3) {
                ForEach(plan.missing.items) { item in
                    Text(item.path)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                if plan.missing.count > plan.missing.items.count {
                    Text("…and \(plan.missing.count - plan.missing.items.count) more").font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(.top, 4)
        } label: {
            Label("\(plan.missing.count) files can't be found", systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(Color.orange)
        }
    }
}
