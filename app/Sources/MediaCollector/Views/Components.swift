import SwiftUI

/// Window and card colours, chosen so the cards clearly stand off the background in both appearances.
enum Theme {
    static func window(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.075, green: 0.075, blue: 0.085) : Color(red: 0.925, green: 0.925, blue: 0.94)
    }
    static func card(_ scheme: ColorScheme) -> Color {
        scheme == .dark ? Color(red: 0.16, green: 0.16, blue: 0.175) : .white
    }
}

/// A calm rounded panel; the only container style in the app.
struct Card<Content: View>: View {
    @Environment(\.colorScheme) private var scheme
    var title: String?
    var symbol: String?
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title {
                HStack(spacing: 6) {
                    if let symbol { Image(systemName: symbol) }
                    Text(title.uppercased()).tracking(0.6)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            }
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Theme.card(scheme), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color.primary.opacity(scheme == .dark ? 0.09 : 0.07), lineWidth: 1)
        )
        .shadow(color: .black.opacity(scheme == .dark ? 0.0 : 0.06), radius: 3, y: 1)
    }
}

func formatName(_ format: String) -> String {
    switch format {
    case "premiere": "Premiere Pro"
    case "fcp7xml": "Final Cut Pro 7 XML"
    case "fcpxml": "Final Cut Pro (FCPXML)"
    case "otio": "OpenTimelineIO"
    case "aaf": "AAF"
    case "aep": "After Effects"
    default: format
    }
}
