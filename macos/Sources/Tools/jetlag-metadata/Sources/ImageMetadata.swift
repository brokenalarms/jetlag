import Foundation
import ImageIO

enum ImageMetadata {

    private static let imageExtensions: Set<String> = [
        "jpg", "jpeg", "heic", "heif", "dng", "arw", "cr2", "nef", "png", "tif", "tiff"
    ]

    static func canHandle(_ path: String) -> Bool {
        let ext = URL(fileURLWithPath: path).pathExtension.lowercased()
        return imageExtensions.contains(ext)
    }

    // MARK: - Tag name mapping (ExifTool name → ImageIO location)

    private enum TagLocation {
        case exif(String)
        case tiff(String)
    }

    private static func tagLocation(for exiftoolName: String) -> TagLocation? {
        switch exiftoolName {
        case "DateTimeOriginal":
            return .exif(kCGImagePropertyExifDateTimeOriginal as String)
        case "CreateDate":
            return .exif(kCGImagePropertyExifDateTimeDigitized as String)
        case "ModifyDate":
            return .tiff(kCGImagePropertyTIFFDateTime as String)
        case "Make":
            return .tiff(kCGImagePropertyTIFFMake as String)
        case "Model":
            return .tiff(kCGImagePropertyTIFFModel as String)
        default:
            return nil
        }
    }

    // MARK: - Read

    static func readTags(file: String, tags: [String]) -> [String: String] {
        let url = URL(fileURLWithPath: file)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)
                as? [String: Any]
        else { return [:] }

        let exifDict = properties[kCGImagePropertyExifDictionary as String]
            as? [String: Any] ?? [:]
        let tiffDict = properties[kCGImagePropertyTIFFDictionary as String]
            as? [String: Any] ?? [:]

        var result: [String: String] = [:]

        for tag in tags {
            let lookupName: String
            switch tag {
            case "Keys:CreationDate":
                continue
            case "CreationDate":
                lookupName = "DateTimeOriginal"
            default:
                lookupName = tag.contains(":") ? String(tag.split(separator: ":").last!) : tag
            }

            guard let location = tagLocation(for: lookupName) else { continue }

            let value: Any?
            switch location {
            case .exif(let key): value = exifDict[key]
            case .tiff(let key): value = tiffDict[key]
            }

            guard let v = value else { continue }

            let stringValue = "\(v)"

            if tag == "CreationDate" || tag == "DateTimeOriginal" {
                let withTZ = appendTimezone(
                    stringValue,
                    exifDict: exifDict,
                    isOriginal: lookupName == "DateTimeOriginal"
                )
                result[tag] = withTZ
            } else {
                result[tag] = stringValue
            }
        }

        return result
    }

    private static func appendTimezone(
        _ dateStr: String,
        exifDict: [String: Any],
        isOriginal: Bool
    ) -> String {
        let tzKey = isOriginal ? "OffsetTimeOriginal" : "OffsetTimeDigitized"
        if let tz = exifDict[tzKey] as? String, !tz.isEmpty {
            return "\(dateStr)\(tz)"
        }
        return dateStr
    }

    // MARK: - Write

    static func writeTags(file: String, tags: [String: String]) -> Bool {
        let url = URL(fileURLWithPath: file)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let sourceType = CGImageSourceGetType(source)
        else { return false }

        var properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)
            as? [String: Any] ?? [:]
        var exifDict = properties[kCGImagePropertyExifDictionary as String]
            as? [String: Any] ?? [:]
        var tiffDict = properties[kCGImagePropertyTIFFDictionary as String]
            as? [String: Any] ?? [:]

        var changed = false
        for (tag, value) in tags {
            guard let location = tagLocation(for: tag) else { continue }
            switch location {
            case .exif(let key):
                exifDict[key] = value
                changed = true
            case .tiff(let key):
                tiffDict[key] = value
                changed = true
            }
        }

        if !changed { return false }

        properties[kCGImagePropertyExifDictionary as String] = exifDict
        properties[kCGImagePropertyTIFFDictionary as String] = tiffDict

        let tempURL = url.deletingLastPathComponent()
            .appendingPathComponent(".\(UUID().uuidString).\(url.pathExtension)")

        let count = CGImageSourceGetCount(source)
        guard let dest = CGImageDestinationCreateWithURL(
            tempURL as CFURL, sourceType, count, nil
        ) else { return false }

        for i in 0..<count {
            let props = (i == 0) ? properties as CFDictionary : nil
            CGImageDestinationAddImageFromSource(dest, source, i, props)
        }

        guard CGImageDestinationFinalize(dest) else {
            try? FileManager.default.removeItem(at: tempURL)
            return false
        }

        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: file)
            let modDate = attrs[.modificationDate] as? Date
            let createDate = attrs[.creationDate] as? Date

            _ = try FileManager.default.replaceItemAt(url, withItemAt: tempURL)

            var restore: [FileAttributeKey: Any] = [:]
            if let d = modDate { restore[.modificationDate] = d }
            if let d = createDate { restore[.creationDate] = d }
            if !restore.isEmpty {
                try FileManager.default.setAttributes(restore, ofItemAtPath: file)
            }
            return true
        } catch {
            try? FileManager.default.removeItem(at: tempURL)
            return false
        }
    }
}
