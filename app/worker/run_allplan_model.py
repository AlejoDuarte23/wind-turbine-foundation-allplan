import shutil
import subprocess
import time
from pathlib import Path


ALLPLAN_EXE = Path(r"C:\Program Files\Allplan\Allplan 2026\Prg\Allplan_2026.exe")
ALLPLAN_LOCAL = Path.home() / "Documents" / "Nemetschek" / "Allplan" / "2026" / "Usr" / "Local"
ALLPLAN_CLOSE_TIMEOUT_SECONDS = 30


def log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def stop_launched_allplan(process: subprocess.Popen, log_path: Path) -> None:
    if process.poll() is not None:
        log(log_path, f"Allplan process already exited with code {process.returncode}.")
        return

    log(log_path, f"Stopping launched Allplan process with PID {process.pid}.")
    process.terminate()

    try:
        process.wait(timeout=ALLPLAN_CLOSE_TIMEOUT_SECONDS)
        log(log_path, f"Allplan process exited with code {process.returncode}.")
    except subprocess.TimeoutExpired:
        log(log_path, "Allplan did not exit after terminate; killing process.")
        process.kill()
        process.wait(timeout=10)
        log(log_path, f"Allplan process killed with code {process.returncode}.")


def main() -> None:
    workdir = Path.cwd()
    template_apn = workdir / "template_project.apn"
    inputs_path = workdir / "inputs.json"
    pyp_source = workdir / "RebarWorker.pyp"
    py_source = workdir / "RebarWorker.py"
    output_apn = workdir / "result_project.apn"
    output_log = workdir / "worker_log.txt"

    if output_apn.exists():
        output_apn.unlink()

    if output_log.exists():
        output_log.unlink()

    log(output_log, "Worker started.")

    if not template_apn.exists():
        raise FileNotFoundError(f"Template APN file was not found: {template_apn}")

    shutil.copy2(template_apn, output_apn)
    log(output_log, f"Copied APN template from {template_apn} to {output_apn}.")

    python_parts_dir = ALLPLAN_LOCAL / "PythonParts" / "ViktorWorker"
    python_scripts_dir = ALLPLAN_LOCAL / "PythonPartsScripts" / "ViktorWorker"
    python_parts_dir.mkdir(parents=True, exist_ok=True)
    python_scripts_dir.mkdir(parents=True, exist_ok=True)

    pyp_target = python_parts_dir / "RebarWorker.pyp"
    py_target = python_scripts_dir / "RebarWorker.py"
    inputs_target = python_scripts_dir / "inputs.json"
    done_marker = python_scripts_dir / "worker_done.txt"
    result_source = python_scripts_dir / "result.json"
    log_source = python_scripts_dir / "worker_log.txt"
    error_source = python_scripts_dir / "worker_error.txt"
    output_json = workdir / "result.json"

    for path in [done_marker, result_source, output_json, log_source, error_source]:
        if path.exists():
            path.unlink()

    shutil.copy2(pyp_source, pyp_target)
    shutil.copy2(py_source, py_target)
    shutil.copy2(inputs_path, inputs_target)
    log(output_log, f"Copied PythonPart to {pyp_target}.")
    log(output_log, f"Copied script and inputs to {python_scripts_dir}.")

    process = subprocess.Popen(
        [
            str(ALLPLAN_EXE),
            str(output_apn),
            "-o",
            f"@{pyp_target}",
        ],
        cwd=str(workdir),
    )
    log(output_log, f"Started Allplan with PID {process.pid} opening {output_apn}.")

    try:
        deadline = time.time() + 840
        while not done_marker.exists():
            if error_source.exists():
                error_text = error_source.read_text(encoding="utf-8")
                log(output_log, "worker_error.txt detected.")
                log(output_log, error_text)
                raise RuntimeError(f"Allplan worker failed:\n{error_text}")

            if process.poll() is not None:
                log(output_log, f"Allplan process ended before marker. Exit code: {process.returncode}.")
                time.sleep(5)
                if not done_marker.exists():
                    raise RuntimeError(f"Allplan closed before the worker finished. Exit code: {process.returncode}")
                break

            if time.time() > deadline:
                log(output_log, "Timeout waiting for worker_done.txt.")
                raise TimeoutError("Allplan worker did not finish within 840 seconds.")

            time.sleep(1)

        log(output_log, "worker_done.txt detected.")
        log(output_log, f"Allplan process state after marker: {process.poll()}.")
        time.sleep(5)
        log(output_log, "Waited 5 seconds for Allplan to finish creating returned reinforcement elements.")
        shutil.copy2(result_source, output_json)
        log(output_log, "Copied result.json back to worker output folder.")

        if log_source.exists():
            with output_log.open("a", encoding="utf-8") as file:
                file.write("\nPythonPart log:\n")
                file.write(log_source.read_text(encoding="utf-8"))

        log(output_log, f"Output APN ready at {output_apn}.")
        log(output_log, "Leaving Allplan open for inspection.")
    except Exception as error:
        log(output_log, f"Worker failed with error: {error}")
        stop_launched_allplan(process, output_log)
        raise


if __name__ == "__main__":
    main()
