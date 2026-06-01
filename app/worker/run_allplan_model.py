import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path


ALLPLAN_EXE = Path(r"C:\Program Files\Allplan\Allplan 2026\Prg\Allplan_2026.exe")
ALLPLAN_LOCAL = Path.home() / "Documents" / "Nemetschek" / "Allplan" / "2026" / "Usr" / "Local"
ALLPLAN_PROJECTS_DIR = Path(os.environ.get("ALLPLAN_PROJECTS_DIR", r"C:\Data\Allplan\Allplan 2026\Prj"))
ALLPLAN_PROCESS_NAMES = ("Allplan_2026.exe", "Allplan.exe")
ALLPLAN_CLOSE_TIMEOUT_SECONDS = 30
ALLPLAN_WRITEBACK_DELAY_SECONDS = 15
PROJECT_NAME = os.environ.get("ALLPLAN_PROJECT_NAME", "viktor-template")
PROJECT_DIR = ALLPLAN_PROJECTS_DIR / f"{PROJECT_NAME}.prj"


def log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def make_writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
    except (FileNotFoundError, PermissionError):
        pass


def remove_readonly_and_retry(function, path, exc_info) -> None:
    make_writable(path)
    function(path)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=remove_readonly_and_retry)


def run_windows_command(args: list[str], log_path: Path, timeout: int = 20) -> subprocess.CompletedProcess:
    log(log_path, f"Running command: {' '.join(args)}")
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if output:
        log(log_path, output)

    return result


def is_process_running(process_name: str, log_path: Path) -> bool:
    result = run_windows_command(
        ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
        log_path,
    )
    return result.returncode == 0 and process_name.lower() in result.stdout.lower()


def stop_existing_allplan_processes(log_path: Path) -> None:
    if os.name != "nt":
        log(log_path, "Skipping Allplan process cleanup outside Windows.")
        return

    log(log_path, "Closing existing Allplan processes before resetting the registered project.")

    for process_name in ALLPLAN_PROCESS_NAMES:
        if is_process_running(process_name, log_path):
            run_windows_command(["taskkill", "/IM", process_name, "/T"], log_path)

    deadline = time.time() + ALLPLAN_CLOSE_TIMEOUT_SECONDS
    while time.time() < deadline:
        running = [
            process_name
            for process_name in ALLPLAN_PROCESS_NAMES
            if is_process_running(process_name, log_path)
        ]
        if not running:
            log(log_path, "No existing Allplan process remains.")
            return
        time.sleep(1)

    for process_name in ALLPLAN_PROCESS_NAMES:
        if is_process_running(process_name, log_path):
            log(log_path, f"Force-closing stale Allplan process: {process_name}.")
            run_windows_command(["taskkill", "/F", "/IM", process_name, "/T"], log_path)


def install_template_project(template_zip: Path, project_dir: Path, log_path: Path) -> Path:
    extract_dir = template_zip.parent / "_template_project_extract"
    remove_tree(extract_dir)
    remove_tree(project_dir)

    extract_dir.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(template_zip), str(extract_dir), "zip")

    project_candidates = sorted(path for path in extract_dir.iterdir() if path.is_dir() and path.suffix == ".prj")
    if project_candidates:
        source_project_dir = project_candidates[0]
    elif (extract_dir / "Project1.Dat.xml").exists():
        source_project_dir = extract_dir
    else:
        raise RuntimeError(
            f"Template archive {template_zip} does not contain a .prj folder or Project1.Dat.xml."
        )

    shutil.copytree(source_project_dir, project_dir, copy_function=shutil.copy2)
    remove_tree(extract_dir)

    project_xml = project_dir / "Project1.Dat.xml"
    if not project_xml.exists():
        raise FileNotFoundError(f"Copied project is missing Project1.Dat.xml: {project_xml}")

    log(log_path, f"Installed template project at {project_dir}.")
    return project_xml


