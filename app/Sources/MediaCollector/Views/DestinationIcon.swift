import AppKit

/// What kind of place a destination is, with the icon macOS itself uses for that volume, so an
/// external drive, a NAS and the internal disk are recognisable at a glance.
struct DestinationInfo {
    enum Kind {
        case internalDisk, externalDrive, network
        var label: String {
            switch self {
            case .internalDisk: "Internal disk"
            case .externalDrive: "External drive"
            case .network: "Network volume"
            }
        }
    }

    let kind: Kind
    let volumeName: String
    let icon: NSImage

    static func info(for url: URL) -> DestinationInfo? {
        let keys: Set<URLResourceKey> = [.volumeURLKey, .volumeNameKey, .volumeIsLocalKey,
                                         .volumeIsInternalKey]
        guard let v = try? url.resourceValues(forKeys: keys), let volumeURL = v.volume else { return nil }
        let kind: Kind = (v.volumeIsLocal == false) ? .network
            : (v.volumeIsInternal == true ? .internalDisk : .externalDrive)
        return DestinationInfo(kind: kind, volumeName: v.volumeName ?? volumeURL.lastPathComponent,
                               icon: NSWorkspace.shared.icon(forFile: volumeURL.path))
    }
}
