import Foundation

enum QuickTimeMetadata {

    private static let videoExtensions: Set<String> = ["mov", "mp4", "m4v", "m4a"]

    static func canHandle(_ path: String) -> Bool {
        let ext = URL(fileURLWithPath: path).pathExtension.lowercased()
        return videoExtensions.contains(ext)
    }

    // Seconds between 1904-01-01 and 1970-01-01
    private static let qtEpochOffset: UInt64 = 2_082_844_800

    // MARK: - Read

    static func readTags(file: String, tags: [String]) -> [String: String] {
        guard let handle = FileHandle(forReadingAtPath: file) else { return [:] }
        defer { handle.closeFile() }

        let fileSize = handle.seekToEndOfFile()
        handle.seek(toFileOffset: 0)

        guard let moov = findAtom(in: handle, type: "moov", range: 0..<fileSize) else {
            return [:]
        }

        let requested = Set(tags)
        var result: [String: String] = [:]

        if requested.contains("CreateDate") || requested.contains("ModifyDate") {
            if let mvhd = findAtom(in: handle, type: "mvhd", range: moov.contentRange) {
                let ts = readTimestampAtom(handle, atom: mvhd)
                if requested.contains("CreateDate") {
                    result["CreateDate"] = formatQTTimestamp(ts.creation)
                }
                if requested.contains("ModifyDate") {
                    result["ModifyDate"] = formatQTTimestamp(ts.modification)
                }
            }
        }

        let needsMedia = requested.contains("QuickTime:MediaCreateDate")
            || requested.contains("QuickTime:MediaModifyDate")
        if needsMedia {
            if let mdhd = findFirstMdhd(in: handle, moovRange: moov.contentRange) {
                let ts = readTimestampAtom(handle, atom: mdhd)
                if requested.contains("QuickTime:MediaCreateDate") {
                    result["MediaCreateDate"] = formatQTTimestamp(ts.creation)
                }
                if requested.contains("QuickTime:MediaModifyDate") {
                    result["MediaModifyDate"] = formatQTTimestamp(ts.modification)
                }
            }
        }

        let needsMdta = requested.contains("CreationDate")
            || requested.contains("Keys:CreationDate")
            || requested.contains("DateTimeOriginal")
            || requested.contains("Make")
            || requested.contains("Model")
        if needsMdta {
            let mdta = readMdtaKeys(in: handle, moovRange: moov.contentRange)
            for alias in ["CreationDate", "Keys:CreationDate", "DateTimeOriginal"] where requested.contains(alias) {
                if let v = mdta["com.apple.quicktime.creationdate"] {
                    result[alias] = exifStyleDate(v)
                }
            }
            if requested.contains("Make"), let v = mdta["com.apple.quicktime.make"] {
                result["Make"] = v
            }
            if requested.contains("Model"), let v = mdta["com.apple.quicktime.model"] {
                result["Model"] = v
            }
        }

        return result
    }

    // MARK: - Write

    static func writeTags(file: String, tags: [String: String]) -> Bool {
        guard FileManager.default.isWritableFile(atPath: file) else { return false }

        var changed = false

        // Pass 1: in-place timestamp patches (via FileHandle, before any full rewrite)
        if let handle = try? FileHandle(forUpdating: URL(fileURLWithPath: file)) {
            let fileSize = handle.seekToEndOfFile()
            handle.seek(toFileOffset: 0)
            if let moov = findAtom(in: handle, type: "moov", range: 0..<fileSize) {
                for (tag, value) in tags {
                    let normalized = normalizeTagName(tag)
                    switch normalized {
                    case "QuickTime:CreateDate":
                        if let mvhd = findAtom(in: handle, type: "mvhd", range: moov.contentRange) {
                            if writeTimestampAtom(handle, atom: mvhd, creation: value, modification: nil) {
                                changed = true
                            }
                        }
                    case "QuickTime:MediaCreateDate":
                        if let mdhd = findFirstMdhd(in: handle, moovRange: moov.contentRange) {
                            if writeTimestampAtom(handle, atom: mdhd, creation: value, modification: nil) {
                                changed = true
                            }
                        }
                    default:
                        break
                    }
                }
            }
            handle.closeFile()
        }

        // Pass 2: mdta key writes (full file rewrite)
        for (tag, value) in tags {
            let normalized = normalizeTagName(tag)
            switch normalized {
            case "DateTimeOriginal", "Keys:CreationDate":
                if writeMdtaKey(file: file, key: "com.apple.quicktime.creationdate", value: isoDate(value)) {
                    changed = true
                }
            case "Make":
                if writeMdtaKey(file: file, key: "com.apple.quicktime.make", value: value) {
                    changed = true
                }
            case "Model":
                if writeMdtaKey(file: file, key: "com.apple.quicktime.model", value: value) {
                    changed = true
                }
            default:
                break
            }
        }

        return changed
    }

