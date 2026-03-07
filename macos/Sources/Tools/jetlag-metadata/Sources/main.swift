import Foundation

let exiftool = ExifToolProcess()

func handleRequest(_ data: Data) -> Data {
    do {
        let request = try JSONDecoder().decode(Request.self, from: data)
        let response: Data

        switch request.op {
        case "read":
            guard case .array(let tagList)? = request.tags else {
                throw MetadataError.invalidRequest("read requires tags as an array of strings")
            }
            let result = try exiftool.readTags(
                file: request.file,
                tags: tagList,
                fast: request.fast ?? false
            )
            response = try JSONEncoder().encode(ReadResponse(tags: result))

        case "write":
            guard case .dict(let tagDict)? = request.tags else {
                throw MetadataError.invalidRequest("write requires tags as a dictionary")
            }
            let result = try exiftool.writeTags(file: request.file, tags: tagDict)
            response = try JSONEncoder().encode(
                WriteResponse(updated: result.updated, files_changed: result.filesChanged)
            )

        default:
            throw MetadataError.unknownOperation(request.op)
        }

        return response
    } catch {
        let errorResponse = ErrorResponse(error: error.localizedDescription)
        return (try? JSONEncoder().encode(errorResponse)) ?? Data("{}".utf8)
    }
}

while let line = readLine(strippingNewline: true) {
    let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty { continue }

    let responseData = handleRequest(Data(trimmed.utf8))
    if let responseString = String(data: responseData, encoding: .utf8) {
        print(responseString)
        fflush(stdout)
    }
}

exiftool.shutdown()
