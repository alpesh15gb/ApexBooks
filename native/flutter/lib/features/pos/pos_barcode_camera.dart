import 'package:material_ui/material_ui.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

typedef PosCameraPreviewBuilder = Widget Function(
  BuildContext context,
  ValueChanged<BarcodeCapture> onDetect,
  Widget Function(BuildContext, MobileScannerException) onError,
);

Widget mobileBarcodePreview(
  BuildContext context,
  ValueChanged<BarcodeCapture> onDetect,
  Widget Function(BuildContext, MobileScannerException) onError,
) {
  // Use the scanner's own controller so it handles Android lifecycle changes.
  return MobileScanner(
    onDetect: onDetect,
    errorBuilder: onError,
    tapToFocus: true,
  );
}

class PosBarcodeCamera extends StatefulWidget {
  const PosBarcodeCamera({
    required this.onBarcode,
    required this.onClose,
    this.previewBuilder = mobileBarcodePreview,
    super.key,
  });

  final ValueChanged<String> onBarcode;
  final VoidCallback onClose;
  final PosCameraPreviewBuilder previewBuilder;

  @override
  State<PosBarcodeCamera> createState() => _PosBarcodeCameraState();
}

class _PosBarcodeCameraState extends State<PosBarcodeCamera> {
  bool _accepted = false;
  String? _instruction;

  void _read(BarcodeCapture capture) {
    if (!mounted || _accepted) return;
    final codes = {
      for (final barcode in capture.barcodes)
        if (barcode.rawValue case final value?)
          if (value.trim().isNotEmpty) value.trim(),
    };
    if (codes.isEmpty) return;
    final instruction = codes.length > 1
        ? 'Aim the camera at one barcode.'
        : codes.single.length > 80
        ? 'Use an item barcode up to 80 characters.'
        : null;
    if (instruction != null) {
      if (_instruction != instruction) {
        setState(() => _instruction = instruction);
      }
      return;
    }
    _accepted = true;
    widget.onBarcode(codes.single);
  }

  Widget _cameraError(BuildContext context, MobileScannerException error) {
    final message = switch (error.errorCode) {
      MobileScannerErrorCode.permissionDenied => 'Camera access was denied. Type a barcode or use your external scanner.',
      _ => 'The camera is unavailable. Type a barcode or use your external scanner.',
    };
    return ColoredBox(
      color: Theme.of(context).colorScheme.surfaceContainer,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Semantics(liveRegion: true, child: Text(message)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(
            'Camera scanner',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          TextButton(
            onPressed: widget.onClose,
            child: const Text('Use barcode field'),
          ),
        ],
      ),
      ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: SizedBox(
          height: 220,
          child: widget.previewBuilder(context, _read, _cameraError),
        ),
      ),
      if (_instruction case final instruction?)
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Semantics(liveRegion: true, child: Text(instruction)),
        ),
    ],
  );
}
