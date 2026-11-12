"""Run Android JVM transport acceptance against an owned disposable loopback API.

No hosted API, reused database, emulator, or device permissions are involved.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def run():
    if any(os.environ.get(key) for key in ("APEX_SYNTHETIC_API_ORIGIN", "APEX_E2E_BASE", "ACCEPTANCE_BASE")):
        raise RuntimeError("External/reused API targets are refused; this runner owns its API.")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="apex-android-http-") as directory:
        work = Path(directory)
        removed = {"DATABASE_URL", "JWT_SECRET", "OPENAI_API_KEY", "OMNIROUTE_API_KEY",
                   "OMNIROUTE", "OCR_BASE_URL", "OCR_ALLOW_INSECURE_HTTP", "COMMERCE_ENCRYPTION_KEY",
                   "COMMERCE_ALLOWED_HOSTS", "CRON_SECRET", "APEX_TEST_DATABASE_URL"}
        env = {k: v for k, v in os.environ.items() if k.upper() not in removed}
        env.update(DATABASE_URL="sqlite:///" + (work / "isolated.db").as_posix(),
                   JWT_SECRET="synthetic-android-http-only-not-production",
                   APEX_SYNTHETIC_API_ORIGIN=origin, NO_PROXY="127.0.0.1,localhost,::1")
        subprocess.run([sys.executable, "migrate.py"], cwd=ROOT / "backend", env=env, check=True, timeout=120)
        with (work / "api.log").open("w") as log:
            api = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                                   cwd=ROOT / "backend", env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                opener = build_opener(ProxyHandler({}))
                for _ in range(60):
                    if api.poll() is not None:
                        raise RuntimeError("Owned synthetic API stopped before readiness.")
                    try:
                        with opener.open(origin + "/api/ready", timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError("Owned synthetic API did not become ready.")
                report = ROOT / "native/android/app/build/test-results/testDebugUnitTest/TEST-com.apexbooks.accounting.CompleteBackupHttpTest.xml"
                report.unlink(missing_ok=True)
                subprocess.run(["bash", "gradlew", ":app:testDebugUnitTest", "--tests",
                                "com.apexbooks.accounting.CompleteBackupHttpTest", "--rerun-tasks",
                                "--no-daemon", "--max-workers=2"],
                               cwd=ROOT / "native/android", env=env, check=True, timeout=1200)
                result = ET.parse(report).getroot()
                if int(result.get("tests", "0")) < 1 or any(int(result.get(key, "0")) for key in ("skipped", "failures", "errors")):
                    raise RuntimeError("Android HTTP acceptance did not execute successfully; skipped results are not evidence.")
                print("Android JVM HTTP acceptance passed against owned temporary books.", flush=True)
            except BaseException:
                log.flush()
                print("\n".join((work / "api.log").read_text(errors="replace").splitlines()[-35:]), flush=True)
                raise
            finally:
                if api.poll() is None:
                    api.terminate()
                try:
                    api.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    api.kill()
                    api.wait(timeout=15)


if __name__ == "__main__":
    run()
