import Foundation

struct MapLifecycleOperationToken: Equatable, Sendable {
    fileprivate let id: UUID
    fileprivate let generation: UInt64
}

/// Small concurrency boundary owned by the lifecycle view model. It keeps
/// stale completions from becoming visible after disconnect/eject and gives
/// the UI one authoritative busy state for backup, remove, and update.
final class MapLifecycleOperationController: @unchecked Sendable {
    private let lock = NSLock()
    private var generation: UInt64 = 0
    private var active: Set<UUID> = []

    var isBusy: Bool {
        lock.lock()
        defer { lock.unlock() }
        return !active.isEmpty
    }

    var canEject: Bool { !isBusy }

    func begin() -> MapLifecycleOperationToken? {
        lock.lock()
        defer { lock.unlock() }
        guard active.isEmpty else { return nil }
        let token = MapLifecycleOperationToken(id: UUID(), generation: generation)
        active.insert(token.id)
        return token
    }

    func isCurrent(_ token: MapLifecycleOperationToken) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return token.generation == generation && active.contains(token.id)
    }

    @discardableResult
    func invalidate() -> UInt64 {
        lock.lock()
        defer { lock.unlock() }
        generation &+= 1
        return generation
    }

    func finish(_ token: MapLifecycleOperationToken) {
        lock.lock()
        active.remove(token.id)
        lock.unlock()
    }
}