    private static func normalizeTagName(_ tag: String) -> String {
        let lower = tag.replacingOccurrences(of: "_", with: "").lowercased()
        switch lower {
        case "createdate": return "QuickTime:CreateDate"
        case "mediacreatedate": return "QuickTime:MediaCreateDate"
        default: return tag
        }
    }

    // MARK: - Atom parsing

    private struct Atom {
        let offset: UInt64
        let size: UInt64
        let headerSize: Int
        let type: String

        var contentRange: Range<UInt64> {
            (offset + UInt64(headerSize))..<(offset + size)
        }
    }

    private static func findAtom(
        in handle: FileHandle,
        type target: String,
        range: Range<UInt64>
    ) -> Atom? {
        var pos = range.lowerBound
        while pos < range.upperBound {
            guard let atom = readAtomHeader(handle, at: pos, limit: range.upperBound) else {
                break
            }
            if atom.type == target { return atom }
            pos = atom.offset + atom.size
        }
        return nil
    }

    private static func findAtoms(
        in handle: FileHandle,
        type target: String,
        range: Range<UInt64>
    ) -> [Atom] {
        var result: [Atom] = []
        var pos = range.lowerBound
        while pos < range.upperBound {
            guard let atom = readAtomHeader(handle, at: pos, limit: range.upperBound) else {
                break
            }
            if atom.type == target { result.append(atom) }
            pos = atom.offset + atom.size
        }
        return result
    }

    private static func readAtomHeader(
        _ handle: FileHandle,
        at offset: UInt64,
        limit: UInt64
    ) -> Atom? {
        guard offset + 8 <= limit else { return nil }
        handle.seek(toFileOffset: offset)
        let header = handle.readData(ofLength: 8)
        guard header.count == 8 else { return nil }

        let size32 = header.uint32BE(at: 0)
        let type = header.fourCC(at: 4)

        var totalSize: UInt64
        var headerSize = 8

        if size32 == 1 {
            // 64-bit extended size
            let ext = handle.readData(ofLength: 8)
            guard ext.count == 8 else { return nil }
            totalSize = ext.uint64BE(at: 0)
            headerSize = 16
        } else if size32 == 0 {
            totalSize = limit - offset
        } else {
            totalSize = UInt64(size32)
        }

        guard totalSize >= UInt64(headerSize), offset + totalSize <= limit else { return nil }
        return Atom(offset: offset, size: totalSize, headerSize: headerSize, type: type)
    }

    // MARK: - Timestamp atoms (mvhd / mdhd)

    private static func findFirstMdhd(
        in handle: FileHandle,
        moovRange: Range<UInt64>
    ) -> Atom? {
        for trak in findAtoms(in: handle, type: "trak", range: moovRange) {
            if let mdia = findAtom(in: handle, type: "mdia", range: trak.contentRange),
               let mdhd = findAtom(in: handle, type: "mdhd", range: mdia.contentRange) {
                return mdhd
            }
        }
        return nil
    }

    private struct RawTimestamps {
        var creation: UInt64 = 0
        var modification: UInt64 = 0
    }

    private static func readTimestampAtom(_ handle: FileHandle, atom: Atom) -> RawTimestamps {
        handle.seek(toFileOffset: atom.offset + UInt64(atom.headerSize))
        let versionFlags = handle.readData(ofLength: 4)
        guard versionFlags.count == 4 else { return RawTimestamps() }

        let version = versionFlags[0]
        var ts = RawTimestamps()

        if version == 1 {
            let data = handle.readData(ofLength: 16)
            guard data.count == 16 else { return ts }
            ts.creation = data.uint64BE(at: 0)
            ts.modification = data.uint64BE(at: 8)
        } else {
            let data = handle.readData(ofLength: 8)
            guard data.count == 8 else { return ts }
            ts.creation = UInt64(data.uint32BE(at: 0))
            ts.modification = UInt64(data.uint32BE(at: 4))
        }

        return ts
    }

