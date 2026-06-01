VIKTOR demo app for a wind turbine foundation native rebar workflow in Allplan.

The app generates a wind turbine foundation APN project from VIKTOR inputs:

- Parametrize a circular pile cap / raft with a raised circular pedestal.
- Configure a circular pile layout below the foundation.
- Configure concrete cover, radial foundation bars, circular base rings, pedestal grid bars, and pile cages.
- Review a clean grayscale 2D plan and section sketch in VIKTOR.
- Send the same parameters to an Allplan PythonPart worker.
- Download an Allplan APN project with the circular foundation, pedestal, piles, and reinforcement layout.

The foundation cap rebar is trimmed around pile footprints when it would clash with pile positions. This is a demo-oriented visual rule, not a reinforcement-code detailing engine.

The Allplan worker opens a template APN directly and returns the modified APN. The older project ZIP workflow is no longer used.

## Allplan project registration and check guide

### 1. Run from VIKTOR

In VIKTOR, run:

```text
Download Allplan project
```

The app sends the APN template project, the PythonPart, the Python script, and the input file to the Allplan worker.

### 2. Check what the worker creates

During the run, the worker copies `template_project.apn` to `result_project.apn`, opens that APN directly in Allplan, and returns the modified APN as the download.

It also creates/copies worker files here:

```text
%USERPROFILE%\Documents\Nemetschek\Allplan\2026\Usr\Local\PythonParts\ViktorWorker
```

and here:

```text
%USERPROFILE%\Documents\Nemetschek\Allplan\2026\Usr\Local\PythonPartsScripts\ViktorWorker
```

The runner script uses these Allplan 2026 paths directly.
