import Foundation

/// Progress of the running stage as shown by the live-cooking ring.
public enum CookingProgress {
    /// Fraction of the stage completed, always within 0...1 even when the device
    /// reports elapsed time beyond the stage length or a zero-length stage.
    public static func fraction(elapsed: TimeInterval, total: TimeInterval) -> Double {
        guard total > 0 else { return 1 }
        return min(max(elapsed / total, 0), 1)
    }

    /// Whole seconds left in the stage, never negative.
    public static func remainingSeconds(elapsed: TimeInterval, total: TimeInterval) -> Int {
        Int(max(total - elapsed, 0).rounded(.up))
    }
}
