import 'package:material_ui/material_ui.dart';

/// Design tokens measured from the web app's computed styles, so Flutter screens
/// match it at the same sizes. Keep names aligned with what they are used for.
abstract final class Apex {
  // Surfaces
  static const paper = Color(0xfff3f6f4);
  static const card = Colors.white;
  static const line = Color(0xffdce5e0);
  static const lineStrong = Color(0xffdfe3e8);
  static const lineSoft = Color(0xffedf0f4);
  static const controlBorder = Color(0xff8a939f);
  static const fieldBorder = Color(0xffaeb7c2);
  static const tableHead = Color(0xfff0f2f5);
  static const tint = Color(0xfff6f9f7);
  static const filterBand = Color(0xfff7faf8);

  // Text
  static const ink = Color(0xff20262e);
  static const inkSoft = Color(0xff353d48);
  static const muted = Color(0xff606a77);
  static const label = Color(0xff414d5b);
  static const heading = Color(0xff20322a);
  static const crumb = Color(0xff7f7368);
  static const link = Color(0xff006aaf);

  // Brand
  static const green = Color(0xff007a3d);
  static const greenDark = Color(0xff075e34);
  static const greenText = Color(0xff08713e);
  static const mint = Color(0xffd3f0df);
  static const mintSoft = Color(0xffeef8f1);
  static const mintLine = Color(0xffc6dfcf);
  static const mintIcon = Color(0xffecf7ef);
  static const forest = Color(0xff173b2e);
  static const red = Color(0xffb3261e);
  static const amber = Color(0xffb7791f);

  // Sidebar
  static const sidebar = Color(0xff132a25);
  static const sidebarRaised = Color(0xff1d372f);
  static const sidebarBorder = Color(0xff365448);
  static const sidebarActive = Color(0xff315647);
  static const sidebarAccent = Color(0xff9bdfb7);
  static const sidebarText = Color(0xffe1eee9);
  static const sidebarLabel = Color(0xffa2beb2);
  static const sidebarFoot = Color(0xffd4dae2);
  static const sidebarCta = Color(0xffd3f0df);
  static const sidebarCtaText = Color(0xff193c2d);

  // Shape
  static const radiusCard = 13.0;
  static const radiusPanel = 12.0;
  static const radiusControl = 8.0;
  static const radiusChip = 7.0;

  static const body = 'DM Sans';
  static const display = 'DM Sans Display';

  static const pageTitle = TextStyle(
    fontFamily: display,
    fontSize: 38,
    fontWeight: FontWeight.w700,
    letterSpacing: -1.7,
    height: 1.13,
    color: ink,
  );
  static const registerTitle = TextStyle(
    fontFamily: display,
    fontSize: 26,
    fontWeight: FontWeight.w700,
    letterSpacing: -1,
    height: 1.2,
    color: Color(0xff223e4d),
  );
  static const sectionTitle = TextStyle(fontFamily: body, 
    fontSize: 19,
    fontWeight: FontWeight.w700,
    letterSpacing: -.38,
    color: heading,
  );
  static const panelTitle = TextStyle(fontFamily: body, 
    fontSize: 18,
    fontWeight: FontWeight.w600,
    letterSpacing: -.36,
    color: ink,
  );
  static const lead = TextStyle(fontFamily: body, fontSize: 14, height: 1.7, color: muted);
  static const note = TextStyle(fontFamily: body, fontSize: 12, height: 1.7, color: muted);
  static const small = TextStyle(fontFamily: body, fontSize: 11, color: muted);
  static const strong = TextStyle(fontFamily: body, 
    fontSize: 13,
    fontWeight: FontWeight.w600,
    color: ink,
  );
  static const button = TextStyle(fontFamily: body, 
    fontSize: 13,
    fontWeight: FontWeight.w600,
    letterSpacing: 0,
  );
  static const eyebrow = TextStyle(fontFamily: body, 
    fontSize: 10,
    fontWeight: FontWeight.w700,
    letterSpacing: .8,
    color: sidebarLabel,
  );
  static const tableHeader = TextStyle(fontFamily: body, 
    fontSize: 10,
    fontWeight: FontWeight.w700,
    letterSpacing: .6,
    color: label,
  );
  static const money = TextStyle(
    fontFamily: display,
    fontSize: 29,
    fontWeight: FontWeight.w600,
    letterSpacing: -1.16,
    height: 1.25,
    color: ink,
  );
}

