# Instrumentation adds external callers absent from the shipping app's call graph.
# Retain their service ABI and shared libraries in the signed test host only.
-keep class com.apexbooks.accounting.data.ApexApi { public *; }
-keep class com.apexbooks.accounting.data.ApexApiKt { public *; }
-keep class com.apexbooks.accounting.data.ApiFailure { public *; }
-keep class com.apexbooks.accounting.data.SessionVault { public *; }
-keep class com.apexbooks.accounting.NativeFiles { public *; }
-keep class androidx.tracing.** { *; }
-keep class kotlin.** { *; }
-keep class kotlinx.coroutines.BuildersKt** { public *; }
