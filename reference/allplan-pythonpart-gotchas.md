# Allplan PythonPart Gotchas

Internal notes from the PythonPart crashes in this repo.

## Standard PythonPart Return

In `create_element(build_ele, doc)`, return model elements through `CreateElementResult`.

```python
return CreateElementResult(
    elements=model_ele_list,
    placement_point=AllplanGeo.Point3D(),
)
```

Do not create elements manually inside `create_element()`.

```python
# Avoid this in a standard PythonPart.
AllplanBaseElements.CreateElements(doc, AllplanGeo.Matrix3D(), model_ele_list, [], None)
return CreateElementResult()
```

## Preview Failure

Failure shape:

```text
PythonPartPreview.execute(...)
AllplanBaseEle.DrawElementPreview(...)
ValueError: Incorrect parameters
```

Likely checks:

- Use `CreateElementResult(elements=...)`, not positional args.
- Set `placement_point=AllplanGeo.Point3D()` for absolute-origin geometry.
- Ensure `model_ele_list` contains individual Allplan elements only.

## Final Placement Failure

Failure shape:

```text
PythonPartTransaction.__create_elements(...)
AllplanBaseEle.CreateElements(...)
RuntimeError: unidentifiable C++ exception
```

Likely checks:

- No `None` in `model_ele_list`.
- No nested Python lists in `model_ele_list`.
- No zero-length cylinders or bars.
- No invalid BRep geometry.
- For `AxisPlacement3D`, keep reference vector perpendicular to the cylinder axis.

## Cylinder Axis Rule

For arbitrary cylinder segments, build an orthogonal basis.

```python
axis = unit(end - start)
reference = perpendicular_reference_vector(axis)
placement = AllplanGeo.AxisPlacement3D(start_point, reference, axis)
```

Do not reuse a fixed reference vector for sloped bars unless it is perpendicular to the axis.

## Logging Payloads

Before returning:

```python
for index, element in enumerate(model_ele_list):
    if element is None:
        raise RuntimeError(f"Invalid model element at index {index}: None")
    if isinstance(element, list):
        raise RuntimeError(f"Invalid model element at index {index}: nested Python list")
```

Also log element count and element type counts.

## Ignore This Noise

```text
APM #8013 ... PBT_POWERSETTINGCHANGE
```

This is a Windows power-setting notification, not the PythonPart crash.

## References

- [Allplan Standard PythonPart](https://pythonparts.allplan.com/2026/manual/key_components/script/standard_pythonpart/)
- [Allplan CreateElementResult](https://pythonparts.allplan.com/2024/api_reference/GeneralScripts/CreateElementResult/CreateElementResult/)
- [Allplan elements](https://pythonparts.allplan.com/2026/manual/features/allplan_elements/)
- [Allplan preview](https://pythonparts.allplan.com/2026/manual/features/preview/)
- [Microsoft: PBT_POWERSETTINGCHANGE](https://learn.microsoft.com/en-us/windows/win32/power/pbt-powersettingchange)
- [Boost.Python runtime errors](https://wiki.python.org/moin/boost.python/RuntimeErrors)
