import Foundation

func emitJSON(_ value: Any) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
        print(String(data: data, encoding: .utf8) ?? "{}")
    } else {
        print("{}")
    }
    fflush(stdout)
}

while let line = readLine() {
    let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty { continue }

    guard let data = trimmed.data(using: .utf8),
          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let op = json["op"] as? String,
          let file = json["file"] as? String
    else {
        emitJSON([:] as [String: String])
        continue
    }

    switch op {
    case "read":
        guard let tags = json["tags"] as? [String] else {
            emitJSON([:] as [String: String])
            continue
        }
        if ImageMetadata.canHandle(file) {
            emitJSON(ImageMetadata.readTags(file: file, tags: tags))
        } else if QuickTimeMetadata.canHandle(file) {
            emitJSON(QuickTimeMetadata.readTags(file: file, tags: tags))
        } else {
            emitJSON([:] as [String: String])
        }

    case "write":
        guard let tags = json["tags"] as? [String: String] else {
            emitJSON([:] as [String: String])
            continue
        }
        let updated: Bool
        if ImageMetadata.canHandle(file) {
            updated = ImageMetadata.writeTags(file: file, tags: tags)
        } else if QuickTimeMetadata.canHandle(file) {
            updated = QuickTimeMetadata.writeTags(file: file, tags: tags)
        } else {
            updated = false
        }
        emitJSON(["updated": updated, "files_changed": updated ? 1 : 0] as [String: Any])

    default:
        emitJSON([:] as [String: String])
    }
}
