import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/pdf_output.dart';
import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'pos_barcode_camera.dart';
import 'pos_controller.dart';
import 'pos_daily_panel.dart';
import 'pos_models.dart';
import 'pos_register_controller.dart';
import 'pos_register_panel.dart';
import 'pos_return_controller.dart';
import 'pos_return_panel.dart';
import 'pos_widgets.dart';
import 'pos_workspace_api.dart';

enum _PosView { checkout, receipts, register }

class PosScreen extends StatefulWidget {
  const PosScreen({
    required this.workspace,
    this.active = true,
    this.revision = 0,
    this.pdfOutput = const PlatformPdfOutput(),
    this.cameraPreview = mobileBarcodePreview,
    super.key,
  });

  final WorkspaceContext workspace;
  final bool active;
  final int revision;
  final PdfOutput pdfOutput;
  final PosCameraPreviewBuilder cameraPreview;

  @override
  State<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends State<PosScreen> {
  late WorkspacePosGateway gateway;
  late PosController counter;
  PosRegisterController? register;
  PosReturnController? _returns;
  late Listenable updates;
  final _scanner = TextEditingController();
  final _receiptSearch = TextEditingController();
  final _receiptDateText = TextEditingController();
  final _scannerFocus = FocusNode(debugLabel: 'Barcode input');
  bool _cameraOpen = false;
  final _scroll = ScrollController();
  final _paymentAnchor = GlobalKey();
  final _pricingLines = <String>{};
  _PosView _view = _PosView.checkout;
  PosReceipt? _viewedReceipt;
  Future<PosReceipt>? _receiptDetail;
  String _receiptDate = '';
  int _receiptLimit = 20;
  final _cartHeading = GlobalKey();
  bool get _history => _view == _PosView.receipts;
  bool get _registerBlocksSale => register?.blocksNewSale == true;
  bool get _otherActionPending =>
      counter.pending != null ||
      counter.posting ||
      counter.canWrite && !counter.pendingAvailable ||
      _registerBlocksSale;
  bool get _returnBlocksWrites => _returns?.blocksWrites == true;
  bool _showReturn = false;
  bool _printing = false;
  String? _printError;
  int _receiptActionRevision = 0;
  bool get _desktopScanner => const {
    TargetPlatform.windows,
    TargetPlatform.macOS,
    TargetPlatform.linux,
  }.contains(defaultTargetPlatform);
  bool get _androidCamera =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  @override
  void didUpdateWidget(covariant PosScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.active) _cameraOpen = false;
    if (oldWidget.workspace.company.id != widget.workspace.company.id ||
        oldWidget.workspace.api != widget.workspace.api ||
        oldWidget.workspace.company.role != widget.workspace.company.role) {
      counter.dispose();
      register?.dispose();
      _returns?.dispose();
      _scanner.clear();
      _receiptSearch.clear();
      _view = _PosView.checkout;
      _viewedReceipt = null;
      _receiptDetail = null;
      _cameraOpen = false;
      _showReturn = _printing = false;
      _printError = null;
      _receiptDate = '';
      _receiptLimit = 20;
      _pricingLines.clear();
      _receiptActionRevision++;
      _connect();
      return;
    }
    if (widget.active &&
        (!oldWidget.active || widget.revision != oldWidget.revision)) {
      final current = counter;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !widget.active || !identical(current, counter)) return;
        unawaited(current.loadProducts());
        unawaited(current.loadStock());
        unawaited(current.loadBanks());
        if (_history) unawaited(current.loadReceipts(reset: true));
        final drawer = register;
        if (_view == _PosView.register && drawer != null) {
          unawaited(drawer.refresh());
        }
        if (current.cart.isNotEmpty && current.editable) current.refreshQuote();
      });
    }
  }

  void _connect() {
    final workspace = widget.workspace;
    gateway = WorkspacePosGateway(workspace);
    counter = PosController(
      gateway: gateway,
      features: workspace.features,
      canWrite: workspace.company.canWrite,
      regularTax: workspace.company.taxMode == 'regular',
      unregistered: workspace.company.taxMode == 'unregistered',
      heldStore: PosHeldStore.forCompany(workspace.company.id),
      stateCode: workspace.company.stateCode,
      businessDate: businessDate,
    );
    register = workspace.features.contains('pos_register_sessions')
        ? PosRegisterController(
            gateway: gateway,
            canWrite: workspace.company.canWrite,
            onChanged: () {
              if (counter.cart.isNotEmpty && counter.editable) {
                counter.refreshQuote();
              }
              unawaited(workspace.refresh());
            },
            onFeedback: () => _showNotice(_PosView.register),
          )
        : null;
    _returns = workspace.features.contains('pos_atomic_returns')
        ? PosReturnController(
            gateway: gateway,
            canWrite: workspace.company.canWrite,
            businessDate: businessDate,
            onSaved: () {
              unawaited(counter.loadStock());
              if (counter.cart.isNotEmpty && counter.editable) {
                counter.refreshQuote();
              }
              final source = _viewedReceipt;
              if (mounted && source != null) {
                final updated = gateway.receipt(source.id);
                setState(() {
                  _receiptDetail = updated;
                });
              }
              if (_showReturn) _showNotice(_view);
              unawaited(workspace.refresh());
            },
            onFeedback: () {
              if (_showReturn) _showNotice(_view);
            },
          )
        : null;
    updates = Listenable.merge([counter, register, _returns]);
    unawaited(counter.initialize());
    unawaited(counter.loadReceipts(reset: true));
    if (register case final drawer?) unawaited(drawer.recover());
    if (_returns case final returns?) unawaited(returns.recover());
  }

  void _scan(String value, {bool keepKeyboardFocus = true}) {
    final matched = counter.scan(value);
    if (matched || _cameraOpen) {
      setState(() {
        _cameraOpen = false;
        if (matched) {
          _scanner.clear();
        } else if (!keepKeyboardFocus) {
          _scanner.text = value;
        }
      });
    }
    if (keepKeyboardFocus && widget.active && counter.editable) {
      _scannerFocus.requestFocus();
    }
  }

  void _openCamera() {
    _scannerFocus.unfocus();
    setState(() => _cameraOpen = true);
  }

  void _cameraRead(String barcode) {
    if (!mounted ||
        !widget.active ||
        !_cameraOpen ||
        _view != _PosView.checkout ||
        !counter.editable) {
      return;
    }
    _scan(barcode, keepKeyboardFocus: false);
  }

  void _closeCamera() {
    setState(() => _cameraOpen = false);
    if (widget.active && counter.editable) _scannerFocus.requestFocus();
  }

  void _selectView(_PosView view) {
    setState(() {
      _view = view;
      _cameraOpen = false;
      _viewedReceipt = null;
      _receiptDetail = null;
      _showReturn = false;
      _printError = null;
      _receiptActionRevision++;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
    if (_history && counter.receipts.isEmpty) {
      unawaited(counter.loadReceipts(reset: true));
    }
    final drawer = register;
    if (view == _PosView.register && drawer != null) {
      unawaited(drawer.refresh());
    }
  }

  Future<void> _complete() async {
    if ((_registerBlocksSale || _returnBlocksWrites) &&
        counter.pending == null) {
      return;
    }
    if (_cameraOpen) setState(() => _cameraOpen = false);
    final before = counter.completed;
    final current = counter;
    await current.submit();
    if (!mounted || !identical(current, counter)) return;
    final newlyCompleted = current.completed != before;
    if (newlyCompleted && current.pending == null) {
      _scanner.clear();
      _pricingLines.clear();
      unawaited(current.loadReceipts(reset: true));
      if (widget.active && _desktopScanner && _view == _PosView.checkout) {
        _scannerFocus.requestFocus();
      }
      unawaited(widget.workspace.refresh());
    }
    if (newlyCompleted ||
        current.status != null ||
        current.recoveryError != null) {
      _showNotice(_PosView.checkout);
    }
  }

  void _showNotice(_PosView view) {
    final current = counter;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted &&
          identical(current, counter) &&
          widget.active &&
          _view == view &&
          _scroll.hasClients) {
        _scroll.jumpTo(0);
      }
    });
  }

  @override
  void dispose() {
    counter.dispose();
    register?.dispose();
    _returns?.dispose();
    _scanner.dispose();
    _receiptSearch.dispose();
    _receiptDateText.dispose();
    _scannerFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ExcludeFocus(
    excluding: !widget.active,
    child: ListenableBuilder(
      listenable: updates,
      builder: (context, _) {
        final drawer = register;
        final returns = _returns;
        return LayoutBuilder(
          builder: (context, limits) {
            final wide = limits.maxWidth >= 850;
            final checkout =
                _view == _PosView.checkout &&
                _viewedReceipt == null &&
                !_showReturn;
            final content = SingleChildScrollView(
              controller: _scroll,
              padding: EdgeInsets.all(wide ? 24 : 16),
              child: Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1380),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _header(),
                      const SizedBox(height: 18),
                      if (!_showReturn &&
                          returns != null &&
                          (returns.pending != null ||
                              returns.storageError != null))
                        _PosNotice(
                          returns.pending != null
                              ? 'A return is awaiting confirmation.'
                              : 'Check saved return activity before posting.',
                          action: 'Open returns',
                          onAction: _openReturnRecovery,
                        ),
                      if (_showReturn && returns != null)
                        PosReturnPanel(
                          returns: returns,
                          banks: counter.banks,
                          back: _closeReturn,
                          otherActionPending: _otherActionPending,
                          download: _downloadDocument,
                        )
                      else if (_viewedReceipt case final receipt?)
                        _receiptView(receipt)
                      else if (_history)
                        _receipts()
                      else if (_view == _PosView.register)
                        _registerView(drawer)
                      else
                        _checkout(wide),
                    ],
                  ),
                ),
              ),
            );
            return Column(
              children: [
                Expanded(child: content),
                if (!wide &&
                    checkout &&
                    counter.cart.isNotEmpty &&
                    counter.pending == null &&
                    MediaQuery.viewInsetsOf(context).bottom == 0)
                  ListenableBuilder(
                    listenable: _scroll,
                    builder: (context, _) {
                      if (_scroll.positions.length == 1 &&
                          _scroll.position.hasContentDimensions &&
                          _scroll.offset > 0 &&
                          _scroll.position.extentAfter <= 72) {
                        return const SizedBox.shrink();
                      }
                      return _mobilePaymentShortcut();
                    },
                  ),
              ],
            );
          },
        );
      },
    ),
  );

  Widget _registerView(PosRegisterController? drawer) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (drawer != null) ...[
        PosRegisterPanel(
          key: ValueKey((
            drawer.active?.id,
            drawer.active?.snapshot,
            drawer.resetVersion,
          )),
          register: drawer,
          loadMovements: gateway.registerMovements,
          checkoutBusy:
              counter.pending != null ||
              counter.posting ||
              counter.canWrite && !counter.pendingAvailable ||
              _returnBlocksWrites,
        ),
        const SizedBox(height: 16),
        PosDisclosure(
          boxed: true,
          title: 'Daily totals and CSV export',
          children: [_dailyPanel(inDisclosure: true)],
        ),
      ] else
        _dailyPanel(inDisclosure: false),
    ],
  );

  Widget _dailyPanel({required bool inDisclosure}) => PosDailyPanel(
    companyName: widget.workspace.company.name,
    loadRecords: gateway.reconciliationRecords,
    today: businessDate,
    inDisclosure: inDisclosure,
  );

  Widget _header() {
    final today = businessDate();
    final sales = counter.receipts
        .where((receipt) => receipt.posted && receipt.date == today)
        .toList();
    final total = sales.fold<int>(0, (sum, receipt) => sum + receipt.paise);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PosHeader(
          salesTotal: counter.loadingReceipts && counter.receipts.isEmpty
              ? '—'
              : posMoneyText(total),
          receiptCount: counter.loadingReceipts && counter.receipts.isEmpty
              ? 'Loading sales…'
              : '${sales.length} ${sales.length == 1 ? 'receipt' : 'receipts'}',
        ),
        const SizedBox(height: 18),
        PosViewTabs<_PosView>(
          selected: _view,
          onSelected: _selectView,
          tabs: [
            const PosTabItem(
              _PosView.checkout,
              'Checkout',
              Icons.shopping_bag_outlined,
            ),
            const PosTabItem(
              _PosView.receipts,
              'Receipts',
              Icons.receipt_long_outlined,
            ),
            const PosTabItem(
              _PosView.register,
              'Register',
              Icons.account_balance_wallet_outlined,
            ),
          ],
        ),
      ],
    );
  }

  Widget _mobilePaymentShortcut() {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final quote = counter.quote;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(top: BorderSide(color: colors.outlineVariant)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  quote == null ? _lineCount : posMoneyText(quote.paise),
                  style: theme.textTheme.titleMedium,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              FilledButton.icon(
                key: const ValueKey('pos-go-to-payment'),
                onPressed: () {
                  final target = _paymentAnchor.currentContext;
                  if (target != null) {
                    FocusManager.instance.primaryFocus?.unfocus();
                    Scrollable.ensureVisible(
                      target,
                      duration: const Duration(milliseconds: 240),
                      curve: Curves.easeOutCubic,
                    );
                  }
                },
                icon: const Icon(Icons.payments_outlined, size: 18),
                label: const Text('Go to payment'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String get _lineCount {
    final count = counter.cart.length;
    return '$count ${count == 1 ? 'item line' : 'item lines'}';
  }

  Widget _checkout(bool wide) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!counter.canWrite)
          const _PosNotice('View-only access. Receipts are available.'),
        if (counter.recoveryError case final error?)
          _PosNotice(
            error,
            action: 'Try recovery',
            onAction: counter.recoverPending,
          ),
        if (counter.status case final status?) _PosNotice(status),
        if (counter.checkingPending)
          const _PosNotice('Checking for a saved sale…'),
        if (counter.completed case final receipt?) _success(receipt),
        if (counter.pending != null) ...[
          _sheet([
            Text(
              'Sale awaiting confirmation',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const Text(
              'The original payment details are saved. Retry to retrieve its receipt or confirm that it was rejected.',
            ),
            FilledButton.icon(
              key: const ValueKey('pos-retry-sale'),
              onPressed: counter.ready ? _complete : null,
              icon: const Icon(Icons.refresh),
              label: Text(
                counter.posting ? 'Confirming sale…' : 'Retry original sale',
              ),
            ),
          ]),
        ] else if (wide)
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 11, child: _catalogue(wide: true)),
              const SizedBox(width: 16),
              Expanded(flex: 9, child: _sale()),
            ],
          )
        else ...[
          _catalogue(wide: false),
          const SizedBox(height: 14),
          _sale(),
        ],
      ],
    );
  }

  Widget _sheet(List<Widget> children, {Key? key, double spacing = 12}) =>
      PosPanel(key: key, spacing: spacing, children: children);

  Widget _sectionHeading(String title, {String? detail}) =>
      PosPanelHeading(title, detail: detail);

  PosProduct? _exactMatch(List<PosProduct> items, String value) {
    final code = value.trim();
    if (code.isEmpty) return null;
    var matches = items.where((item) => item.barcode == code).toList();
    if (matches.isEmpty) {
      matches = items
          .where((item) => item.name.trim().toLowerCase() == code.toLowerCase())
          .toList();
    }
    return matches.length == 1 ? matches.single : null;
  }

  Widget _catalogue({required bool wide}) {
    final query = _scanner.text.trim().toLowerCase();
    final all = counter.products;
    final filtered = all
        .where(
          (product) =>
              product.searchText(counter.locationNames).contains(query),
        )
        .toList();
    final exact = query.isEmpty ? null : _exactMatch(filtered, _scanner.text);
    final ordered = exact == null
        ? filtered
        : [exact, ...filtered.where((product) => product.id != exact.id)];
    final shown = ordered.take(30).toList();
    final list = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 7,
      children: [for (final product in shown) _productTile(product)],
    );
    return _sheet(spacing: 9, [
      _sectionHeading(
        'Products',
        detail: counter.loadingProducts || counter.productsError != null
            ? null
            : '${all.length} ${all.length == 1 ? 'item' : 'items'}',
      ),
      TextField(
        key: const ValueKey('pos-barcode'),
        controller: _scanner,
        focusNode: _scannerFocus,
        autofocus: widget.active && counter.canWrite && _desktopScanner,
        textInputAction: TextInputAction.go,
        onSubmitted: _scan,
        onChanged: (_) => setState(() {}),
        style: const TextStyle(fontSize: 15),
        decoration: posFieldDecoration(
          hint: 'Scan barcode or search',
          prefix: const Icon(Icons.qr_code_scanner, size: 22),
          suffix: _scanner.text.isEmpty
              ? const Icon(Icons.search, size: 18)
              : TextButton(
                  onPressed: () => setState(_scanner.clear),
                  child: const Text('Clear'),
                ),
        ),
      ),
      if (_androidCamera && counter.canWrite)
        if (_cameraOpen && widget.active && counter.editable)
          PosBarcodeCamera(
            onBarcode: _cameraRead,
            onClose: _closeCamera,
            previewBuilder: widget.cameraPreview,
          )
        else
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              onPressed:
                  widget.active && counter.editable && !counter.loadingProducts
                  ? _openCamera
                  : null,
              icon: const Icon(Icons.camera_alt_outlined),
              label: const Text('Scan with camera'),
            ),
          ),
      if (!wide && counter.cart.isNotEmpty)
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(minimumSize: const Size(0, 44)),
          onPressed: () {
            final target = _cartHeading.currentContext;
            if (target != null) {
              Scrollable.ensureVisible(
                target,
                duration: const Duration(milliseconds: 240),
              );
            }
          },
          icon: const Icon(Icons.shopping_bag_outlined, size: 17),
          label: Text('Review sale · $_lineCount'),
        ),
      if (counter.loadingProducts) const LinearProgressIndicator(),
      if (counter.productsError case final error?)
        _PosNotice(error, action: 'Retry', onAction: counter.loadProducts),
      if (counter.stockError case final error?)
        _PosNotice(error, action: 'Refresh stock', onAction: counter.loadStock),
      if (shown.isNotEmpty)
        wide
            ? list
            : ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 320),
                child: Scrollbar(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(3),
                    child: list,
                  ),
                ),
              ),
      if (counter.loadingProducts)
        const Text('Loading the product catalogue…', style: _small),
      if (!counter.loadingProducts &&
          all.isEmpty &&
          counter.productsError == null)
        const Text('Add items in Items to start selling.', style: _small),
      if (all.isNotEmpty && filtered.isEmpty)
        const Text('No matching items.', style: _small),
      if (filtered.length > shown.length)
        Text(
          'Showing ${shown.length} of ${filtered.length} products. Search or scan to find a specific item.',
          style: _small,
        ),
    ]);
  }

  static const _small = TextStyle(fontSize: 13, color: Apex.muted);

  Widget _thumbnail(PosProduct product) {
    final uri = product.thumbnail;
    if (uri.startsWith('data:image') && uri.contains(',')) {
      try {
        return ClipRRect(
          borderRadius: BorderRadius.circular(7),
          child: Image.memory(
            base64Decode(uri.substring(uri.indexOf(',') + 1)),
            width: 41,
            height: 41,
            fit: BoxFit.contain,
            gaplessPlayback: true,
            errorBuilder: (_, _, _) => _fallbackTile(),
          ),
        );
      } catch (_) {
        return _fallbackTile();
      }
    }
    return _fallbackTile();
  }

  Widget _fallbackTile() => const ApexIconTile(
    Icons.inventory_2_outlined,
    background: PosColors.media,
    foreground: Apex.label,
    size: 41,
    iconSize: 19,
    radius: 7,
  );

  Widget _productTile(PosProduct product) {
    final available = counter.stock[product.id];
    final stockLabel = counter.loadingStock
        ? 'Checking book stock…'
        : available == null
        ? 'Book stock: Unavailable'
        : 'Book stock: $available';
    final outOfStock =
        !counter.loadingStock &&
        (available == null || (double.tryParse(available) ?? 0) <= 0);
    final shelves = posLocationNames(product, counter.locationNames);
    const meta = TextStyle(fontSize: 12, height: 1.45, color: Apex.muted);
    final enabled = counter.editable;
    return Material(
      key: ValueKey('product-${product.id}'),
      color: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: PosColors.rule),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: enabled
            ? () {
                counter.add(product);
                _scanner.clear();
                if (widget.active && _desktopScanner) {
                  _scannerFocus.requestFocus();
                }
              }
            : null,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 67),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
            child: Row(
              children: [
                _thumbnail(product),
                const SizedBox(width: 11),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        product.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: Apex.ink,
                        ),
                      ),
                      if (product.barcode.isNotEmpty)
                        Text(
                          product.barcode,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: meta,
                        ),
                      if (shelves.isNotEmpty)
                        Row(
                          key: ValueKey('location-${product.id}'),
                          children: [
                            const Icon(
                              Icons.place_outlined,
                              size: 11,
                              color: Apex.muted,
                            ),
                            const SizedBox(width: 3),
                            Expanded(
                              child: Text(
                                shelves.join(' · '),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: meta,
                              ),
                            ),
                          ],
                        ),
                      if (product.tracked)
                        Text(
                          stockLabel,
                          style: outOfStock && !counter.loadingStock
                              ? meta.copyWith(
                                  color: PosColors.warn,
                                  fontWeight: FontWeight.w700,
                                )
                              : meta,
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  posMoneyText(parsePosMoney(product.rate) ?? 0),
                  textAlign: TextAlign.end,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: Apex.ink,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
                if (enabled) ...[
                  const SizedBox(width: 9),
                  const Icon(Icons.add, size: 17, color: PosColors.green),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<bool> _confirm(String message, String action) async =>
      await showDialog<bool>(
        context: context,
        builder: (dialog) => AlertDialog(
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialog, true),
              child: Text(action),
            ),
          ],
        ),
      ) ??
      false;

  Widget _heldSales() {
    final held = counter.held.sales;
    return PosDisclosure(
      key: ValueKey('held-${counter.cart.isEmpty}-${held.length}'),
      title: 'Held sales (${held.length})',
      initiallyExpanded: counter.cart.isEmpty,
      children: [
        for (final saved in held)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: Apex.line)),
            ),
            child: Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              alignment: WrapAlignment.spaceBetween,
              children: [
                Text(
                  '${saved.customer.trim().isEmpty ? 'Walk-in customer' : saved.customer} · ${saved.lines.length} item lines',
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    OutlinedButton(
                      onPressed: counter.editable && counter.cart.isEmpty
                          ? () => counter.recallSale(saved)
                          : null,
                      child: const Text('Resume'),
                    ),
                    TextButton(
                      onPressed: counter.editable
                          ? () async {
                              if (await _confirm(
                                'Discard this held sale?',
                                'Discard',
                              )) {
                                counter.discardHeld(saved);
                              }
                            }
                          : null,
                      child: const Text('Discard'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        if (counter.cart.isNotEmpty)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Hold or finish the current sale before resuming another.',
              style: _small,
            ),
          ),
        const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
            'Held sales stay in the app while it is open. They do not reserve stock.',
            style: _small,
          ),
        ),
      ],
    );
  }

  Widget _sale() {
    final theme = Theme.of(context);
    final hasLines = counter.cart.isNotEmpty;
    return _sheet(spacing: 9, [
      KeyedSubtree(
        key: _cartHeading,
        child: _sectionHeading('Current sale', detail: _lineCount),
      ),
      if (counter.held.sales.isNotEmpty) _heldSales(),
      if (!hasLines)
        PosDashedBox(
          child: Column(
            children: [
              const Icon(
                Icons.shopping_bag_outlined,
                size: 25,
                color: PosColors.emptyText,
              ),
              const SizedBox(height: 6),
              const Text(
                'Your cart is empty',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: PosColors.emptyText,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Scan a barcode or choose a product to start.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontSize: 13,
                  color: PosColors.muted,
                ),
              ),
            ],
          ),
        ),
      for (final line in counter.cart) _line(line),
      if (hasLines)
        Wrap(
          spacing: 8,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            OutlinedButton(
              key: const ValueKey('pos-hold-sale'),
              onPressed: counter.canHold
                  ? () {
                      _pricingLines.clear();
                      _scanner.clear();
                      counter.holdSale();
                    }
                  : null,
              child: const Text('Hold sale'),
            ),
            TextButton(
              key: const ValueKey('pos-clear-sale'),
              onPressed: counter.editable
                  ? () async {
                      if (await _confirm(
                        'Clear the current sale?',
                        'Clear sale',
                      )) {
                        _pricingLines.clear();
                        _scanner.clear();
                        counter.clearSale();
                      }
                    }
                  : null,
              child: const Text('Clear sale'),
            ),
          ],
        ),
      if (hasLines) _billing(),
      if (hasLines) _paymentFields(),
      _totalBand(),
      if (hasLines) _checkingTotal(),
      _completeButton(),
    ]);
  }

  Widget _billing() => DecoratedBox(
    decoration: const BoxDecoration(
      border: Border.symmetric(horizontal: BorderSide(color: PosColors.rule)),
    ),
    child: Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 8),
        minTileHeight: 46,
        title: Text.rich(
          TextSpan(
            text: 'Customer and billing',
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: Color(0xff36594b),
            ),
            children: [
              TextSpan(
                text:
                    '  ${counter.customer.trim().isEmpty ? 'Walk-in customer' : counter.customer}',
                style: const TextStyle(
                  fontWeight: FontWeight.w500,
                  color: PosColors.muted,
                ),
              ),
            ],
          ),
        ),
        children: [
          _PartyField(
            value: counter.customer,
            parties: [for (final party in counter.parties) party.name],
            enabled: counter.editable,
            onChanged: (value) => counter.changeBilling(customer: value),
          ),
          const SizedBox(height: 10),
          _PosInput(
            value: counter.billingAddress,
            label: 'Billing address',
            maxLength: 500,
            enabled: counter.editable,
            onChanged: (value) => counter.changeBilling(address: value),
          ),
          const SizedBox(height: 10),
          _fieldGroup([
            _PosInput(
              value: counter.billingGstin,
              label: 'Customer GSTIN',
              maxLength: 15,
              enabled: counter.editable,
              onChanged: (value) => counter.changeBilling(gstin: value),
            ),
            _PosInput(
              value: counter.billingPhone,
              label: 'Customer phone',
              maxLength: 32,
              enabled: counter.editable,
              onChanged: (value) => counter.changeBilling(phone: value),
            ),
          ]),
          if (!counter.unregistered) ...[
            const SizedBox(height: 10),
            _PosInput(
              value: counter.placeOfSupply,
              label: 'Place of supply (state code)',
              maxLength: 2,
              numeric: true,
              enabled: counter.editable,
              error: counter.billingValid ? null : 'Enter a two-digit state code.',
              onChanged: (value) => counter.changeBilling(place: value),
            ),
          ],
          if (counter.regularTax)
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              title: const Text('Prices include GST'),
              value: counter.inclusive,
              onChanged: counter.editable
                  ? (value) => counter.changeBilling(inclusive: value)
                  : null,
            ),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text('Round total to nearest rupee'),
            value: counter.round,
            onChanged: counter.editable
                ? (value) => counter.changeBilling(round: value)
                : null,
          ),
        ],
      ),
    ),
  );

  Widget _line(PosLine line) {
    final theme = Theme.of(context);
    final id = line.product.id;
    final editingPrice = _pricingLines.contains(id);
    final milli = line.quantityMilli;
    final unit = line.product.unit;
    final unitRate = parsePosMoney(line.rate);
    return DecoratedBox(
      key: ValueKey('line-$id'),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: PosColors.rule),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 6, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        line.product.name,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: Apex.ink,
                        ),
                      ),
                      if (unitRate != null)
                        Text(
                          '${posMoneyText(unitRate)} / ${unit.isEmpty ? 'unit' : unit}',
                          style: const TextStyle(
                            fontSize: 12,
                            color: PosColors.muted,
                          ),
                        ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Remove ${line.product.name}',
                  onPressed: counter.editable
                      ? () {
                          _pricingLines.remove(id);
                          counter.remove(line);
                        }
                      : null,
                  icon: const Icon(Icons.delete_outline, size: 18),
                ),
              ],
            ),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      tooltip: 'Decrease quantity for ${line.product.name}',
                      color: PosColors.green,
                      onPressed:
                          counter.editable && milli != null && milli > 1000
                          ? () => counter.changeLine(
                              line,
                              quantity: _plainQuantity(
                                posDecimalText(milli - 1000, 3),
                              ),
                            )
                          : null,
                      icon: const Icon(Icons.remove, size: 18),
                    ),
                    SizedBox(
                      width: 104,
                      child: _PosInput(
                        key: ValueKey('quantity-$id'),
                        value: line.quantity,
                        label: unit.isEmpty ? 'Quantity' : 'Quantity ($unit)',
                        visibleLabel: 'Qty',
                        numeric: true,
                        compact: true,
                        enabled: counter.editable,
                        onChanged: (value) =>
                            counter.changeLine(line, quantity: value),
                      ),
                    ),
                    IconButton(
                      tooltip: 'Increase quantity for ${line.product.name}',
                      color: PosColors.green,
                      onPressed: counter.editable && milli != null
                          ? () => counter.add(line.product)
                          : null,
                      icon: const Icon(Icons.add, size: 18),
                    ),
                  ],
                ),
                TextButton.icon(
                  onPressed: () => setState(() {
                    if (editingPrice) {
                      _pricingLines.remove(id);
                    } else {
                      _pricingLines.add(id);
                    }
                  }),
                  icon: Icon(
                    editingPrice ? Icons.expand_more : Icons.chevron_right,
                    size: 18,
                  ),
                  label: const Text('Price and discount'),
                ),
              ],
            ),
            if (editingPrice) ...[
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: _fieldGroup([
                  _PosInput(
                    value: line.rate,
                    label: 'Rate (₹)',
                    numeric: true,
                    enabled: counter.editable,
                    onChanged: (value) => counter.changeLine(line, rate: value),
                  ),
                  _PosInput(
                    value: line.discount,
                    label: 'Discount amount (₹)',
                    enabled: counter.editable,
                    numeric: true,
                    onChanged: (value) =>
                        counter.changeLine(line, discount: value),
                  ),
                ]),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _paymentFields() {
    final quote = counter.quote;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 10,
      children: [
        const SizedBox(height: 2),
        DropdownButtonFormField<PosTender>(
          key: ValueKey('method-${counter.tender.name}'),
          initialValue: counter.tender,
          decoration: const InputDecoration(labelText: 'Payment method'),
          onChanged: counter.editable
              ? (method) => counter.changePayment(method: method)
              : null,
          items: [
            const DropdownMenuItem(value: PosTender.cash, child: Text('Cash')),
            const DropdownMenuItem(
              value: PosTender.bank,
              child: Text('Bank / UPI / card'),
            ),
            if (counter.splitSupported)
              const DropdownMenuItem(
                value: PosTender.split,
                child: Text('Cash + bank / UPI / card'),
              ),
          ],
          isExpanded: true,
        ),
        if (counter.needsBank) ...[
          if (counter.bankError case final error?)
            _PosNotice(error, action: 'Retry', onAction: counter.loadBanks),
          DropdownButtonFormField<String>(
            key: ValueKey('bank-${counter.bankId}'),
            initialValue: counter.banks.any((bank) => bank.id == counter.bankId)
                ? counter.bankId
                : null,
            decoration: const InputDecoration(labelText: 'Receiving bank'),
            isExpanded: true,
            items: [
              for (final account in counter.banks)
                DropdownMenuItem(value: account.id, child: Text(account.label)),
            ],
            onChanged: counter.editable
                ? (id) => counter.changePayment(bankId: id)
                : null,
          ),
        ],
        if (counter.tender != PosTender.bank)
          _fieldGroup([
            if (counter.tender == PosTender.split)
              _PosInput(
                value: counter.bankText,
                label: 'Bank / UPI / card amount (₹)',
                numeric: true,
                enabled: counter.editable,
                onChanged: (value) => counter.changePayment(bankText: value),
              ),
            _PosInput(
              key: const ValueKey('pos-cash'),
              value: counter.cashText,
              label: 'Cash tendered (₹)',
              numeric: true,
              enabled: counter.editable,
              onChanged: (value) => counter.changePayment(cashText: value),
            ),
          ]),
        if (counter.needsBank)
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text('Bank, UPI or card payment received'),
            value: counter.bankConfirmed,
            onChanged: counter.editable && quote != null
                ? (value) => counter.changePayment(confirmed: value)
                : null,
          ),
        if (_registerBlocksSale)
          _PosNotice(
            'Check the saved register activity before completing another sale.',
            action: 'Open register',
            onAction: () => _selectView(_PosView.register),
          ),
      ],
    );
  }

  Widget _totalBand() {
    final theme = Theme.of(context);
    final quote = counter.quote;
    final payment = counter.payment;
    const text = PosColors.totalText;
    int amount(String name) {
      final raw = posText(quote?.data[name]);
      return parsePosMoney(raw.startsWith('-') ? raw.substring(1) : raw) ?? 0;
    }

    final gst = amount('cgst') + amount('sgst') + amount('igst');
    final splitNeedsAmount =
        counter.tender == PosTender.split &&
        (payment.error == 'Enter a bank amount below the total.');
    final showCash =
        quote != null &&
        counter.tender != PosTender.bank &&
        !splitNeedsAmount &&
        payment.cash > 0;
    final short = payment.tendered < payment.cash;
    return Container(
      key: _paymentAnchor,
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      decoration: BoxDecoration(
        color: PosColors.wash,
        border: Border.all(color: PosColors.totalBorder),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 3,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Total payable',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: text,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 2,
                child: Semantics(
                  liveRegion: true,
                  child: Text(
                    quote == null
                        ? (counter.cart.isEmpty ? posMoneyText(0) : '—')
                        : posMoneyText(quote.paise),
                    key: const ValueKey('pos-total'),
                    textAlign: TextAlign.end,
                    style: const TextStyle(
                      fontFamily: Apex.display,
                      fontSize: 28,
                      height: 1.15,
                      letterSpacing: -.7,
                      fontWeight: FontWeight.w700,
                      color: text,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
              ),
            ],
          ),
          if (quote != null && counter.regularTax)
            Text(
              'GST ${posMoneyText(gst)}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: PosColors.muted,
              ),
            ),
          if (showCash)
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              spacing: 12,
              runSpacing: 4,
              children: [
                Text(
                  'Cash due ${posMoneyText(payment.cash)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: PosColors.muted,
                  ),
                ),
                Text(
                  short
                      ? 'Still needed ${posMoneyText(payment.cash - payment.tendered)}'
                      : 'Change ${posMoneyText(payment.change)}',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: short ? PosColors.warn : text,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          if (quote != null && splitNeedsAmount)
            Text(
              'Enter a bank amount greater than zero and less than the total.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: PosColors.muted,
              ),
            ),
        ],
      ),
    );
  }

  Widget _checkingTotal() {
    if (counter.cart.isEmpty || counter.quote != null) {
      return const SizedBox.shrink();
    }
    if (counter.quoteError case final error?) {
      return _PosNotice(
        error,
        action: 'Refresh total',
        onAction: counter.refreshQuote,
      );
    }
    return const Text('Checking sale total…', style: _small);
  }

  Widget _completeButton() => SizedBox(
    height: 46,
    child: FilledButton(
      key: const ValueKey('pos-complete-sale'),
      onPressed: counter.ready && !_registerBlocksSale && !_returnBlocksWrites
          ? _complete
          : null,
      child: Text(
        counter.posting ? 'Posting sale…' : 'Complete sale',
        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
      ),
    ),
  );

  Widget _fieldGroup(List<Widget> children) => LayoutBuilder(
    builder: (context, limits) {
      if (children.length == 1) return children.single;
      if (limits.maxWidth < 345) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [children.first, const SizedBox(height: 8), children.last],
        );
      }
      return Row(
        children: [
          Expanded(child: children.first),
          const SizedBox(width: 10),
          Expanded(child: children.last),
        ],
      );
    },
  );



  Widget _success(PosReceipt receipt) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: DecoratedBox(
      decoration: BoxDecoration(
        color: PosColors.successFill,
        border: Border.all(color: PosColors.successBorder),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Stack(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 42, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: 10,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.check_circle_outline,
                      size: 23,
                      color: PosColors.successText,
                    ),
                    const SizedBox(width: 11),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            receipt.posted
                                ? 'Sale completed'
                                : 'Sale was cancelled',
                            style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: PosColors.successText,
                            ),
                          ),
                          Text(
                            '${receipt.number} · ${posMoneyText(receipt.paise)}',
                            style: const TextStyle(
                              fontSize: 13,
                              color: Color(0xff426454),
                            ),
                          ),
                          if (receipt.posted && receipt.change > 0)
                            Text(
                              'Change ${posMoneyText(receipt.change)}',
                              style: const TextStyle(
                                fontSize: 13,
                                color: Color(0xff426454),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (receipt.posted &&
                        widget.workspace.features.contains('thermal_receipts'))
                      PopupMenuButton<int>(
                        enabled: !_printing,
                        tooltip: 'Print receipt',
                        onSelected: (width) => _printReceipt(receipt, width),
                        itemBuilder: (_) => const [
                          PopupMenuItem(value: 80, child: Text('80 mm roll')),
                          PopupMenuItem(value: 58, child: Text('58 mm roll')),
                        ],
                        child: _menuButton(
                          Icons.print_outlined,
                          'Print receipt',
                          trailing: Icons.expand_more,
                        ),
                      ),
                    OutlinedButton.icon(
                      onPressed: _printing
                          ? null
                          : () => _downloadDocument(receipt.id, receipt.number),
                      icon: const Icon(Icons.download_outlined, size: 18),
                      label: const Text('Download receipt'),
                    ),
                    OutlinedButton.icon(
                      onPressed: () => _openReceipt(receipt),
                      icon: const Icon(Icons.receipt_long_outlined, size: 18),
                      label: const Text('View receipt'),
                    ),
                  ],
                ),
                if (_printing) const LinearProgressIndicator(),
                if (_printError case final error?) _PosNotice(error),
              ],
            ),
          ),
          Positioned(
            top: 4,
            right: 4,
            child: IconButton(
              tooltip: 'Dismiss receipt',
              onPressed: counter.dismissCompleted,
              icon: const Icon(Icons.close, size: 18),
            ),
          ),
        ],
      ),
    ),
  );

  Widget _menuButton(IconData icon, String label, {IconData? trailing}) =>
      DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(color: Apex.line),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 18),
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: Apex.ink,
                ),
              ),
              if (trailing != null) ...[
                const SizedBox(width: 4),
                Icon(trailing, size: 16),
              ],
            ],
          ),
        ),
      );

  /// "Download receipt" / credit note / refund voucher: the default PDF.
  Future<void> _downloadDocument(String id, String number) async {
    if (_printing) return;
    final source = gateway;
    setState(() {
      _printing = true;
      _printError = null;
    });
    try {
      final document = await source.documentPdf(id, number);
      await saveApexFile(document.name, document.bytes, 'application/pdf');
    } catch (error) {
      _printError = switch (error) {
        PosFailure() => error.message,
        FormatException() => error.message,
        _ => 'Could not save the PDF.',
      };
    } finally {
      if (mounted && identical(source, gateway)) {
        setState(() => _printing = false);
      }
    }
  }

  Widget _receipts() {
    final query = _receiptSearch.text.trim().toLowerCase();
    final receipts = counter.receipts
        .where(
          (receipt) =>
              (_receiptDate.isEmpty || receipt.date == _receiptDate) &&
              '${receipt.number} ${receipt.customer}'.toLowerCase().contains(
                query,
              ),
        )
        .toList();
    final shown = receipts.take(_receiptLimit).toList();
    final thermal = widget.workspace.features.contains('thermal_receipts');
    final canReturn =
        _returns?.canWrite == true &&
        !_otherActionPending &&
        !_returnBlocksWrites;
    return _sheet(spacing: 12, [
      _sectionHeading(
        'Receipt history',
        detail: counter.loadingReceipts && counter.receipts.isEmpty
            ? 'Loading…'
            : '${receipts.length} ${receipts.length == 1 ? 'receipt' : 'receipts'}',
      ),
      PosFieldRow([
        TextField(
          controller: _receiptSearch,
          onChanged: (_) => setState(() => _receiptLimit = 20),
          decoration: posFieldDecoration(
            label: 'Search loaded receipts',
            hint: 'Search receipts',
            prefix: const Icon(Icons.search, size: 20),
          ),
        ),
        TextField(
          key: const ValueKey('pos-receipt-date'),
          readOnly: true,
          controller: _receiptDateText
            ..text = _receiptDate.isEmpty ? '' : apexDate(_receiptDate),
          onTap: _pickReceiptDate,
          decoration: posFieldDecoration(
            label: 'Sale date',
            hint: 'Any date',
            suffix: const Icon(Icons.calendar_today_outlined, size: 18),
          ),
        ),
      ]),
      Align(
        alignment: Alignment.centerLeft,
        child: Wrap(
          spacing: 8,
          children: [
            OutlinedButton(
              onPressed: () => setState(() {
                _receiptDate = _receiptDate.isEmpty ? businessDate() : '';
                _receiptLimit = 20;
              }),
              child: Text(_receiptDate.isEmpty ? 'Show today' : 'Show all dates'),
            ),
            TextButton.icon(
              onPressed: counter.loadingReceipts
                  ? null
                  : () => counter.loadReceipts(reset: true),
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Refresh receipts'),
            ),
          ],
        ),
      ),
      if (counter.loadingReceipts) const LinearProgressIndicator(),
      if (counter.receiptsError case final error?) _PosNotice(error),
      if (_printing) const LinearProgressIndicator(),
      if (_printError case final error?) _PosNotice(error),
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final receipt in shown)
            DecoratedBox(
              decoration: const BoxDecoration(
                border: Border(bottom: BorderSide(color: Apex.line)),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 520),
                      child: InkWell(
                        onTap: () => _openReceipt(receipt),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Wrap(
                              crossAxisAlignment: WrapCrossAlignment.center,
                              children: [
                                Text(
                                  receipt.number,
                                  style: const TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w700,
                                    color: Apex.ink,
                                  ),
                                ),
                                Text(
                                  ' · ${receipt.customer}',
                                  style: const TextStyle(
                                    fontSize: 15,
                                    color: Apex.ink,
                                  ),
                                ),
                              ],
                            ),
                            Text(
                              '${receipt.date} · ${posMoneyText(receipt.paise)}${receipt.posted ? '' : ' · Cancelled'}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: PosColors.muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        OutlinedButton(
                          onPressed: () => _openReceipt(receipt),
                          child: const Text('View receipt'),
                        ),
                        if (receipt.posted && thermal)
                          OutlinedButton(
                            onPressed: _printing
                                ? null
                                : () => _printReceipt(receipt, 80),
                            child: const Text('Reprint 80 mm'),
                          ),
                        if (receipt.posted && _returns?.canWrite == true)
                          OutlinedButton(
                            onPressed: canReturn
                                ? () => _openReturn(receipt)
                                : null,
                            child: const Text('Start return'),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
      if (!counter.loadingReceipts && receipts.isEmpty)
        const Text('No receipts match your filters.', style: _small),
      if (receipts.length > _receiptLimit)
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton(
            onPressed: () => setState(() => _receiptLimit += 20),
            child: const Text('Show more receipts'),
          ),
        )
      else if (!counter.loadingReceipts &&
          counter.hasMoreReceipts &&
          counter.receipts.isNotEmpty)
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton(
            onPressed: () => counter.loadReceipts(),
            child: const Text('Load more receipts'),
          ),
        ),
    ]);
  }

  Future<void> _pickReceiptDate() async {
    final today = DateTime.parse(businessDate());
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(_receiptDate) ?? today,
      firstDate: DateTime(2000),
      lastDate: today.add(const Duration(days: 1)),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _receiptDate = picked.toIso8601String().substring(0, 10);
      _receiptLimit = 20;
    });
  }

  void _openReceipt(PosReceipt receipt) {
    setState(() {
      _viewedReceipt = receipt;
      _receiptDetail = gateway.receipt(receipt.id);
      _showReturn = false;
      _printError = null;
      _receiptActionRevision++;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
  }

  Widget _receiptView(PosReceipt receipt) => FutureBuilder<PosReceipt>(
    key: ValueKey(receipt.id),
    initialData: receipt,
    future: _receiptDetail,
    builder: (context, snapshot) {
      final theme = Theme.of(context);
      final record = snapshot.data ?? receipt;
      final lines = record.data['lines'];
      return _sheet([
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => _selectView(_view),
            icon: const Icon(Icons.arrow_back),
            label: Text(_history ? 'Back to receipts' : 'Back to checkout'),
          ),
        ),
        Text(receipt.number, style: theme.textTheme.titleLarge),
        Text('${record.customer} · ${record.date}'),
        Text(record.posted ? 'Posted' : 'Cancelled'),
        Text(
          'Total ${posMoneyText(record.paise)}',
          style: theme.textTheme.headlineSmall,
        ),
        if (record.data['payment_account'] case final String method)
          Text(switch (method) {
            'bank' => 'Paid by bank / UPI / card',
            'split' => 'Paid by cash and bank',
            _ => 'Paid in cash',
          }),
        if (record.change > 0) Text('Change ${posMoneyText(record.change)}'),
        if (record.posted &&
            widget.workspace.features.contains('thermal_receipts'))
          _thermalActions(record, allowSave: true),
        if (snapshot.connectionState == ConnectionState.waiting)
          const LinearProgressIndicator(),
        if (snapshot.hasError)
          _PosNotice(
            'Receipt details could not be loaded.',
            action: 'Retry',
            onAction: () => _openReceipt(receipt),
          ),
        if (snapshot.connectionState == ConnectionState.done &&
            !snapshot.hasError &&
            record.posted &&
            _returns?.canWrite == true)
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.tonalIcon(
              onPressed: _otherActionPending || _returnBlocksWrites
                  ? null
                  : () => _openReturn(record),
              icon: const Icon(Icons.assignment_return_outlined),
              label: const Text('Return items'),
            ),
          ),
        if (lines is List)
          for (final line in lines.whereType<PosJson>())
            Text(
              '${posText(line['quantity'])} × ${posText(line['description'])}',
            ),
      ]);
    },
  );

  void _openReturn(PosReceipt receipt) {
    final returns = _returns;
    if (returns == null ||
        !returns.canWrite ||
        !receipt.posted ||
        _otherActionPending ||
        returns.blocksWrites) {
      return;
    }
    setState(() {
      _showReturn = true;
      _printError = null;
      _receiptActionRevision++;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
    unawaited(returns.start(receipt.id));
  }

  void _openReturnRecovery() {
    setState(() {
      _showReturn = true;
      _receiptActionRevision++;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
  }

  void _closeReturn() {
    if (_viewedReceipt == null) {
      _selectView(_PosView.receipts);
      return;
    }
    setState(() => _showReturn = false);
    if (_scroll.hasClients) _scroll.jumpTo(0);
  }

  Widget _thermalActions(PosReceipt receipt, {bool allowSave = false}) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final width in [58, 80])
                OutlinedButton.icon(
                  onPressed: _printing
                      ? null
                      : () => _printReceipt(receipt, width),
                  icon: const Icon(Icons.print_outlined),
                  label: Text('Print $width mm'),
                ),
              if (allowSave)
                PopupMenuButton<int>(
                  enabled: !_printing,
                  tooltip: 'Save receipt PDF',
                  onSelected: (width) =>
                      _printReceipt(receipt, width, save: true),
                  itemBuilder: (_) => const [
                    PopupMenuItem(value: 58, child: Text('Save 58 mm PDF')),
                    PopupMenuItem(value: 80, child: Text('Save 80 mm PDF')),
                  ],
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 8,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: const [
                        Icon(Icons.download_outlined, size: 18),
                        SizedBox(width: 8),
                        Text('Save PDF'),
                      ],
                    ),
                  ),
                ),
            ],
          ),
          if (allowSave)
            Text(
              'Choose the matching roll in your printer settings.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          if (_printing) const LinearProgressIndicator(),
          if (_printError case final error?) _PosNotice(error),
        ],
      );

  Future<void> _printReceipt(
    PosReceipt receipt,
    int width, {
    bool save = false,
  }) async {
    if (_printing || !widget.active) return;
    final source = gateway;
    final revision = _receiptActionRevision;
    bool current() =>
        mounted &&
        widget.active &&
        identical(source, gateway) &&
        revision == _receiptActionRevision;
    setState(() {
      _printing = true;
      _printError = null;
    });
    try {
      final document = await source.receiptPdf(receipt, width);
      if (!current()) return;
      if (save) {
        await saveApexFile(document.name, document.bytes, 'application/pdf');
      } else {
        await widget.pdfOutput.print(document);
      }
    } catch (error) {
      if (current()) {
        _printError = switch (error) {
          PosFailure() => error.message,
          FormatException() => error.message,
          UnsupportedError() => error.message,
          _ =>
            save
                ? 'Could not save the receipt PDF.'
                : 'Could not send the receipt to the printer.',
        };
      }
    } finally {
      if (mounted && identical(source, gateway)) {
        setState(() => _printing = false);
      }
    }
  }
}

