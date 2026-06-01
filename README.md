VIKTOR demo app for a wind turbine foundation native rebar workflow in Allplan.

The app generates a wind turbine foundation Allplan project from VIKTOR inputs:

- Parametrize a circular pile cap / raft with a raised circular pedestal.
- Configure a circular pile layout below the foundation.
- Configure concrete cover, radial foundation bars, circular base rings, pedestal grid bars, and pile cages.
- Review a clean grayscale 2D plan and section sketch in VIKTOR.
- Send the same parameters to an Allplan PythonPart worker.
- Download an Allplan project ZIP with the circular foundation, pedestal, piles, and reinforcement layout.

The foundation cap rebar is trimmed around pile footprints when it would clash with pile positions. This is a demo-oriented visual rule, not a reinforcement-code detailing engine.

The Allplan worker uses a clean project ZIP template for each run. It resets the registered Allplan project `viktor-template` under `C:\Data\Allplan\Allplan 2026\Prj\viktor-template.prj`, opens it with Allplan's `/l ...\Project1.Dat.xml` startup argument, runs the PythonPart with `-o`, and returns the modified project as `result_project.zip`. The project root and name can be overridden with `ALLPLAN_PROJECTS_DIR` and `ALLPLAN_PROJECT_NAME` on the worker machine.

## First-time Allplan setup

Before running the VIKTOR worker on a new Windows machine, create or import a registered Allplan project named `viktor-template`.

The default expected project folder is:

```text
C:\Data\Allplan\Allplan 2026\Prj\viktor-template.prj
```

The worker expects this file to exist:

```text
C:\Data\Allplan\Allplan 2026\Prj\viktor-template.prj\Project1.Dat.xml
```

In Allplan Project Management, confirm that `viktor-template` appears under `Local`. This project is used as a disposable worker target: the worker closes existing Allplan sessions, resets the project folder from `viktor-template.prj.zip`, runs the PythonPart, and returns the modified project ZIP. Do not use `viktor-template` for manual production work.

If the worker machine uses a different project root or project name, set these environment variables before starting the VIKTOR worker:

```powershell
$env:ALLPLAN_PROJECTS_DIR = "C:\Data\Allplan\Allplan 2026\Prj"
$env:ALLPLAN_PROJECT_NAME = "viktor-template"
```

During the run, the worker also creates/copies worker files under `%USERPROFILE%\Documents\Nemetschek\Allplan\2026\Usr\Local\PythonParts\ViktorWorker` and `%USERPROFILE%\Documents\Nemetschek\Allplan\2026\Usr\Local\PythonPartsScripts\ViktorWorker`.
