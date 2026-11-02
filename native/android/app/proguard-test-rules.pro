# Error Prone's compile-time IncompatibleModifiers annotation refers to a JDK
# compiler enum that Android intentionally does not provide. It is not used by
# the runner or app at runtime. Keep this exception confined to the test APK.
-dontwarn javax.lang.model.element.Modifier