String _plainQuantity(String raw) =>
    raw.contains('.') ? raw.replaceFirst(RegExp(r'\.?0+$'), '') : raw;

class _PosNotice extends StatelessWidget {
  const _PosNotice(this.message, {this.action, this.onAction});

  final String message;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      margin: const EdgeInsets.only(bottom: 4),
      decoration: BoxDecoration(
        color: colors.secondaryContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Wrap(
        spacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Semantics(liveRegion: true, child: Text(message)),
          if (action case final label?)
            TextButton(onPressed: onAction, child: Text(label)),
        ],
      ),
    );
  }
}

class _PosInput extends StatefulWidget {
  const _PosInput({
    required this.value,
    required this.label,
    required this.enabled,
    required this.onChanged,
    this.numeric = false,
    this.compact = false,
    this.visibleLabel,
    this.maxLength,
    this.error,
    super.key,
  });

  final int? maxLength;
  final String? error;
  final String value;
  final String label;
  final bool enabled;
  final bool numeric;
  final bool compact;
  final String? visibleLabel;
  final ValueChanged<String> onChanged;

  @override
  State<_PosInput> createState() => _PosInputState();
}

class _PosInputState extends State<_PosInput> {
  late final TextEditingController _text = TextEditingController(
    text: widget.value,
  );

