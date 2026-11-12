# Android return-source selection seam

Run `python native/tests/AndroidSourceSelection/check.py --kotlin-home /path/to/kotlinc` with Java and the Kotlin distribution available locally. It downloads nothing.

The script extracts and compiles the actual `EntryEditor.chooseSource`, confirmation and load methods, with a controlled model/transport/JSON seam and Kotlin coroutines. It also compiles the production remaining-quantity helper. Assertions exercise delayed failure/retry, dirty confirmation/Keep editing, stale company/editor/draft responses, malformed staged lines and single-flight loading. Save & new Review placement, fresh-editor reset and retry-submission wiring receive source assertions only.

This is not a full Android build or Compose/device test. Real Review-step clicking, focus, rotation, process recreation, save/reset and uncertain-response retry acceptance remain required. No real credentials, server or accounting database are used.