    private static func writeTimestampAtom(
        _ handle: FileHandle,
        atom: Atom,
        creation: String?,
        modification: String?
    ) -> Bool {
        handle.seek(toFileOffset: atom.offset + UInt64(atom.headerSize))
        let versionFlags = handle.readData(ofLength: 4)
        guard versionFlags.count == 4 else { return false }

        let version = versionFlags[0]
        let tsFieldOffset = atom.offset + UInt64(atom.headerSize) + 4

        if version == 1 {
            let existing = handle.readData(ofLength: 16)
            guard existing.count == 16 else { return false }
            var bytes = [UInt8](existing)

            if let c = creation, let qtVal = parseToQTTimestamp(c) {
                var v = qtVal.bigEndian
                withUnsafeBytes(of: &v) { bytes.replaceSubrange(0..<8, with: $0) }
            }
            if let m = modification, let qtVal = parseToQTTimestamp(m) {
                var v = qtVal.bigEndian
                withUnsafeBytes(of: &v) { bytes.replaceSubrange(8..<16, with: $0) }
            }

            handle.seek(toFileOffset: tsFieldOffset)
            handle.write(Data(bytes))
        } else {
            let existing = handle.readData(ofLength: 8)
            guard existing.count == 8 else { return false }
            var bytes = [UInt8](existing)

            if let c = creation, let qtVal = parseToQTTimestamp(c) {
                var v = UInt32(clamping: qtVal).bigEndian
                withUnsafeBytes(of: &v) { bytes.replaceSubrange(0..<4, with: $0) }
            }
            if let m = modification, let qtVal = parseToQTTimestamp(m) {
                var v = UInt32(clamping: qtVal).bigEndian
                withUnsafeBytes(of: &v) { bytes.replaceSubrange(4..<8, with: $0) }
            }

            handle.seek(toFileOffset: tsFieldOffset)
            handle.write(Data(bytes))
        }

        return true
    }

    // MARK: - mdta keys (Keys:CreationDate, Make, Model)

    private static func metaChildRange(
        _ handle: FileHandle,
        meta: Atom
    ) -> Range<UInt64> {
        // QuickTime meta has no version+flags; ISO 14496-12 meta does.
        // Detect by checking if bytes at +0 form a valid atom header.
        let start = meta.contentRange.lowerBound
        handle.seek(toFileOffset: start)
        let probe = handle.readData(ofLength: 8)
        guard probe.count == 8 else { return start..<meta.contentRange.upperBound }

        let size = probe.uint32BE(at: 0)
        let type = probe.fourCC(at: 4)
        let isPrintable = type.unicodeScalars.allSatisfy { $0.value >= 0x20 && $0.value < 0x7F }

        if size >= 8 && size <= meta.size && isPrintable {
            return start..<meta.contentRange.upperBound
        }
        return (start + 4)..<meta.contentRange.upperBound
    }

    private static func readMdtaKeys(
        in handle: FileHandle,
        moovRange: Range<UInt64>
    ) -> [String: String] {
        guard let meta = findAtom(in: handle, type: "meta", range: moovRange) else { return [:] }

        let childRange = metaChildRange(handle, meta: meta)

        guard let keysAtom = findAtom(in: handle, type: "keys", range: childRange),
              let ilstAtom = findAtom(in: handle, type: "ilst", range: childRange)
        else { return [:] }

        let keys = parseKeysAtom(handle, atom: keysAtom)
        return parseIlstAtom(handle, atom: ilstAtom, keys: keys)
    }

    private static func parseKeysAtom(_ handle: FileHandle, atom: Atom) -> [Int: String] {
        handle.seek(toFileOffset: atom.contentRange.lowerBound)
        let header = handle.readData(ofLength: 8) // version(4) + count(4)
        guard header.count == 8 else { return [:] }

        let count = header.uint32BE(at: 4)
        var keys: [Int: String] = [:]

        for i in 0..<count {
            let sizeData = handle.readData(ofLength: 4)
            guard sizeData.count == 4 else { break }
            let keySize = Int(sizeData.uint32BE(at: 0))
            guard keySize > 8 else { break }

            let rest = handle.readData(ofLength: keySize - 4)
            guard rest.count == keySize - 4 else { break }

            // 4 bytes namespace + key string
            let keyName = String(data: rest[4...], encoding: .utf8) ?? ""
            keys[Int(i) + 1] = keyName // 1-based index
        }

        return keys
    }