ThemeData apexTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: Apex.forest,
    surface: Colors.white,
    primary: Apex.green,
    onPrimary: Colors.white,
    primaryContainer: Apex.mint,
    onPrimaryContainer: Apex.forest,
    secondaryContainer: Apex.mint,
    onSecondaryContainer: Apex.forest,
    outline: Apex.fieldBorder,
    outlineVariant: Apex.line,
    onSurface: Apex.ink,
    onSurfaceVariant: Apex.muted,
    error: Apex.red,
  );
  final inputBorder = OutlineInputBorder(
    borderSide: const BorderSide(color: Apex.lineStrong),
    borderRadius: BorderRadius.circular(Apex.radiusControl),
  );
  final buttonShape = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(Apex.radiusControl),
  );
  const buttonPadding = EdgeInsets.symmetric(horizontal: 19);
  return ThemeData(
    fontFamily: Apex.body,
    colorScheme: scheme,
    scaffoldBackgroundColor: Apex.paper,
    dividerColor: Apex.line,
    dividerTheme: const DividerThemeData(color: Apex.line, space: 1),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        fontFamily: Apex.display,
        fontWeight: FontWeight.w700,
        letterSpacing: -1,
        color: Apex.ink,
      ),
      headlineSmall: TextStyle(
        fontFamily: Apex.display,
        fontSize: 26,
        fontWeight: FontWeight.w700,
        letterSpacing: -1,
        color: Apex.ink,
      ),
      titleLarge: TextStyle(
        fontSize: 19,
        fontWeight: FontWeight.w700,
        letterSpacing: -.38,
        color: Apex.heading,
      ),
      titleMedium: TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w600,
        letterSpacing: -.1,
        color: Apex.ink,
      ),
      titleSmall: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: Apex.ink,
      ),
      bodyLarge: TextStyle(fontSize: 14, color: Apex.ink),
      bodyMedium: TextStyle(fontSize: 13, color: Apex.inkSoft),
      bodySmall: TextStyle(fontSize: 12, color: Apex.muted),
      labelLarge: TextStyle(fontFamily: Apex.body, fontWeight: FontWeight.w600, letterSpacing: 0),
      labelMedium: TextStyle(fontWeight: FontWeight.w600, color: Apex.label),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 66,
      elevation: 0,
      backgroundColor: Colors.white,
      indicatorColor: Apex.mint,
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          letterSpacing: 0,
          fontSize: 12,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w700
              : FontWeight.w500,
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      isDense: true,
      border: inputBorder,
      enabledBorder: inputBorder,
      focusedBorder: inputBorder.copyWith(
        borderSide: const BorderSide(color: Apex.green, width: 1.6),
      ),
      labelStyle: const TextStyle(fontFamily: Apex.body, fontSize: 13, color: Apex.muted),
      floatingLabelStyle: const TextStyle(
        fontFamily: Apex.body,
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: Apex.label,
      ),
      hintStyle: const TextStyle(fontFamily: Apex.body, fontSize: 13, color: Color(0xff8a929c)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 13, vertical: 13),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Apex.green,
        foregroundColor: Colors.white,
        disabledBackgroundColor: const Color(0xff9cc9b0),
        disabledForegroundColor: Colors.white,
        minimumSize: const Size(48, 40),
        padding: buttonPadding,
        textStyle: Apex.button,
        shape: buttonShape,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        backgroundColor: Colors.white,
        foregroundColor: Apex.inkSoft,
        minimumSize: const Size(48, 40),
        padding: buttonPadding,
        textStyle: Apex.button,
        side: const BorderSide(color: Apex.controlBorder),
        shape: buttonShape,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: Apex.link,
        textStyle: Apex.button,
        shape: buttonShape,
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: Colors.white,
      selectedColor: const Color(0xffe3f2e9),
      side: const BorderSide(color: Apex.lineStrong),
      labelStyle: const TextStyle(
        fontFamily: Apex.body,
        fontSize: 12,
        fontWeight: FontWeight.w700,
        color: Apex.inkSoft,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Apex.radiusChip),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      titleTextStyle: TextStyle(
        fontFamily: Apex.body,
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: Apex.ink,
      ),
      subtitleTextStyle: TextStyle(
        fontFamily: Apex.body,
        fontSize: 12,
        color: Apex.muted,
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
    ),
    tooltipTheme: const TooltipThemeData(waitDuration: Duration(milliseconds: 400)),
  );
}
