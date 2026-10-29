import Foundation

/// A camera and the kind of media it shot: what a profile is. One camera has
/// a photo profile and a video profile, never two of either. Case is ignored, as
/// the pipeline ignores it: cameras write SONY where a profile may say Sony.
struct CameraKind: Hashable {
    let camera: FileCamera
    let type: MediaType

    init?(camera: FileCamera?, type: MediaType) {
        guard let camera else { return nil }
        self.camera = camera
        self.type = type
    }

    init?(profile: MediaProfile) {
        self.init(camera: FileCamera(make: profile.exif?.make, model: profile.exif?.model),
                  type: profile.type ?? .video)
    }

    private var identity: [String] {
        [camera.make?.lowercased() ?? "", camera.model?.lowercased() ?? "", type.rawValue]
    }

    static func == (lhs: CameraKind, rhs: CameraKind) -> Bool { lhs.identity == rhs.identity }
    func hash(into hasher: inout Hasher) { hasher.combine(identity) }

    /// A profile's default name: its camera and kind of media.
    var defaultProfileName: String { "\(camera.name) \(type.label)" }
}

/// What a card holds, measured against the profiles there are.
struct CardContents: Equatable {
    struct Match: Equatable {
        let profileName: String
        let folder: String
    }

    struct NewCamera: Equatable {
        let kind: CameraKind
        let folder: String
        let extensions: [String]
    }

    /// Profiles whose camera shot media on the card, and the folder it is in.
    var matched: [Match] = []
    /// Camera kinds on the card that no profile has yet.
    var newCameras: [NewCamera] = []
    /// Folders holding media that records no camera at all.
    var cameralessFolders: [String] = []

    var isEmpty: Bool { matched.isEmpty && newCameras.isEmpty && cameralessFolders.isEmpty }
}

enum ProfileMatcher {

    static func contents(of probes: [ProbedCamera], profiles: [String: MediaProfile]) -> CardContents {
        var contents = CardContents()
        for probe in probes.sorted(by: { $0.files > $1.files }) {
            guard let kind = CameraKind(camera: probe.camera, type: probe.type) else {
                if !contents.cameralessFolders.contains(probe.folder) {
                    contents.cameralessFolders.append(probe.folder)
                }
                continue
            }
            if let name = profileName(for: kind, in: profiles) {
                if !contents.matched.contains(where: { $0.profileName == name }) {
                    contents.matched.append(.init(profileName: name, folder: probe.folder))
                }
            } else if let index = contents.newCameras.firstIndex(where: { $0.kind == kind }) {
                let existing = contents.newCameras[index]
                contents.newCameras[index] = .init(kind: kind, folder: existing.folder,
                                                   extensions: (existing.extensions + [probe.fileExtension]).sorted())
            } else {
                contents.newCameras.append(.init(kind: kind, folder: probe.folder, extensions: [probe.fileExtension]))
            }
        }
        return contents
    }

    static func profileName(for kind: CameraKind, in profiles: [String: MediaProfile]) -> String? {
        profiles.keys.sorted().first { CameraKind(profile: profiles[$0]!) == kind }
    }

    /// Profiles sharing a camera kind with another. Each kind is meant to have
    /// one profile; these predate that and are left for the user to resolve.
    static func duplicates(in profiles: [String: MediaProfile]) -> Set<String> {
        let byKind = Dictionary(grouping: profiles.keys) { CameraKind(profile: profiles[$0]!) }
        return Set(byKind.filter { $0.key != nil && $0.value.count > 1 }.values.joined())
    }
}