def write_worker_inputs(
    inputs_path: Path,
    inputs_target: Path,
    project_dir: Path,
    project_xml: Path,
) -> None:
    with inputs_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    data["_worker_context"] = {
        "expected_project_name": PROJECT_NAME,
        "expected_project_dir": str(project_dir),
        "expected_project_xml": str(project_xml),
        "expected_project_dir_name": project_dir.name,
    }

    inputs_target.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_artifact(output_log: Path, artifact_path: Path, title: str) -> None:
    if not artifact_path.exists():
        log(output_log, f"{title} was not written: {artifact_path}.")
        return

    with output_log.open("a", encoding="utf-8") as file:
        file.write(f"\n{title}:\n")
        file.write(artifact_path.read_text(encoding="utf-8"))
        file.write("\n")


def main() -> None:
    workdir = Path.cwd()
    template_zip = workdir / "template_project.zip"
    inputs_path = workdir / "inputs.json"
    pyp_source = workdir / "RebarWorker.pyp"
    py_source = workdir / "RebarWorker.py"
    output_zip = workdir / "result_project.zip"
    output_log = workdir / "worker_log.txt"

    if output_zip.exists():
        output_zip.unlink()

    if output_log.exists():
        output_log.unlink()

    log(output_log, "Worker started.")

    if not template_zip.exists():
        raise FileNotFoundError(f"Template project ZIP was not found: {template_zip}")

    stop_existing_allplan_processes(output_log)

    log(output_log, f"Installing template project from {template_zip}.")
    project_xml = install_template_project(template_zip, PROJECT_DIR, output_log)
    log(output_log, f"Template project ready at {project_xml}.")

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
    context_probe_source = python_scripts_dir / "context_probe.json"
    output_json = workdir / "result.json"

    for path in [done_marker, result_source, output_json, log_source, error_source, context_probe_source]:
        if path.exists():
            path.unlink()

    shutil.copy2(pyp_source, pyp_target)
    shutil.copy2(py_source, py_target)
    write_worker_inputs(inputs_path, inputs_target, PROJECT_DIR, project_xml)
    log(output_log, f"Copied PythonPart to {pyp_target}.")
    log(output_log, f"Copied script and inputs to {python_scripts_dir}.")

    process = None

    try:
        process = subprocess.Popen(
            [
                str(ALLPLAN_EXE),
                "/l",
                str(project_xml),
                "-o",
                f"@{pyp_target}",
            ],
            cwd=str(workdir),
        )
        log(output_log, f"Started Allplan with PID {process.pid} using project {project_xml}.")

        deadline = time.time() + 840
        while not done_marker.exists():
            if error_source.exists():
                error_text = error_source.read_text(encoding="utf-8")
                log(output_log, "worker_error.txt detected.")
                log(output_log, error_text)
                append_artifact(output_log, log_source, "PythonPart log")
                append_artifact(output_log, context_probe_source, "PythonPart context probe")
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
        time.sleep(ALLPLAN_WRITEBACK_DELAY_SECONDS)
        log(
            output_log,
            f"Waited {ALLPLAN_WRITEBACK_DELAY_SECONDS} seconds for Allplan to finish creating returned elements.",
        )
        shutil.copy2(result_source, output_json)
        log(output_log, "Copied result.json back to worker output folder.")

        append_artifact(output_log, log_source, "PythonPart log")
        append_artifact(output_log, context_probe_source, "PythonPart context probe")

        shutil.make_archive(
            base_name=str(output_zip.with_suffix("")),
            format="zip",
            root_dir=str(PROJECT_DIR.parent),
            base_dir=PROJECT_DIR.name,
        )
        log(output_log, f"Created {output_zip}.")
        log(output_log, f"Leaving launched Allplan process open for inspection. PID: {process.pid}.")
        process = None
    finally:
        if process is not None:
            log(output_log, f"Leaving launched Allplan process open after worker exit. PID: {process.pid}.")


if __name__ == "__main__":
    main()
