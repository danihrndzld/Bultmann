import Foundation
import PDFKit
import Vision
import CoreGraphics

// usage: ocr_vision <pdf> <outdir> [dpi] [startPage] [endPage]
let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: ocr_vision <pdf> <outdir> [dpi] [start] [end]\n".data(using: .utf8)!)
    exit(1)
}
let pdfPath = args[1]
let outDir = args[2]
let dpi: CGFloat = args.count > 3 ? CGFloat(Double(args[3]) ?? 300) : 300
let scale = dpi / 72.0

guard let doc = PDFDocument(url: URL(fileURLWithPath: pdfPath)) else {
    FileHandle.standardError.write("cannot open pdf\n".data(using: .utf8)!); exit(1)
}
let n = doc.pageCount
let start = args.count > 4 ? (Int(args[4]) ?? 0) : 0
let end   = args.count > 5 ? (Int(args[5]) ?? n) : n
try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

for i in start..<min(end, n) {
    autoreleasepool {
        guard let page = doc.page(at: i) else { return }
        let bounds = page.bounds(for: .mediaBox)
        let w = max(1, Int(bounds.width * scale))
        let h = max(1, Int(bounds.height * scale))
        let cs = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8,
                                  bytesPerRow: 0, space: cs,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return }
        ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
        ctx.scaleBy(x: scale, y: scale)
        ctx.translateBy(x: -bounds.origin.x, y: -bounds.origin.y)
        page.draw(with: .mediaBox, to: ctx)
        guard let cgImage = ctx.makeImage() else { return }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US", "de-DE"]
        request.usesLanguageCorrection = true
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        do { try handler.perform([request]) } catch {
            FileHandle.standardError.write("page \(i) OCR error: \(error)\n".data(using: .utf8)!)
        }

        var lines: [[String: Any]] = []
        for obs in (request.results ?? []) {
            guard let cand = obs.topCandidates(1).first else { continue }
            let bb = obs.boundingBox // normalized, origin bottom-left
            lines.append([
                "text": cand.string,
                "conf": cand.confidence,
                "x": bb.origin.x, "y": bb.origin.y,
                "w": bb.size.width, "h": bb.size.height
            ])
        }
        let pageObj: [String: Any] = ["page": i, "w": w, "h": h, "lines": lines]
        if let data = try? JSONSerialization.data(withJSONObject: pageObj) {
            let outURL = URL(fileURLWithPath: outDir).appendingPathComponent(String(format: "page-%04d.json", i))
            try? data.write(to: outURL)
        }
        FileHandle.standardError.write("page \(i+1)/\(n): \(lines.count) lines\n".data(using: .utf8)!)
    }
}
