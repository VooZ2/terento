import Foundation

/// Inspects the downloaded ZIP itself before any filesystem extraction. The
/// proof's IMG size bounds expansion; provider notice files get a separate cap.
/// No archive program or bundled script runs during this inspection.
enum BBBikeArchiveSafety {
    enum Failure: Error { case invalidArchive }

    static func validate(archiveURL: URL, expectedPayloadPath: String, expectedIMGBytes: UInt64) throws {
        let handle = try FileHandle(forReadingFrom: archiveURL)
        defer { try? handle.close() }
        let size = try handle.seekToEnd()
        func require(_ condition: Bool) throws {
            guard condition else { throw Failure.invalidArchive }
        }
        func read(_ offset: UInt64, _ count: UInt64) throws -> [UInt8] {
            try require(count <= 1_048_576 && offset <= size && count <= size - offset)
            try handle.seek(toOffset: offset)
            let bytes = [UInt8](try handle.read(upToCount: Int(count)) ?? Data())
            try require(UInt64(bytes.count) == count)
            return bytes
        }
        func number(_ bytes: [UInt8], _ offset: Int, _ count: Int) throws -> UInt64 {
            try require(offset >= 0 && count <= 8 && offset <= bytes.count && count <= bytes.count - offset)
            return (0..<count).reduce(UInt64(0)) { $0 | UInt64(bytes[offset + $1]) << ($1 * 8) }
        }
        try require(size >= 22 && expectedIMGBytes >= 512)
        let tailSize = min(size, 65_557)
        let tail = try read(size - tailSize, tailSize)
        var eocdIndex: Int?
        for index in stride(from: tail.count - 22, through: 0, by: -1) {
            if try number(tail, index, 4) == 0x06054b50,
               index + 22 + Int(try number(tail, index + 20, 2)) == tail.count {
                eocdIndex = index; break
            }
        }
        guard let end = eocdIndex else { throw Failure.invalidArchive }
        try require(try number(tail, end + 4, 2) == 0 && number(tail, end + 6, 2) == 0)
        var entries = try number(tail, end + 10, 2)
        try require(try number(tail, end + 8, 2) == entries)
        var centralSize = try number(tail, end + 12, 4)
        var centralOffset = try number(tail, end + 16, 4)
        let endOffset = size - tailSize + UInt64(end)
        if entries == 0xffff || centralSize == 0xffffffff || centralOffset == 0xffffffff {
            try require(endOffset >= 20)
            let locator = try read(endOffset - 20, 20)
            try require(try number(locator, 0, 4) == 0x07064b50 && number(locator, 4, 4) == 0 && number(locator, 16, 4) == 1)
            let zip64Offset = try number(locator, 8, 8)
            let zip64 = try read(zip64Offset, 56)
            try require(try number(zip64, 0, 4) == 0x06064b50 && number(zip64, 4, 8) >= 44
                && number(zip64, 16, 4) == 0 && number(zip64, 20, 4) == 0)
            entries = try number(zip64, 32, 8)
            try require(try number(zip64, 24, 8) == entries)
            centralSize = try number(zip64, 40, 8)
            centralOffset = try number(zip64, 48, 8)
        }
        try require(entries > 0 && entries <= 64 && centralSize <= 1_048_576
            && centralOffset <= endOffset && centralSize <= endOffset - centralOffset)
        let central = try read(centralOffset, centralSize)
        let parts = expectedPayloadPath.split(separator: "/")
        try require(parts.count == 2 && parts[1] == "gmapsupp.img")
        let root = String(parts[0]) + "/"
        let allowed = Set([root, expectedPayloadPath, root + "README.txt", root + "README.html",
                           root + "CHECKSUM.txt", root + "logfile.txt", root + "basecamp-macos.sh"])
        var names = Set<String>()
        var position = 0
        var ancillaryBytes: UInt64 = 0
        var intervals: [(UInt64, UInt64)] = []
        for _ in 0..<Int(entries) {
            try require(try number(central, position, 4) == 0x02014b50)
            let flags = try number(central, position + 8, 2)
            let method = try number(central, position + 10, 2)
            try require(flags & 0x2041 == 0 && (method == 0 || method == 8))
            let nameLength = Int(try number(central, position + 28, 2))
            let extraLength = Int(try number(central, position + 30, 2))
            let commentLength = Int(try number(central, position + 32, 2))
            let endPosition = position + 46 + nameLength + extraLength + commentLength
            try require(endPosition <= central.count && nameLength > 0)
            let nameBytes = Array(central[(position + 46)..<(position + 46 + nameLength)])
            guard let name = String(bytes: nameBytes, encoding: .utf8) else { throw Failure.invalidArchive }
            try require(allowed.contains(name) && names.insert(name).inserted)
            let mode = try number(central, position + 38, 4) >> 16
            let fileType = mode & 0xf000
            try require(fileType == 0 || fileType == (name == root ? 0x4000 : 0x8000))
            try require(try number(central, position + 34, 2) == 0)
            var packed = try number(central, position + 20, 4)
            var expanded = try number(central, position + 24, 4)
            var offset = try number(central, position + 42, 4)
            if packed == 0xffffffff || expanded == 0xffffffff || offset == 0xffffffff {
                var cursor = position + 46 + nameLength
                let limit = cursor + extraLength
                var found = false
                while cursor + 4 <= limit {
                    let tag = try number(central, cursor, 2)
                    let length = Int(try number(central, cursor + 2, 2))
                    try require(cursor + 4 + length <= limit)
                    if tag == 1 {
                        try require(!found); found = true
                        var valueOffset = cursor + 4
                        let valueEnd = valueOffset + length
                        func next() throws -> UInt64 {
                            try require(valueOffset + 8 <= valueEnd)
                            defer { valueOffset += 8 }
                            return try number(central, valueOffset, 8)
                        }
                        if expanded == 0xffffffff { expanded = try next() }
                        if packed == 0xffffffff { packed = try next() }
                        if offset == 0xffffffff { offset = try next() }
                    }
                    cursor += 4 + length
                }
                try require(found)
            }
            if name == expectedPayloadPath { try require(expanded == expectedIMGBytes) }
            else {
                try require(expanded <= 8_388_608 && ancillaryBytes <= 8_388_608 - expanded)
                ancillaryBytes += expanded
            }
            if name == root { try require(expanded == 0) }
            try require(offset < centralOffset)
            let local = try read(offset, 30)
            try require(try number(local, 0, 4) == 0x04034b50 && number(local, 6, 2) == flags
                && number(local, 8, 2) == method && number(local, 26, 2) == UInt64(nameLength))
            if flags & 8 == 0 {
                let localPacked = try number(local, 18, 4)
                let localExpanded = try number(local, 22, 4)
                try require((localPacked == packed || localPacked == 0xffffffff)
                    && (localExpanded == expanded || localExpanded == 0xffffffff))
                try require(try number(local, 14, 4) == number(central, position + 16, 4))
            }
            let localExtra = try number(local, 28, 2)
            if try flags & 8 == 0 && (number(local, 18, 4) == 0xffffffff || number(local, 22, 4) == 0xffffffff) {
                let extra = try read(offset + 30 + UInt64(nameLength), localExtra)
                var cursor = 0
                var found = false
                while cursor + 4 <= extra.count {
                    let tag = try number(extra, cursor, 2)
                    let length = Int(try number(extra, cursor + 2, 2))
                    try require(cursor + 4 + length <= extra.count)
                    if tag == 1 {
                        try require(!found && length >= 16)
                        found = true
                        try require(try number(extra, cursor + 4, 8) == expanded
                            && number(extra, cursor + 12, 8) == packed)
                    }
                    cursor += 4 + length
                }
                try require(found)
            }
            try require(try read(offset + 30, UInt64(nameLength)) == nameBytes)
            let dataOffset = offset + 30 + UInt64(nameLength) + localExtra
            try require(dataOffset <= centralOffset && packed <= centralOffset - dataOffset)
            intervals.append((offset, dataOffset + packed))
            position = endPosition
        }
        try require(position == central.count && names.contains(expectedPayloadPath)
            && names.contains(root + "README.txt") && names.contains(root + "CHECKSUM.txt"))
        let sorted = intervals.sorted { $0.0 < $1.0 }
        for index in 1..<sorted.count { try require(sorted[index - 1].1 <= sorted[index].0) }
    }
}