    private static func parseIlstAtom(
        _ handle: FileHandle,
        atom: Atom,
        keys: [Int: String]
    ) -> [String: String] {
        var result: [String: String] = [:]
        var pos = atom.contentRange.lowerBound

        while pos < atom.contentRange.upperBound {
            guard let item = readAtomHeader(handle, at: pos, limit: atom.contentRange.upperBound)
            else { break }

            let keyIndex = Int(item.type.fourCCValue)
            if let keyName = keys[keyIndex] {
                if let dataAtom = findAtom(in: handle, type: "data", range: item.contentRange) {
                    handle.seek(toFileOffset: dataAtom.contentRange.lowerBound)
                    let typeAndLocale = handle.readData(ofLength: 8)
                    guard typeAndLocale.count == 8 else { break }

                    let remaining = Int(dataAtom.contentRange.upperBound
                        - dataAtom.contentRange.lowerBound) - 8
                    if remaining > 0 {
                        let valueData = handle.readData(ofLength: remaining)
                        if let str = String(data: valueData, encoding: .utf8) {
                            result[keyName] = str
                        }
                    }
                }
            }

            pos = item.offset + item.size
        }

        return result
    }

    // MARK: - mdta key writing

    private static func writeMdtaKey(file: String, key: String, value: String) -> Bool {
        guard let handle = FileHandle(forReadingAtPath: file) else { return false }
        defer { handle.closeFile() }

        let fileSize = handle.seekToEndOfFile()
        handle.seek(toFileOffset: 0)

        guard let moov = findAtom(in: handle, type: "moov", range: 0..<fileSize) else {
            return false
        }

        guard let meta = findAtom(in: handle, type: "meta", range: moov.contentRange) else {
            return rewriteWithNewMdtaKey(file: file, moovAtom: moov, key: key, value: value)
        }

        let childRange = metaChildRange(handle, meta: meta)

        guard let keysAtom = findAtom(in: handle, type: "keys", range: childRange),
              let ilstAtom = findAtom(in: handle, type: "ilst", range: childRange)
        else {
            return rewriteWithNewMdtaKey(file: file, moovAtom: moov, key: key, value: value)
        }

        let keys = parseKeysAtom(handle, atom: keysAtom)

        // Check if key already exists with same-length value
        if let existingIndex = keys.first(where: { $0.value == key })?.key {
            // Find the ilst entry for this index and check value length
            var pos = ilstAtom.contentRange.lowerBound
            while pos < ilstAtom.contentRange.upperBound {
                guard let item = readAtomHeader(handle, at: pos,
                    limit: ilstAtom.contentRange.upperBound) else { break }

                let idx = Int(item.type.fourCCValue)
                if idx == existingIndex {
                    if let dataAtom = findAtom(in: handle, type: "data",
                        range: item.contentRange) {
                        let valueOffset = dataAtom.contentRange.lowerBound + 8
                        let existingLen = Int(dataAtom.contentRange.upperBound - valueOffset)
                        let newData = Data(value.utf8)

                        if newData.count == existingLen {
                            guard let wh = try? FileHandle(forUpdating:
                                URL(fileURLWithPath: file)) else { return false }
                            defer { wh.closeFile() }
                            wh.seek(toFileOffset: valueOffset)
                            wh.write(newData)
                            return true
                        }
                    }
                }
                pos = item.offset + item.size
            }
        }

        return rewriteWithNewMdtaKey(file: file, moovAtom: moov, key: key, value: value)
    }

    // MARK: - Full moov rewrite

