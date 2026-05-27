VIKTOR demo app for a wind turbine foundation visual rebar workflow in Allplan.

The app keeps the reinforcement as regular 3D visual geometry so the workflow stays stable and easy to inspect:

- Parametrize a circular pile cap / raft with a raised circular pedestal.
- Configure a circular pile layout below the foundation.
- Configure concrete cover, radial foundation bars, circular base rings, pedestal grid bars, and pile cage visuals.
- Review a clean grayscale 2D plan and section sketch in VIKTOR.
- Send the same parameters to an Allplan PythonPart worker.
- Download an Allplan project with the circular foundation, pedestal, piles, and visible visual rebar layout.

The foundation cap rebar is trimmed around pile footprints when it would clash with pile positions. This is a demo-oriented visual rule, not a reinforcement-code detailing engine.

The current version uses regular 3D geometry to show the rebar in Allplan. Creating native Allplan reinforcement entities is still work in progress.

## Allplan project registration and check guide

### 1. Download the empty project

Download the provided empty Allplan project ZIP.

This ZIP is the clean starting template for the worker.

### 2. Register the project in Allplan

Open Allplan and import the empty project ZIP:

```text
Project and Resource Management
-> Import Project
-> Select the empty project ZIP
-> Import
```

After importing, confirm that the project name is exactly:

```text
viktor-template
```

The worker opens the Allplan project by this exact name.

### 3. Check the local project folder

After import, confirm that this folder exists:

```text
C:\Data\Allplan\Allplan 2026\Prj\viktor-template.prj
```

This is the local Allplan project folder.

It should be the empty/clean template project before running the worker. It is not a single empty file; it is an Allplan project folder with internal Allplan files.

### 4. Close Allplan before running

Close Allplan completely before starting the VIKTOR worker.

This avoids locked project files and makes sure the worker can replace the clean template correctly.

### 5. Run from VIKTOR

In VIKTOR, run:

```text
Download Allplan project
```

The app sends the template project ZIP, the PythonPart, the Python script, and the input file to the Allplan worker.

### 6. Check what the worker creates

During the run, the worker uses this local project folder:

```text
C:\Data\Allplan\Allplan 2026\Prj\viktor-template.prj
```

It also creates/copies worker files here:

```text
%USERPROFILE%\Documents\Nemetschek\Allplan\2026\Usr\Local\PythonParts\ViktorWorker
```

and here:

```text
%USERPROFILE%\Documents\Nemetschek\Allplan\2026\Usr\Local\PythonPartsScripts\ViktorWorker
```

The runner script uses these Allplan 2026 paths directly.
