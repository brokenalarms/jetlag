import Foundation

/// Asks probe-camera what camera shot the media at a path, so the camera is
/// always read from files by the scripts rather than typed in or re-derived here.
enum CameraProbe {
    static func probe(path: String, extensions: [String]? = nil,
                      launcher: any ScriptLaunching) async -> [ProbedCamera] {
        guard FileManager.default.fileExists(atPath: path) else { return [] }
        var args = [path]
        if let extensions, !extensions.isEmpty {
            args += ["--extensions"] + extensions
        }
        let (process, stream) = launcher.run(script: "probe-camera.sh", args: args)
        var found: [ProbedCamera] = []
        for await line in stream where line.stream == .stdout && line.isMachineReadable {
            if let data = line.text.data(using: .utf8),
               let probed = try? JSONDecoder().decode(ProbedCamera.self, from: data) {
                found.append(probed)
            }
        }
        process.waitUntilExit()
        return found
    }
}