    private static func rewriteWithNewMdtaKey(
        file: String,
        moovAtom: Atom,
        key: String,
        value: String
    ) -> Bool {
        let url = URL(fileURLWithPath: file)
        guard let readHandle = FileHandle(forReadingAtPath: file) else { return false }
        defer { readHandle.closeFile() }

        let fileSize = readHandle.seekToEndOfFile()
        readHandle.seek(toFileOffset: 0)

        // Read original moov data
        readHandle.seek(toFileOffset: moovAtom.offset + UInt64(moovAtom.headerSize))
        let moovData = readHandle.readData(
            ofLength: Int(moovAtom.size) - moovAtom.headerSize
        )

        // Build new moov with updated/added mdta key
        guard var newMoovContent = buildUpdatedMoov(
            originalContent: moovData,
            moovAtom: moovAtom,
            key: key,
            value: value,
            readHandle: readHandle
        ) else { return false }

        let newMoovSize = UInt32(newMoovContent.count + 8)
        var moovHeader = Data(count: 8)
        moovHeader.writeUInt32BE(newMoovSize, at: 0)
        moovHeader.writeFourCC("moov", at: 4)

        let sizeDelta = Int64(newMoovSize) - Int64(moovAtom.size)

        // Adjust stco/co64 chunk offsets. These are absolute file offsets.
        // Only offsets pointing past moov need adjustment — data before moov
        // (e.g. mdat in standard camera layout) stays at the same position.
        let moovEnd = moovAtom.offset + moovAtom.size
        if sizeDelta != 0 {
            adjustChunkOffsets(in: &newMoovContent, delta: sizeDelta, threshold: moovEnd)
        }

        // Write new file
        let tempURL = url.deletingLastPathComponent()
            .appendingPathComponent(".\(UUID().uuidString).\(url.pathExtension)")

        guard FileManager.default.createFile(atPath: tempURL.path, contents: nil) else {
            return false
        }
        guard let writeHandle = FileHandle(forWritingAtPath: tempURL.path) else {
            try? FileManager.default.removeItem(at: tempURL)
            return false
        }
        defer { writeHandle.closeFile() }

        readHandle.seek(toFileOffset: 0)

        // Copy atoms before moov
        copyBytes(from: readHandle, to: writeHandle, count: Int(moovAtom.offset))

        // Write new moov
        writeHandle.write(moovHeader)
        writeHandle.write(newMoovContent)

        // Copy atoms after moov using buffered IO
        let afterMoov = moovAtom.offset + moovAtom.size
        if afterMoov < fileSize {
            readHandle.seek(toFileOffset: afterMoov)
            copyBytes(from: readHandle, to: writeHandle, count: Int(fileSize - afterMoov))
        }

        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: file)
            let modDate = attrs[.modificationDate] as? Date
            let createDate = attrs[.creationDate] as? Date

            writeHandle.closeFile()
            readHandle.closeFile()

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

    private static func buildUpdatedMoov(
        originalContent: Data,
        moovAtom: Atom,
        key: String,
        value: String,
        readHandle: FileHandle
    ) -> Data? {
        // Parse children of moov to find/rebuild meta atom
        var result = Data()
        var pos = 0
        var foundMeta = false

        while pos < originalContent.count {
            guard pos + 8 <= originalContent.count else { break }
            let size32 = originalContent.uint32BE(at: pos)
            let type = originalContent.fourCC(at: pos + 4)

            var atomSize: Int
            if size32 == 1, pos + 16 <= originalContent.count {
                atomSize = Int(originalContent.uint64BE(at: pos + 8))
            } else if size32 == 0 {
                atomSize = originalContent.count - pos
            } else {
                atomSize = Int(size32)
            }

            guard atomSize >= 8, pos + atomSize <= originalContent.count else { break }

            if type == "meta" {
                foundMeta = true
                let metaContent = Data(originalContent[pos..<(pos + atomSize)])
                let newMeta = rebuildMetaAtom(metaContent, key: key, value: value)
                result.append(newMeta)
            } else {
                result.append(originalContent[pos..<(pos + atomSize)])
            }

            pos += atomSize
        }

        if !foundMeta {
            result.append(buildNewMetaAtom(key: key, value: value))
        }

        return result
    }

    private static func rebuildMetaAtom(_ metaData: Data, key: String, value: String) -> Data {
        guard metaData.count >= 16 else {
            return buildNewMetaAtom(key: key, value: value)
        }

        // Detect QuickTime (no version+flags) vs ISO (with version+flags)
        let headerSize = 8
        let probeSize = metaData.uint32BE(at: headerSize)
        let probeType = metaData.fourCC(at: headerSize + 4)
        let isPrintable = probeType.unicodeScalars.allSatisfy {
            $0.value >= 0x20 && $0.value < 0x7F
        }
        let hasVersionFlags = !(probeSize >= 8 && isPrintable)
        let childStart = hasVersionFlags ? headerSize + 4 : headerSize

        var existingKeys: [(String)] = []
        var existingItems: [(Int, Data)] = []
        var otherChildren = Data()

        var pos = childStart
        while pos + 8 <= metaData.count {
            let size32 = metaData.uint32BE(at: pos)
            let type = metaData.fourCC(at: pos + 4)
            let atomSize = (size32 == 0) ? (metaData.count - pos) : Int(size32)
            guard atomSize >= 8, pos + atomSize <= metaData.count else { break }

            if type == "keys" {
                existingKeys = parseKeysFromData(Data(metaData[pos..<(pos + atomSize)]))
            } else if type == "ilst" {
                existingItems = parseIlstFromData(Data(metaData[pos..<(pos + atomSize)]))
            } else {
                otherChildren.append(metaData[pos..<(pos + atomSize)])
            }

            pos += atomSize
        }

        var keyIndex = existingKeys.firstIndex(of: key)
        if keyIndex == nil {
            existingKeys.append(key)
            keyIndex = existingKeys.count - 1
        }
        let oneBasedIndex = keyIndex! + 1

        let valueBytes = Data(value.utf8)
        let dataAtomContent = buildDataAtom(typeIndicator: 1, value: valueBytes)

        var newItems = existingItems.filter { $0.0 != oneBasedIndex }
        newItems.append((oneBasedIndex, dataAtomContent))

        let keysAtom = buildKeysAtom(existingKeys)
        let ilstAtom = buildIlstAtom(newItems)

        // Rebuild meta — always write QuickTime-style (no version+flags)
        var metaContent = Data()
        metaContent.append(otherChildren)
        metaContent.append(keysAtom)
        metaContent.append(ilstAtom)

        var metaResult = Data(count: 8)
        metaResult.writeUInt32BE(UInt32(metaContent.count + 8), at: 0)
        metaResult.writeFourCC("meta", at: 4)
        metaResult.append(metaContent)

        return metaResult
    }

