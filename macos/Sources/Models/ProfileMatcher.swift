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

/// What the folder chosen as a new profile's source holds, measured against the
/// profiles there are.
struct SourceContents: Equatable {
    struct NewCamera: Equatable {
        let kind: CameraKind
        let source: String
        let extensions: [String]
    }

    /// Profiles that already exist for a camera kind found in the source.
    var existingProfiles: [String] = []
    /// Camera kinds found in the source that no profile has yet.
    var newCameras: [NewCamera] = []
    /// Whether some of the source's media records no camera at all.
    var hasCameralessMedia = false
}

enum ProfileMatcher {

    static func contents(of probes: [ProbedCamera], source: String,
                         profiles: [String: MediaProfile]) -> SourceContents {
        var contents = SourceContents()
        for probe in probes.sorted(by: { $0.files > $1.files }) {
            guard let kind = CameraKind(camera: probe.camera, type: probe.type) else {
                contents.hasCameralessMedia = true
                continue
            }
            if let name = profileName(for: kind, in: profiles) {
                if !contents.existingProfiles.contains(name) {
                    contents.existingProfiles.append(name)
                }
            } else if let index = contents.newCameras.firstIndex(where: { $0.kind == kind }) {
                let existing = contents.newCameras[index]
                contents.newCameras[index] = .init(kind: kind, source: source,
                                                   extensions: (existing.extensions + [probe.fileExtension]).sorted())
            } else {
                contents.newCameras.append(.init(kind: kind, source: source, extensions: [probe.fileExtension]))
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
