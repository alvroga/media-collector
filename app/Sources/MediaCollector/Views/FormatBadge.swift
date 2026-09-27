import SwiftUI

/// The project formats we read, each with a neutral, original file-type badge. Vendor logos are
/// deliberately not used (trademarks); the colour and extension are enough to tell them apart.
enum ProjectFormat: String, CaseIterable, Identifiable {
    case premiere, otio, fcp7xml, aaf, fcpxml, aep
    var id: String { rawValue }

    init?(engineName: String) { self.init(rawValue: engineName) }

    var displayName: String {
        switch self {
        case .premiere: "Premiere Pro"
        case .fcp7xml: "Final Cut 7 XML"
        case .fcpxml: "Final Cut Pro"
        case .otio: "OpenTimelineIO"
        case .aaf: "AAF"
        case .aep: "After Effects"
        }
    }

    var shortName: String {
        switch self {
        case .premiere: "Premiere"
        case .fcp7xml: "FCP XML"
        case .fcpxml: "FCPXML"
        case .otio: "OTIO"
        case .aaf: "AAF"
        case .aep: "AEP"
        }
    }

    var fileExtension: String {
        switch self {
        case .premiere: "PRPROJ"
        case .fcp7xml: "XML"
        case .fcpxml: "FCPXMLD"
        case .otio: "OTIO"
        case .aaf: "AAF"
        case .aep: "AEP"
        }
    }

    /// The lower-case extension shown under the badge on the drop zone.
    var dottedExtension: String {
        switch self {
        case .premiere: ".prproj"
        case .otio: ".otio"
        case .fcp7xml: ".xml"
        case .aaf: ".aaf"
        case .fcpxml: ".fcpxmld"
        case .aep: ".aep"
        }
    }

    var symbol: String {
        switch self {
        case .premiere: "film"
        case .fcp7xml: "chevron.left.forwardslash.chevron.right"
        case .fcpxml: "film.stack"
        case .otio: "timeline.selection"
        case .aaf: "waveform"
        case .aep: "sparkles.rectangle.stack"
        }
    }

    var tint: Color {
        switch self {
        case .premiere: Color(red: 0.58, green: 0.40, blue: 0.95)
        case .fcp7xml: Color(red: 0.96, green: 0.58, blue: 0.20)
        case .fcpxml: Color(red: 0.16, green: 0.68, blue: 0.72)
        case .otio: Color(red: 0.30, green: 0.72, blue: 0.40)
        case .aaf: Color(red: 0.92, green: 0.34, blue: 0.48)
        case .aep: Color(red: 0.36, green: 0.52, blue: 0.95)
        }
    }
}

/// A little document: folded corner, a symbol, and a coloured label band with the extension.
struct FormatBadge: View {
    let format: ProjectFormat
    var size: CGFloat = 44

    var body: some View {
        let w = size * 0.82, h = size
        ZStack(alignment: .bottom) {
            DocShape(fold: size * 0.26)
                .fill(LinearGradient(colors: [format.tint.opacity(0.95), format.tint.opacity(0.70)],
                                     startPoint: .top, endPoint: .bottom))
            DocShape(fold: size * 0.26)
                .stroke(.white.opacity(0.18), lineWidth: 0.8)
            VStack(spacing: size * 0.05) {
                Image(systemName: format.symbol)
                    .font(.system(size: size * 0.34, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.top, size * 0.16)
                Spacer(minLength: 0)
                Text(format.fileExtension)
                    .font(.system(size: max(6, size * 0.145), weight: .heavy, design: .rounded))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .padding(.horizontal, 2)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, size * 0.05)
                    .background(.black.opacity(0.22))
                    .clipShape(UnevenRoundedRectangle(bottomLeadingRadius: size * 0.10, bottomTrailingRadius: size * 0.10))
            }
            .clipShape(DocShape(fold: size * 0.26))
        }
        .frame(width: w, height: h)
        .shadow(color: .black.opacity(0.25), radius: size * 0.05, y: size * 0.03)
        .accessibilityLabel(format.displayName)
    }
}

private struct DocShape: Shape {
    var fold: CGFloat
    func path(in r: CGRect) -> Path {
        let c = r.width * 0.12
        var p = Path()
        p.move(to: CGPoint(x: r.minX + c, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - fold, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.minY + fold))
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - c))
        p.addQuadCurve(to: CGPoint(x: r.maxX - c, y: r.maxY), control: CGPoint(x: r.maxX, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX + c, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.maxY - c), control: CGPoint(x: r.minX, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + c))
        p.addQuadCurve(to: CGPoint(x: r.minX + c, y: r.minY), control: CGPoint(x: r.minX, y: r.minY))
        p.closeSubpath()
        return p
    }
}

/// The five supported formats in a row, for the empty state.
struct FormatRow: View {
    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            ForEach(ProjectFormat.allCases) { f in
                VStack(spacing: 6) {
                    FormatBadge(format: f, size: 40)
                    Text(f.dottedExtension).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                }
            }
        }
    }
}
