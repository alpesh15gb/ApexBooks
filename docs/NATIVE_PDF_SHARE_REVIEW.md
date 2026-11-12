# Native PDF and external-share review (2026-11-12)

Local follow-up to `41ef08e`; no production access, publication, messages or external application launches were performed during tests.

## Changes

- Android commits the requested PDF template together with successfully fetched bytes. While a format fetch is pending, file actions are disabled; failure leaves the previous format and bytes intact with a retry action. Request identity, workspace, page and current PDF identity suppress obsolete responses, including close and company/session changes. Initial load failure surfaces the normal error instead of silently disappearing.
- PDF preview open and page-render failures have terminal error panels and retry controls. An explicit Open in another PDF viewer action grants read access to a uniquely named cache file; it does not launch automatically. Actions recheck the current PDF immediately before file/intent operations. Filename sanitization follows the existing share path.
- Windows and Android WhatsApp preparation capture document, party phone and company before awaiting branding. A shared tested helper checks ownership before the read, after success/failure, and immediately before launch. A stale company/session suppresses the launch; Android additionally checks the detail identity. Cancellation is not swallowed into a fallback message.

## Executed evidence

- `native/tests/AndroidPdfLoading/check.py --kotlin-home /tmp/apex-kotlin/kotlinc`: compiled the actual AppModel request/close methods in a deterministic JVM transport seam. Seven scenarios passed: failed format/retry, close, company, page, session, out-of-order response, and visible initial failure. Preview open/page error and retry wiring is source asserted, not Android runtime tested. Log: `/tmp/apex-native-pdf-seam.log`.
- Android `ScopedExternalActionTest`: two compiled JUnit tests passed, covering five delayed success/failure/final-boundary scenarios plus coroutine cancellation. All launches were in-memory callbacks.
- The Windows portable test project passed, including five synthetic delayed-branding ownership scenarios and existing CSV, source selection, retry, transfer and company-load checks. Log: `/tmp/apex-native-share-windows.log`. This compiles the production helper, not the WinUI page.
- `git diff --check` passed.

## Remaining acceptance

Full exact-revision WinUI/Android builds and UI/device tests remain required. In particular, verify Compose retry interactions, actual PdfRenderer failures, chooser availability, file saving/sharing/printing and lifecycle changes on Android. The PDF page preview is an image with a page label; it does not expose document text to TalkBack. The external viewer option is a fallback, not an accessibility certification. No real WhatsApp communication was used to validate these changes.