    private static func buildNewMetaAtom(key: String, value: String) -> Data {
        let hdlr = buildHdlrAtom()
        let keysAtom = buildKeysAtom([key])
        let valueData = Data(value.utf8)
        let dataAtom = buildDataAtom(typeIndicator: 1, value: valueData)
        let ilstAtom = buildIlstAtom([(1, dataAtom)])

        var metaContent = Data()
        metaContent.append(hdlr)
        metaContent.append(keysAtom)
        metaContent.append(ilstAtom)

        var meta = Data(count: 8)
        meta.writeUInt32BE(UInt32(metaContent.count + 8), at: 0)
        meta.writeFourCC("meta", at: 4)
        meta.append(metaContent)

        return meta
    }

    private static func buildHdlrAtom() -> Data {
        var data = Data()
        let content = Data(count: 4) // version + flags
            + Data(count: 4) // pre_defined (0)
            + "mdta".data(using: .ascii)! // handler type
            + Data(count: 12) // reserved
            + Data(count: 1) // name (null terminator)

        var header = Data(count: 8)
        header.writeUInt32BE(UInt32(content.count + 8), at: 0)
        header.writeFourCC("hdlr", at: 4)
        data.append(header)
        data.append(content)
        return data
    }

    private static func buildKeysAtom(_ keys: [String]) -> Data {
        var content = Data(count: 4) // version + flags
        var countData = Data(count: 4)
        countData.writeUInt32BE(UInt32(keys.count), at: 0)
        content.append(countData)

        for key in keys {
            let keyData = "mdta".data(using: .ascii)! + key.data(using: .utf8)!
            var sizeData = Data(count: 4)
            sizeData.writeUInt32BE(UInt32(keyData.count + 4), at: 0)
            content.append(sizeData)
            content.append(keyData)
        }

        var atom = Data(count: 8)
        atom.writeUInt32BE(UInt32(content.count + 8), at: 0)
        atom.writeFourCC("keys", at: 4)
        atom.append(content)
        return atom
    }

    private static func buildIlstAtom(_ items: [(Int, Data)]) -> Data {
        var content = Data()

        for (keyIndex, dataAtom) in items {
            let itemSize = UInt32(dataAtom.count + 8)
            var itemHeader = Data(count: 8)
            itemHeader.writeUInt32BE(itemSize, at: 0)
            itemHeader.writeUInt32BE(UInt32(keyIndex), at: 4)
            content.append(itemHeader)
            content.append(dataAtom)
        }

        var atom = Data(count: 8)
        atom.writeUInt32BE(UInt32(content.count + 8), at: 0)
        atom.writeFourCC("ilst", at: 4)
        atom.append(content)
        return atom
    }

    private static func buildDataAtom(typeIndicator: UInt32, value: Data) -> Data {
        let size = UInt32(value.count + 16)
        var atom = Data(count: 8)
        atom.writeUInt32BE(size, at: 0)
        atom.writeFourCC("data", at: 4)

        var typeData = Data(count: 4)
        typeData.writeUInt32BE(typeIndicator, at: 0)
        atom.append(typeData)
        atom.append(Data(count: 4)) // locale
        atom.append(value)
        return atom
    }

