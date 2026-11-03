# Restored-company navigation lifetime

Run after the pinned Gradle wrapper has populated its distribution:

```bash
python3 native/tests/AndroidLifecycle/check.py
```

Or select an existing distribution with `--gradle-home /path/to/gradle-8.14.3`.
The script downloads nothing and uses the Kotlin compiler/coroutines shipped with
that distribution. It works on Windows and Unix using Java argument files and
the platform classpath separator, including long cache paths and paths with
spaces. It compiles the actual `AppModel.chooseCompany` and `task`
method bodies in a controlled model seam, not an Android Application or Compose
runtime. The fake transport suspends until the caller's dialog scope is cancelled.

Assertions reproduce the old selected-but-unloaded state with dialog-owned work,
prove ViewModel-owned work completes both record/bank loads after that cancellation,
and require the production Open restored company action to use the ViewModel task.
Existing generation guards are not replaced. Actual instrumentation must still
prove the newly restored company reaches its loaded register through the real UI.

The test does not access a network, user account, database, SDK device or credentials.
