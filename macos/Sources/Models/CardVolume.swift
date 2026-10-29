import Foundation

/// What decides whether a mounted volume is a camera card, without reading
/// anything on volumes that cannot be one. The boot disk and other fixed drives
/// hold the folders macOS guards — Photos, Desktop, other apps' data — and a
/// network share is guarded as a whole, so even listing them would prompt for
/// access nobody asked to give. Folder access is only ever asked for when the
/// user picks a folder.
struct CardVolume {
    let isRootFileSystem: Bool
    let isLocal: Bool
    let isRemovable: Bool
    let isEjectable: Bool

    static let resourceKeys: [URLResourceKey] = [
        .volumeIsRootFileSystemKey, .volumeIsLocalKey, .volumeIsRemovableKey, .volumeIsEjectableKey,
    ]

    /// The folders cameras write at a card's root, matched exactly: a
    /// case-insensitive check would find the boot disk's /private.
    static let cardFolders: Set<String> = ["DCIM", "PRIVATE"]

    init(isRootFileSystem: Bool, isLocal: Bool, isRemovable: Bool, isEjectable: Bool) {
        self.isRootFileSystem = isRootFileSystem
        self.isLocal = isLocal
        self.isRemovable = isRemovable
        self.isEjectable = isEjectable
    }

    init(_ values: URLResourceValues) {
        self.init(isRootFileSystem: values.volumeIsRootFileSystem ?? true,
                  isLocal: values.volumeIsLocal ?? false,
                  isRemovable: values.volumeIsRemovable ?? false,
                  isEjectable: values.volumeIsEjectable ?? false)
    }

    var mayBeCard: Bool { !isRootFileSystem && isLocal && (isRemovable || isEjectable) }

    static func hasCardLayout(topLevelNames: [String]) -> Bool {
        !cardFolders.isDisjoint(with: topLevelNames)
    }

    static func mountedCards() -> [URL] {
        let volumes = FileManager.default.mountedVolumeURLs(
            includingResourceValuesForKeys: resourceKeys, options: [.skipHiddenVolumes]) ?? []
        return volumes.filter { volume in
            guard let values = try? volume.resourceValues(forKeys: Set(resourceKeys)),
                  CardVolume(values).mayBeCard,
                  let names = try? FileManager.default.contentsOfDirectory(atPath: volume.path)
            else { return false }
            return hasCardLayout(topLevelNames: names)
        }
    }
}