    private static func parseKeysFromData(_ data: Data) -> [String] {
        let base = data.startIndex
        guard data.count >= 16 else { return [] } // header(8) + version(4) + count(4)

        let count = data.uint32BE(at: base + 12)
        var keys: [String] = []
        var pos = base + 16

        for _ in 0..<count {
            guard pos + 4 <= data.endIndex else { break }
            let keySize = Int(data.uint32BE(at: pos))
            guard keySize > 8, pos + keySize <= data.endIndex else { break }
            // skip size(4) + namespace(4), read key string
            let keyStr = String(data: data[(pos + 8)..<(pos + keySize)], encoding: .utf8) ?? ""
            keys.append(keyStr)
            pos += keySize
        }

        return keys
    }

    private static func parseIlstFromData(_ data: Data) -> [(Int, Data)] {
        let base = data.startIndex
        var items: [(Int, Data)] = []
        var pos = base + 8 // skip ilst header

        while pos + 8 <= data.endIndex {
            let size = Int(data.uint32BE(at: pos))
            let keyIndex = Int(data.uint32BE(at: pos + 4))
            guard size >= 8, pos + size <= data.endIndex else { break }

            let itemContent = Data(data[(pos + 8)..<(pos + size)])
            items.append((keyIndex, itemContent))
            pos += size
        }

        return items
    }

    // MARK: - Chunk offset adjustment (stco/co64)

    private static func adjustChunkOffsets(
        in data: inout Data,
        delta: Int64,
        threshold: UInt64
    ) {
        var pos = 0
        while pos + 8 <= data.count {
            let size = Int(data.uint32BE(at: pos))
            guard size >= 8, pos + size <= data.count else { break }
            let type = data.fourCC(at: pos + 4)

            if type == "stco" {
                adjustStco(in: &data, at: pos, delta: delta, threshold: threshold)
            } else if type == "co64" {
                adjustCo64(in: &data, at: pos, delta: delta, threshold: threshold)
            } else if ["moov", "trak", "mdia", "minf", "stbl"].contains(type) {
                var sub = Data(data[(pos + 8)..<(pos + size)])
                adjustChunkOffsets(in: &sub, delta: delta, threshold: threshold)
                data.replaceSubrange((pos + 8)..<(pos + size), with: sub)
            }

            pos += size
        }
    }

    private static func adjustStco(
        in data: inout Data,
        at pos: Int,
        delta: Int64,
        threshold: UInt64
    ) {
        guard pos + 16 <= data.count else { return }
        let count = Int(data.uint32BE(at: pos + 12))
        var offset = pos + 16

        for _ in 0..<count {
            guard offset + 4 <= data.count else { break }
            let old = UInt64(data.uint32BE(at: offset))
            if old >= threshold {
                let adjusted = UInt32(clamping: max(0, Int64(old) + delta))
                data.writeUInt32BE(adjusted, at: offset)
            }
            offset += 4
        }
    }

    private static func adjustCo64(
        in data: inout Data,
        at pos: Int,
        delta: Int64,
        threshold: UInt64
    ) {
        guard pos + 16 <= data.count else { return }
        let count = Int(data.uint32BE(at: pos + 12))
        var offset = pos + 16

        for _ in 0..<count {
            guard offset + 8 <= data.count else { break }
            let old = data.uint64BE(at: offset)
            if old >= threshold {
                let adjusted = UInt64(bitPattern: max(0, Int64(bitPattern: old) + delta))
                data.writeUInt64BE(adjusted, at: offset)
            }
            offset += 8
        }
    }

    // MARK: - Date conversion

    private static func formatQTTimestamp(_ qtTimestamp: UInt64) -> String {
        if qtTimestamp <= qtEpochOffset {
            return "0000:00:00 00:00:00"
        }
        let unix = TimeInterval(qtTimestamp - qtEpochOffset)
        let date = Date(timeIntervalSince1970: unix)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy:MM:dd HH:mm:ss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
    }

    private static func parseToQTTimestamp(_ exifDate: String) -> UInt64? {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy:MM:dd HH:mm:ss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        guard let date = formatter.date(from: exifDate) else { return nil }
        let unix = UInt64(date.timeIntervalSince1970)
        return unix + qtEpochOffset
    }

    private static func exifStyleDate(_ isoString: String) -> String {
        // Convert "2025-06-18T07:25:21+08:00" → "2025:06:18 07:25:21+08:00"
        var s = isoString
        if s.count >= 10 {
            let idx4 = s.index(s.startIndex, offsetBy: 4)
            let idx7 = s.index(s.startIndex, offsetBy: 7)
            if s[idx4] == "-" { s.replaceSubrange(idx4...idx4, with: ":") }
            if s[idx7] == "-" { s.replaceSubrange(idx7...idx7, with: ":") }
        }
        if let tIdx = s.firstIndex(of: "T") {
            s.replaceSubrange(tIdx...tIdx, with: " ")
        }
        // Ensure timezone has colon: +0900 → +09:00
        if let plusIdx = s.lastIndex(of: "+") ?? s.lastIndex(of: "-"),
           plusIdx > s.index(s.startIndex, offsetBy: 10) {
            let tz = String(s[plusIdx...])
            if tz.count == 5 && !tz.contains(":") {
                let insertIdx = s.index(plusIdx, offsetBy: 3)
                s.insert(":", at: insertIdx)
            }
        }
        return s
    }

