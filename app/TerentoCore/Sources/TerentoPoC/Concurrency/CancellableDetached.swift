import Foundation

/// Runs blocking native or process work away from the main actor while
/// retaining a cancellation handle for the complete lifetime of the work.
enum CancellableDetached {
    static func run<T: Sendable>(
        priority: TaskPriority? = nil,
        operation: @escaping @Sendable () async throws -> T
    ) async throws -> T {
        let task = Task.detached(priority: priority) {
            try await operation()
        }

        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
    }
}