  @override
  void didUpdateWidget(covariant _PosInput oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_text.text != widget.value) {
      _text.value = TextEditingValue(
        text: widget.value,
        selection: TextSelection.collapsed(offset: widget.value.length),
      );
    }
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
    controller: _text,
    enabled: widget.enabled,
    onChanged: widget.onChanged,
    maxLength: widget.maxLength,
    keyboardType: widget.numeric
        ? const TextInputType.numberWithOptions(decimal: true)
        : TextInputType.text,
    decoration: InputDecoration(
      label: widget.visibleLabel == null
          ? null
          : Text(widget.visibleLabel!, semanticsLabel: widget.label),
      labelText: widget.visibleLabel == null ? widget.label : null,
      counterText: '',
      errorText: widget.error,
      isDense: widget.compact,
      floatingLabelBehavior: widget.compact
          ? FloatingLabelBehavior.always
          : null,
      contentPadding: widget.compact
          ? const EdgeInsets.symmetric(horizontal: 10, vertical: 12)
          : null,
    ),
  );
}


/// Customer box with the company's customers as suggestions, like the web
/// datalist. Any typed name is accepted ("Walk-in customer" when empty).
class _PartyField extends StatefulWidget {
  const _PartyField({
    required this.value,
    required this.parties,
    required this.enabled,
    required this.onChanged,
  });