    private static func isoDate(_ exifDate: String) -> String {
        // Convert "2025:06:18 07:25:21+08:00" → "2025-06-18T07:25:21+08:00"
        var s = exifDate
        if s.count >= 10 {
            let idx4 = s.index(s.startIndex, offsetBy: 4)
            let idx7 = s.index(s.startIndex, offsetBy: 7)
            if s[idx4] == ":" { s.replaceSubrange(idx4...idx4, with: "-") }
            if s[idx7] == ":" { s.replaceSubrange(idx7...idx7, with: "-") }
        }
        if s.count >= 11 {
            let idx10 = s.index(s.startIndex, offsetBy: 10)
            if s[idx10] == " " { s.replaceSubrange(idx10...idx10, with: "T") }
        }
        return s
    }

    // MARK: - IO helpers

    private static func copyBytes(from: FileHandle, to: FileHandle, count: Int) {
        var remaining = count
        let bufferSize = 65536
        while remaining > 0 {
            let chunk = min(remaining, bufferSize)
            let data = from.readData(ofLength: chunk)
            if data.isEmpty { break }
            to.write(data)
            remaining -= data.count
        }
    }
}

// MARK: - Data extensions for binary parsing

extension Data {
    func uint32BE(at offset: Int) -> UInt32 {
        let base = startIndex + offset
        guard base + 4 <= endIndex else { return 0 }
        return UInt32(self[base]) << 24
            | UInt32(self[base + 1]) << 16
            | UInt32(self[base + 2]) << 8
            | UInt32(self[base + 3])
    }

    func uint64BE(at offset: Int) -> UInt64 {
        let base = startIndex + offset
        guard base + 8 <= endIndex else { return 0 }
        return UInt64(self[base]) << 56
            | UInt64(self[base + 1]) << 48
            | UInt64(self[base + 2]) << 40
            | UInt64(self[base + 3]) << 32
            | UInt64(self[base + 4]) << 24
            | UInt64(self[base + 5]) << 16
            | UInt64(self[base + 6]) << 8
            | UInt64(self[base + 7])
    }

    func fourCC(at offset: Int) -> String {
        let base = startIndex + offset
        guard base + 4 <= endIndex else { return "????" }
        let bytes = [self[base], self[base + 1], self[base + 2], self[base + 3]]
        return String(bytes.map { Character(UnicodeScalar($0)) })
    }

    mutating func writeUInt32BE(_ value: UInt32, at offset: Int) {
        let base = startIndex + offset
        self[base] = UInt8((value >> 24) & 0xFF)
        self[base + 1] = UInt8((value >> 16) & 0xFF)
        self[base + 2] = UInt8((value >> 8) & 0xFF)
        self[base + 3] = UInt8(value & 0xFF)
    }

    mutating func writeUInt64BE(_ value: UInt64, at offset: Int) {
        let base = startIndex + offset
        self[base] = UInt8((value >> 56) & 0xFF)
        self[base + 1] = UInt8((value >> 48) & 0xFF)
        self[base + 2] = UInt8((value >> 40) & 0xFF)
        self[base + 3] = UInt8((value >> 32) & 0xFF)
        self[base + 4] = UInt8((value >> 24) & 0xFF)
        self[base + 5] = UInt8((value >> 16) & 0xFF)
        self[base + 6] = UInt8((value >> 8) & 0xFF)
        self[base + 7] = UInt8(value & 0xFF)
    }

    mutating func writeFourCC(_ value: String, at offset: Int) {
        let ascii = Array(value.utf8)
        guard ascii.count == 4 else { return }
        let base = startIndex + offset
        for i in 0..<4 {
            self[base + i] = ascii[i]
        }
    }
}

extension String {
    var fourCCValue: UInt32 {
        let bytes = Array(utf8)
        guard bytes.count == 4 else { return 0 }
        return UInt32(bytes[0]) << 24
            | UInt32(bytes[1]) << 16
            | UInt32(bytes[2]) << 8
            | UInt32(bytes[3])
    }
}
