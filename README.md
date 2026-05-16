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