  final String value;
  final List<String> parties;
  final bool enabled;
  final ValueChanged<String> onChanged;

  @override
  State<_PartyField> createState() => _PartyFieldState();
}

class _PartyFieldState extends State<_PartyField> {
  late final _text = TextEditingController(text: widget.value);
  final _focus = FocusNode();

  @override
  void didUpdateWidget(covariant _PartyField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_text.text != widget.value) {
      _text.value = TextEditingValue(
        text: widget.value,
        selection: TextSelection.collapsed(offset: widget.value.length),
      );
    }
  }

  @override
  void dispose() {
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RawAutocomplete<String>(
    textEditingController: _text,
    focusNode: _focus,
    optionsBuilder: (value) {
      final query = value.text.trim().toLowerCase();
      if (query.isEmpty) return const Iterable<String>.empty();
      return widget.parties
          .where((name) => name.toLowerCase().contains(query))
          .take(6);
    },
    onSelected: widget.onChanged,
    fieldViewBuilder: (context, controller, focus, submit) => TextField(
      controller: controller,
      focusNode: focus,
      enabled: widget.enabled,
      onChanged: widget.onChanged,
      decoration: const InputDecoration(
        labelText: 'Customer',
        hintText: 'Walk-in customer',
      ),
    ),
    optionsViewBuilder: (context, onSelected, options) => Align(
      alignment: Alignment.topLeft,
      child: Material(
        elevation: 4,
        borderRadius: BorderRadius.circular(8),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 220, maxWidth: 420),
          child: ListView(
            padding: EdgeInsets.zero,
            shrinkWrap: true,
            children: [
              for (final option in options)
                ListTile(
                  dense: true,
                  title: Text(option),
                  onTap: () => onSelected(option),
                ),
            ],
          ),
        ),
      ),
    ),
  );
}
