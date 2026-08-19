// Prints the Corsair Xeneon Edge's current CoreGraphics origin+size, or NONE.
import CoreGraphics
var count: UInt32 = 0
CGGetActiveDisplayList(0, nil, &count)
var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
CGGetActiveDisplayList(count, &ids, &count)
for d in ids {
    // Edge is the 2560x720 panel; main here is 5120x1440. Match by size.
    if CGDisplayPixelsWide(d) == 2560 && CGDisplayPixelsHigh(d) == 720 {
        let b = CGDisplayBounds(d)
        print("\(Int(b.origin.x)) \(Int(b.origin.y)) \(Int(b.size.width)) \(Int(b.size.height))")
        exit(0)
    }
}
print("NONE")
