import shutil
import subprocess
import time
from pathlib import Path


ALLPLAN_EXE = Path(r"C:\Program Files\Allplan\Allplan 2026\Prg\Allplan_2026.exe")
ALLPLAN_LOCAL = Path.home() / "Documents" / "Nemetschek" / "Allplan" / "2026" / "Usr" / "Local"
ALLPLAN_PROJECTS_DIR = Path(r"C:\Data\Allplan\Allplan 2026\Prj")
PROJECT_NAME = "viktor-template"
PROJECT_DIR = ALLPLAN_PROJECTS_DIR / f"{PROJECT_NAME}.prj"
STAGING_PROJECT_DIR = ALLPLAN_PROJECTS_DIR / f"{PROJECT_NAME}.prj.incoming"


def log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def ensure_allplan_is_closed(log_path: Path) -> None:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {ALLPLAN_EXE.name}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return
    except Exception as error:
        log(log_path, f"Could not check whether Allplan is running: {error}")
        return

    if ALLPLAN_EXE.name.lower() in result.stdout.lower():
        message = (
            f"{ALLPLAN_EXE.name} is already running. Close Allplan before starting "
            "the VIKTOR worker so the template project can be replaced cleanly."
        )
        log(log_path, message)
        raise RuntimeError(message)


def install_template_project(template_zip: Path, log_path: Path) -> None:
    extract_dir = template_zip.parent / "_template_project_extract"

    if not template_zip.is_file():
        raise FileNotFoundError(f"Missing template project zip: {template_zip}")

    try:
        for temp_dir in [extract_dir, STAGING_PROJECT_DIR]:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        extract_dir.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(str(template_zip), str(extract_dir), "zip")

        project_folder_inside_zip = extract_dir / f"{PROJECT_NAME}.prj"
        project_source = project_folder_inside_zip if project_folder_inside_zip.exists() else extract_dir

        if not project_source.is_dir() or not any(project_source.iterdir()):
            raise RuntimeError(f"Template project zip did not contain a usable project folder: {template_zip}")

        ALLPLAN_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(project_source, STAGING_PROJECT_DIR)
        log(log_path, f"Prepared fresh project copy at {STAGING_PROJECT_DIR}.")

        if PROJECT_DIR.exists():
            try:
                shutil.rmtree(PROJECT_DIR)
                log(log_path, f"Removed existing project at {PROJECT_DIR}.")
            except Exception as error:
                message = (
                    f"Could not remove existing project at {PROJECT_DIR}. "
                    "Close Allplan and retry so the VIKTOR template can replace it cleanly."
                )
                log(log_path, f"{message} Original error: {error}")
                raise RuntimeError(message) from error

        shutil.move(str(STAGING_PROJECT_DIR), str(PROJECT_DIR))
        log(log_path, f"Installed fresh template project at {PROJECT_DIR}.")
    finally:
        for temp_dir in [extract_dir, STAGING_PROJECT_DIR]:
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as error:
                    log(log_path, f"Could not remove temporary folder {temp_dir}: {error}")


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
    ensure_allplan_is_closed(output_log)
    log(output_log, f"Installing template project from {template_zip}.")
    install_template_project(template_zip, output_log)
    log(output_log, f"Template project ready at {PROJECT_DIR}.")

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
            "-o",
            f"@{pyp_target}",
        ],
        cwd=str(workdir),
    )
    log(output_log, f"Started Allplan with PID {process.pid}.")

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
            process.terminate()
            raise TimeoutError("Allplan worker did not finish within 840 seconds.")

        time.sleep(1)

    log(output_log, "worker_done.txt detected.")
    log(output_log, f"Allplan process state after marker: {process.poll()}.")
    time.sleep(5)
    log(output_log, "Waited 5 seconds for Allplan to finish creating returned reinforcement elements.")
    shutil.copy2(result_source, output_json)
    log(output_log, "Copied result.json back to worker output folder.")

    with output_log.open("a", encoding="utf-8") as file:
        file.write("\nPythonPart log:\n")
        file.write(log_source.read_text(encoding="utf-8"))

    shutil.make_archive(
        base_name=str(output_zip.with_suffix("")),
        format="zip",
        root_dir=str(PROJECT_DIR),
    )
    log(output_log, f"Created {output_zip}.")


if __name__ == "__main__":
    main()
