import json
import math
import os
import sys
import traceback
from pathlib import Path

try:
    import NemAll_Python_AllplanSettings as AllplanSettings
except ImportError:
    AllplanSettings = None

try:
    import NemAll_Python_IFW_ElementAdapter as AllplanIFWAdapter
except ImportError:
    AllplanIFWAdapter = None

import NemAll_Python_BaseElements as AllplanBaseElements
import NemAll_Python_Geometry as AllplanGeo
import NemAll_Python_Reinforcement as AllplanReinf
import NemAll_Python_Utility as AllplanUtil
import StdReinfShapeBuilder.GeneralReinfShapeBuilder as GeneralShapeBuilder
from CreateElementResult import CreateElementResult
from StdReinfShapeBuilder.ConcreteCoverProperties import ConcreteCoverProperties
from StdReinfShapeBuilder.ReinforcementShapeProperties import ReinforcementShapeProperties
from TypeCollections.Curve3DList import Curve3DList
from TypeCollections.ModelEleList import ModelEleList

try:
    from Utils.RotationUtil import RotationUtil
except ImportError:
    from Utils import RotationUtil as RotationUtilModule

    RotationUtil = getattr(RotationUtilModule, "RotationUtil", RotationUtilModule)


DRAWING_FILE_NUMBER = 1


def _clean_project_name(value: str) -> str:
    return str(value or "").strip()


def _worker_file(file_name: str) -> Path:
    return Path(__file__).with_name(file_name)


def _log(message: str) -> None:
    log_path = _worker_file("worker_log.txt")
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{message}\n")


def _write_error(error: BaseException) -> None:
    error_path = _worker_file("worker_error.txt")
    error_path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )


def check_allplan_version(build_ele, version: float) -> bool:
    return True


def _load_inputs() -> dict:
    with _worker_file("inputs.json").open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_path(value: str) -> str:
    if not value:
        return ""
    return os.path.normcase(os.path.normpath(str(value).strip().strip('"')))


def _get_current_project_path(context: dict) -> str:
    if AllplanSettings is None:
        context["current_project_path_error"] = "NemAll_Python_AllplanSettings is not available."
        return ""

    try:
        return str(AllplanSettings.AllplanPaths.GetCurPrjPath())
    except BaseException as error:
        context["current_project_path_error"] = repr(error)
        return ""


def _get_allplan_path(context: dict, output_key: str, method_name: str) -> str:
    if AllplanSettings is None:
        context[f"{output_key}_error"] = "NemAll_Python_AllplanSettings is not available."
        return ""

    try:
        return str(getattr(AllplanSettings.AllplanPaths, method_name)())
    except BaseException as error:
        context[f"{output_key}_error"] = repr(error)
        return ""


def _get_active_drawing_file_number(context: dict) -> int | None:
    try:
        return AllplanBaseElements.DrawingFileService.GetActiveFileNumber()
    except BaseException as error:
        context["active_drawing_file_static_error"] = repr(error)

    try:
        drawing_service = AllplanBaseElements.DrawingFileService()
        return drawing_service.GetActiveFileNumber()
    except BaseException as error:
        context["active_drawing_file_instance_error"] = repr(error)
        return None


def _get_drawing_file_name(context: dict, drawing_file_number: int | None) -> tuple[bool, str]:
    if drawing_file_number is None:
        return False, ""

    try:
        ok, name = AllplanBaseElements.DrawingFileService.GetDrawingFileName(drawing_file_number)
        return bool(ok), str(name)
    except BaseException as error:
        context["drawing_file_name_static_error"] = repr(error)

    try:
        drawing_service = AllplanBaseElements.DrawingFileService()
        ok, name = drawing_service.GetDrawingFileName(drawing_file_number)
        return bool(ok), str(name)
    except BaseException as error:
        context["drawing_file_name_instance_error"] = repr(error)
        return False, ""


def _get_active_document_name(context: dict) -> str:
    if AllplanIFWAdapter is None:
        context["active_document_name_error"] = "NemAll_Python_IFW_ElementAdapter is not available."
        return ""

    try:
        return str(AllplanIFWAdapter.DocumentNameService.GetActiveDocumentName())
    except BaseException as error:
        context["active_document_name_error"] = repr(error)
        return ""


def _collect_project_context(data: dict, stage: str) -> dict:
    worker_context = data.get("_worker_context", {})
    context = {
        "stage": stage,
        "argv": sys.argv,
        "allplan_settings_available": AllplanSettings is not None,
        "expected_project_name": worker_context.get("expected_project_name", ""),
        "expected_project_dir": worker_context.get("expected_project_dir", ""),
        "expected_project_xml": worker_context.get("expected_project_xml", ""),
        "expected_project_dir_name": worker_context.get("expected_project_dir_name", ""),
    }

    try:
        current_project_name, host_name = AllplanBaseElements.ProjectService.GetCurrentProjectNameAndHost()
        context["current_project_name"] = current_project_name
        context["host_name"] = host_name
    except BaseException as error:
        context["current_project_error"] = repr(error)
        context["current_project_name"] = ""
        context["host_name"] = ""

    context["current_project_path"] = _get_current_project_path(context)
    context["tmp_path"] = _get_allplan_path(context, "tmp_path", "GetTmpPath")
    context["usr_path"] = _get_allplan_path(context, "usr_path", "GetUsrPath")

    active_drawing_file_number = _get_active_drawing_file_number(context)
    context["active_drawing_file_number"] = active_drawing_file_number
    ok_drawing_file_name, drawing_file_name = _get_drawing_file_name(context, active_drawing_file_number)
    context["active_drawing_file_name_ok"] = ok_drawing_file_name
    context["active_drawing_file_name"] = drawing_file_name
    context["active_document_name"] = _get_active_document_name(context)

    _worker_file("context_probe.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _log(
        "Context probe "
        f"{stage}: project='{context.get('current_project_name', '')}', "
        f"path='{context.get('current_project_path', '')}'."
    )
    return context


def _project_context_matches(context: dict) -> bool:
    expected_name = _clean_project_name(context.get("expected_project_name", ""))
    current_project_name = _clean_project_name(context.get("current_project_name", ""))
    if expected_name and current_project_name == expected_name:
        return True

    expected_dir = _normalize_path(context.get("expected_project_dir", ""))
    expected_xml = _normalize_path(context.get("expected_project_xml", ""))
    current_path = _normalize_path(context.get("current_project_path", ""))

    if not expected_dir or not current_path:
        return False

    return (
        current_path == expected_dir
        or current_path == expected_xml
        or current_path.startswith(expected_dir + os.sep)
    )


def _open_expected_project(doc, data: dict, context: dict) -> dict:
    expected_name = _clean_project_name(context.get("expected_project_name", ""))
    if not expected_name:
        return context

    current_name = _clean_project_name(context.get("current_project_name", ""))
    if current_name == expected_name:
        return context

    host_name = _clean_project_name(context.get("host_name", "")) or "localhost"
    _log(f"Opening registered Allplan project '{expected_name}' on host '{host_name}'.")

    open_result = AllplanBaseElements.ProjectService.OpenProject(
        doc,
        host_name,
        expected_name,
    )

    _log(f"OpenProject returned: {open_result}")
    return _collect_project_context(data, "after_open_project")


def _assert_expected_project_context(context: dict) -> None:
    expected_dir = context.get("expected_project_dir", "")
    expected_name = _clean_project_name(context.get("expected_project_name", ""))
    if not expected_dir and not expected_name:
        _log("No expected project was provided; skipping project context validation.")
        return

    if _project_context_matches(context):
        _log(
            "Validated active Allplan project: "
            f"name='{_clean_project_name(context.get('current_project_name', ''))}', "
            f"path='{context.get('current_project_path', '')}'."
        )
        return

    raise RuntimeError(
        "Allplan is running the PythonPart in the wrong project. "
        f"Expected project '{expected_name}' at path '{expected_dir}', "
        f"but Allplan reported project '{_clean_project_name(context.get('current_project_name', ''))}' "
        f"at path '{context.get('current_project_path', '')}'. "
        "Make sure the registered project exists in Allplan project management and is not locked."
    )


def _public_inputs(data: dict) -> dict:
    return {key: value for key, value in data.items() if not key.startswith("_")}


def _load_drawing_file(doc) -> None:
    drawing_service = AllplanBaseElements.DrawingFileService()

    drawing_service.LoadFile(
        doc,
        DRAWING_FILE_NUMBER,
        AllplanBaseElements.DrawingFileLoadState.ActiveForeground,
    )


def create_element(build_ele, doc) -> CreateElementResult:
    try:
        _log("Wind turbine foundation PythonPart started.")
        data = _load_inputs()
        run_id = data["run_id"]

        done_marker = _worker_file("worker_done.txt")
        result_path = _worker_file("result.json")

        _log(f"Run ID: {run_id}.")
        context = _collect_project_context(data, "before_open_project")
        if not _project_context_matches(context):
            context = _open_expected_project(doc, data, context)
        _assert_expected_project_context(context)

        _log(f"Loading drawing file {DRAWING_FILE_NUMBER}.")
        _load_drawing_file(doc)
        context = _collect_project_context(data, "after_load_drawing_file")
        _assert_expected_project_context(context)

        _log("Drawing file loaded.")
        _log("Creating circular foundation, piles, and visual rebar geometry.")
        model_elements = create_model_elements(data)

        _log_model_elements(model_elements)

        result = build_result(data, run_id, _clean_project_name(context.get("current_project_name", "")))
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        _log("result.json written.")

        done_marker.write_text("done", encoding="utf-8")
        _log("worker_done.txt written.")
        _log("Returning model elements through CreateElementResult with fixed origin placement.")

        return CreateElementResult(
            elements=model_elements,
            placement_point=AllplanGeo.Point3D(),
        )

    except BaseException as error:
        _log(f"Worker failed: {error}")
        _write_error(error)
        raise


def create_model_elements(data: dict) -> ModelEleList:
    elements = ModelEleList()
    add_concrete_context(elements, data)
    add_foundation_rebar_visual(elements, data)
    add_pedestal_rebar_visual(elements, data)
    add_pile_rebar_visual(elements, data)
    return elements


def _log_model_elements(model_elements: ModelEleList) -> None:
    try:
        _log(f"Prepared {len(model_elements)} model elements.")
    except Exception as error:
        _log(f"Could not read model element count: {error}")

    try:
        type_counts = {}
        for index, element in enumerate(model_elements):
            if element is None:
                raise RuntimeError(f"Invalid model element at index {index}: None")
            if isinstance(element, list):
                raise RuntimeError(f"Invalid model element at index {index}: nested Python list")

            element_type = type(element).__name__
            type_counts[element_type] = type_counts.get(element_type, 0) + 1

        _log(f"Model element types: {type_counts}")
    except TypeError as error:
        _log(f"Could not iterate model elements for type validation: {error}")


def add_concrete_context(elements: ModelEleList, data: dict) -> None:
    foundation_radius = data["foundation_diameter"] / 2.0
    pedestal_radius = data["pedestal_diameter"] / 2.0
    edge_h = data["foundation_edge_thickness"]
    center_h = data["foundation_center_thickness"]

    append_vertical_cylinder(elements, foundation_radius, 0.0, edge_h)

    slope_height = max(0.0, center_h - edge_h)
    if slope_height > 0.0 and foundation_radius > pedestal_radius:
        append_vertical_conical_frustum(
            elements=elements,
            bottom_radius=foundation_radius,
            top_radius=pedestal_radius,
            z_min=edge_h,
            height=slope_height,
            segments=96,
        )

    append_vertical_cylinder(elements, pedestal_radius, center_h, data["pedestal_height"])

    for pile in data["pile_centers"]:
        append_vertical_cylinder(
            elements,
            data["pile_diameter"] / 2.0,
            -data["pile_depth"],
            data["pile_depth"],
            pile["x"],
            pile["y"],
        )


def add_foundation_rebar_visual(elements: ModelEleList, data: dict) -> None:
    foundation_radius = data["foundation_diameter"] / 2.0
    pedestal_radius = data["pedestal_diameter"] / 2.0
    cover = data["cover"]
    outer_radius = max(0.0, foundation_radius - cover)
    bottom_inner_radius = cover
    top_inner_radius = max(cover, pedestal_radius * 0.35)

    ring_diameter = data["ring_bar_diameter"]
    append_circular_rebar_area(
        elements=elements,
        position_number=101,
        diameter=ring_diameter,
        radial_profile=[
            (pedestal_radius + cover, cover),
            (outer_radius, cover),
        ],
        spacing=data["ring_spacing"],
    )

    top_profile = [
        (top_inner_radius, foundation_top_z(data, top_inner_radius) - cover),
    ]
    if top_inner_radius < pedestal_radius < outer_radius:
        top_profile.append(
            (pedestal_radius, foundation_top_z(data, pedestal_radius) - cover)
        )
    top_profile.append(
        (outer_radius, foundation_top_z(data, outer_radius) - cover)
    )
    append_circular_rebar_area(
        elements=elements,
        position_number=102,
        diameter=ring_diameter,
        radial_profile=top_profile,
        spacing=data["ring_spacing"],
    )

    # Bottom radial bars: one real rotational Allplan placement.
    append_radial_rebar_set(
        elements=elements,
        position_number=6100,
        diameter=data["bottom_radial_bar_diameter"],
        r_start=bottom_inner_radius,
        r_end=outer_radius,
        z_start=cover,
        z_end=cover,
        bar_count=data["bottom_radial_bar_count"],
        end_hook_length=outer_radial_hook_length(data),
        end_hook_angle=90.0,
    )

    # Top radial bars: one real rotational Allplan placement.
    # The seed bar is inclined in the XZ plane, then Allplan rotates it around Z.
    top_slope_start_radius = min(max(pedestal_radius + cover, top_inner_radius), outer_radius)
    top_slope_end_radius = outer_radius

    top_slope_start_z = foundation_top_z(data, top_slope_start_radius) - cover
    top_slope_end_z = foundation_top_z(data, top_slope_end_radius) - cover

    _log(
        "Top radial rotational placement: "
        f"r_start={top_slope_start_radius:.2f}, "
        f"z_start={top_slope_start_z:.2f}, "
        f"r_end={top_slope_end_radius:.2f}, "
        f"z_end={top_slope_end_z:.2f}, "
        f"count={data['top_radial_bar_count']}"
    )

    append_radial_rebar_set(
        elements=elements,
        position_number=7100,
        diameter=data["top_radial_bar_diameter"],
        r_start=top_slope_start_radius,
        r_end=top_slope_end_radius,
        z_start=top_slope_start_z,
        z_end=top_slope_end_z,
        bar_count=data["top_radial_bar_count"],
        start_hook_length=inner_radial_hook_length(data["top_radial_bar_diameter"]),
        start_hook_angle=-90.0,
        end_hook_length=outer_radial_hook_length(data),
        end_hook_angle=-90.0,
    )


def add_pedestal_rebar_visual(elements: ModelEleList, data: dict) -> None:
    pedestal_radius = data["pedestal_diameter"] / 2.0
    clear_radius = max(0.0, pedestal_radius - data["cover"])
    frame_radius = pedestal_frame_radius(data)
    bar_diameter = data["pedestal_grid_bar_diameter"]
    frame_z_bottom = pedestal_frame_bottom_z(data)
    tie_z_bottom = frame_z_bottom
    z_top = data["foundation_center_thickness"] + data["pedestal_height"] - data["cover"]
    steel_grade = data.get("steel_grade", -1)
    concrete_grade = data.get("concrete_grade", -1)

    for frame_index, x in enumerate(positions_between(-frame_radius, frame_radius, data["pedestal_grid_spacing"])):
        y_half = math.sqrt(max(0.0, frame_radius * frame_radius - x * x))
        append_pedestal_rectangular_frame(
            elements=elements,
            position_number=8000 + frame_index,
            diameter=bar_diameter,
            points=[
                AllplanGeo.Point3D(x, -y_half, frame_z_bottom),
                AllplanGeo.Point3D(x, y_half, frame_z_bottom),
                AllplanGeo.Point3D(x, y_half, z_top),
                AllplanGeo.Point3D(x, -y_half, z_top),
            ],
            steel_grade=steel_grade,
            concrete_grade=concrete_grade,
        )

    for frame_index, y in enumerate(positions_between(-frame_radius, frame_radius, data["pedestal_grid_spacing"])):
        x_half = math.sqrt(max(0.0, frame_radius * frame_radius - y * y))
        append_pedestal_rectangular_frame(
            elements=elements,
            position_number=9000 + frame_index,
            diameter=bar_diameter,
            points=[
                AllplanGeo.Point3D(-x_half, y, frame_z_bottom),
                AllplanGeo.Point3D(x_half, y, frame_z_bottom),
                AllplanGeo.Point3D(x_half, y, z_top),
                AllplanGeo.Point3D(-x_half, y, z_top),
            ],
            steel_grade=steel_grade,
            concrete_grade=concrete_grade,
        )

    append_vertical_circular_rebar_stack(
        elements=elements,
        position_number=201,
        diameter=data["pedestal_tie_diameter"],
        cx=0.0,
        cy=0.0,
        radius=clear_radius,
        z_start=tie_z_bottom,
        z_end=z_top,
        spacing=data["pedestal_tie_spacing"],
    )


def add_pile_rebar_visual(elements: ModelEleList, data: dict) -> None:
    pile_radius = data["pile_diameter"] / 2.0
    cover = data["cover"]
    vertical_diameter = data["pile_vertical_diameter"]
    hoop_diameter = data["pile_hoop_diameter"]
    vertical_count = data["pile_vertical_count"]
    steel_grade = data.get("steel_grade", -1)
    concrete_grade = data.get("concrete_grade", -1)

    if vertical_count < 2:
        raise ValueError("Rotational pile vertical placement needs at least two bars.")

    vertical_axis_radius = pile_radius - cover - vertical_diameter / 2.0
    if vertical_axis_radius <= 0.0:
        raise ValueError("No room left for pile vertical bars after cover and diameter.")

    hoop_axis_radius = pile_radius - cover - hoop_diameter / 2.0
    if hoop_axis_radius <= 0.0:
        raise ValueError("No room left for pile hoops after cover and diameter.")

    if data["pile_hoop_spacing"] <= 0.0:
        raise ValueError("Pile hoop spacing must be positive.")

    z_bottom = -data["pile_depth"] + cover
    hoop_z_top = -cover
    if (hoop_z_top - z_bottom) <= 0.001:
        raise ValueError("Pile reinforcement clear height is zero or negative.")

    for pile_index, pile in enumerate(data["pile_centers"]):
        cx = pile["x"]
        cy = pile["y"]
        vertical_z_top = pile_vertical_top_z(data, math.hypot(cx, cy))

        append_pile_vertical_rebar_set(
            elements=elements,
            position_number=4000 + pile_index,
            diameter=vertical_diameter,
            cx=cx,
            cy=cy,
            radius=vertical_axis_radius,
            z_bottom=z_bottom,
            z_top=vertical_z_top,
            bar_count=vertical_count,
            steel_grade=steel_grade,
            concrete_grade=concrete_grade,
        )

        append_vertical_circular_rebar_stack(
            elements=elements,
            position_number=6000 + pile_index,
            diameter=hoop_diameter,
            cx=cx,
            cy=cy,
            radius=hoop_axis_radius,
            z_start=z_bottom,
            z_end=hoop_z_top,
            spacing=data["pile_hoop_spacing"],
        )


def append_vertical_cylinder(elements: ModelEleList, radius: float, z_min: float, height: float, cx: float = 0.0, cy: float = 0.0) -> None:
    if radius <= 0.0 or height <= 0.0:
        return

    placement = AllplanGeo.AxisPlacement3D(
        AllplanGeo.Point3D(cx, cy, z_min),
        AllplanGeo.Vector3D(1.0, 0.0, 0.0),
        AllplanGeo.Vector3D(0.0, 0.0, 1.0),
    )
    elements.append_geometry_3d(AllplanGeo.BRep3D.CreateCylinder(placement, radius, height))


def append_vertical_conical_frustum(
    elements: ModelEleList,
    bottom_radius: float,
    top_radius: float,
    z_min: float,
    height: float,
    cx: float = 0.0,
    cy: float = 0.0,
    segments: int = 96,
) -> None:
    if bottom_radius <= 0.0 or top_radius <= 0.0 or height <= 0.0:
        return

    full_circle = float(AllplanGeo.Angle.FromDeg(360))

    bottom_profile = AllplanGeo.Arc3D(
        center=AllplanGeo.Point3D(cx, cy, z_min),
        minor=bottom_radius,
        major=bottom_radius,
        startAngle=0.0,
        deltaAngle=full_circle,
    )

    top_profile = AllplanGeo.Arc3D(
        center=AllplanGeo.Point3D(cx, cy, z_min + height),
        minor=top_radius,
        major=top_radius,
        startAngle=0.0,
        deltaAngle=full_circle,
    )

    error_code, frustum = AllplanGeo.CreateLoftedBRep3D(
        [bottom_profile, top_profile],
        Curve3DList(),
        True,
        False,
        True,
        False,
    )

    if frustum is None or error_code != AllplanGeo.eOK:
        raise RuntimeError(
            f"Could not create foundation conical frustum. Allplan error code: {error_code}"
        )

    elements.append_geometry_3d(frustum)


def append_pedestal_rectangular_frame(
    elements: ModelEleList,
    position_number: int,
    diameter: float,
    points: list[AllplanGeo.Point3D],
    steel_grade: int = -1,
    concrete_grade: int = -1,
) -> None:
    shape = create_world_rectangular_stirrup_shape(
        diameter=diameter,
        points=points,
        steel_grade=steel_grade,
        concrete_grade=concrete_grade,
    )
    if shape is None:
        return

    placement = AllplanReinf.BarPlacement(
        position_number,
        1,
        AllplanGeo.Vector3D(),
        AllplanGeo.Point3D(),
        AllplanGeo.Point3D(),
        shape,
    )

    elements.append(placement)


def create_world_rectangular_stirrup_shape(
    diameter: float,
    points: list[AllplanGeo.Point3D],
    steel_grade: int = -1,
    concrete_grade: int = -1,
):
    if diameter <= 0.0:
        raise RuntimeError("Pedestal rectangular frame diameter must be greater than zero.")

    if len(points) != 4:
        raise RuntimeError("Pedestal rectangular frame requires exactly four corner points.")

    for start_point, end_point in zip(points, points[1:] + points[:1]):
        if point_distance(start_point, end_point) <= 0.001:
            return None

    shape_polyline = AllplanGeo.Polyline3D()
    for point in points + [points[0]]:
        shape_polyline += point

    bending_roller_factor = AllplanReinf.BendingRollerService.GetBendingRollerFactor(
        diameter,
        steel_grade,
        concrete_grade,
        True,
    )
    bending_roller = AllplanUtil.VecDoubleList([bending_roller_factor] * 5)
    bending_shape = AllplanReinf.BendingShape(
        shape_polyline,
        bending_roller,
        diameter,
        steel_grade,
        concrete_grade,
        AllplanReinf.BendingShapeType.Stirrup,
    )

    try:
        if not bending_shape.IsValid():
            raise RuntimeError("Created pedestal rectangular frame shape is invalid.")
    except AttributeError:
        pass

    return bending_shape


def point_distance(left: AllplanGeo.Point3D, right: AllplanGeo.Point3D) -> float:
    dx = right.X - left.X
    dy = right.Y - left.Y
    dz = right.Z - left.Z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def append_circular_rebar_area(
    elements: ModelEleList,
    position_number: int,
    diameter: float,
    radial_profile: list[tuple[float, float]],
    spacing: float,
    cx: float = 0.0,
    cy: float = 0.0,
    start_angle: float = 0.0,
    end_angle: float = 360.0,
    max_bar_length: float = 18000.0,
    min_bar_length: float = 1000.0,
    max_bar_rise: float = 10000.0,
) -> None:
    if diameter <= 0.0 or spacing <= 0.0:
        return

    clean_profile = [
        (float(radius), float(z))
        for radius, z in radial_profile
        if radius > 0.0
    ]
    if len(clean_profile) < 2:
        return

    clean_profile.sort(key=lambda item: item[0])
    inner_radius = clean_profile[0][0]
    outer_radius = clean_profile[-1][0]
    if outer_radius <= inner_radius:
        return

    contour = AllplanGeo.Polyline3D()
    for radius, z in clean_profile:
        contour += AllplanGeo.Point3D(cx + radius, cy, z)

    rotation_axis = AllplanGeo.Line3D(
        AllplanGeo.Point3D(cx, cy, 0.0),
        AllplanGeo.Point3D(cx, cy, 1.0),
    )
    circular_area = AllplanReinf.CircularAreaElement(
        position_number,
        diameter,
        -1,
        -1,
        rotation_axis,
        contour,
        start_angle,
        end_angle,
        start_angle,
        end_angle,
        0.0,
        0.0,
        0.0,
    )
    circular_area.SetBarProperties(
        spacing,
        max_bar_length,
        min_bar_length,
        0,
        max_bar_length,
        max_bar_length,
        0.0,
        max_bar_rise,
    )
    circular_area.SetOverlap(
        0.0,
        0.0,
        False,
        0.0,
        0.0,
        False,
        50.0 * diameter,
    )
    elements.append(circular_area)


def append_vertical_circular_rebar_stack(
    elements: ModelEleList,
    position_number: int,
    diameter: float,
    cx: float,
    cy: float,
    radius: float,
    z_start: float,
    z_end: float,
    spacing: float,
    start_angle: float = 0.0,
    end_angle: float = 360.0,
    max_bar_length: float = 18000.0,
    min_bar_length: float = 1000.0,
    max_bar_rise: float = 10000.0,
) -> None:
    if diameter <= 0.0 or radius <= 0.0 or spacing <= 0.0:
        return
    if z_end <= z_start:
        return

    contour = AllplanGeo.Polyline3D()
    contour += AllplanGeo.Point3D(cx + radius, cy, z_start)
    contour += AllplanGeo.Point3D(cx + radius, cy, z_end)
    rotation_axis = AllplanGeo.Line3D(
        AllplanGeo.Point3D(cx, cy, z_start),
        AllplanGeo.Point3D(cx, cy, z_start + 1.0),
    )
    circular_area = AllplanReinf.CircularAreaElement(
        position_number,
        diameter,
        -1,
        -1,
        rotation_axis,
        contour,
        start_angle,
        end_angle,
        start_angle,
        end_angle,
        0.0,
        0.0,
        0.0,
    )
    circular_area.SetBarProperties(
        spacing,
        max_bar_length,
        min_bar_length,
        0,
        max_bar_length,
        max_bar_length,
        0.0,
        max_bar_rise,
    )
    circular_area.SetOverlap(
        0.0,
        0.0,
        False,
        0.0,
        0.0,
        False,
        50.0 * diameter,
    )
    elements.append(circular_area)


def append_radial_rebar_set(
    elements: ModelEleList,
    position_number: int,
    diameter: float,
    r_start: float,
    r_end: float,
    z_start: float,
    z_end: float,
    bar_count: int,
    start_hook_length: float = -1.0,
    start_hook_angle: float = 90.0,
    end_hook_length: float = -1.0,
    end_hook_angle: float = 90.0,
) -> None:
    if diameter <= 0.0:
        return

    if bar_count <= 0:
        return

    if r_end <= r_start:
        return

    start_point = AllplanGeo.Point3D(r_start, 0.0, z_start)
    end_point = AllplanGeo.Point3D(r_end, 0.0, z_end)

    bending_shape = create_straight_rebar_shape_from_points(
        diameter=diameter,
        start_point=start_point,
        end_point=end_point,
        start_hook_length=start_hook_length,
        start_hook_angle=start_hook_angle,
        end_hook_length=end_hook_length,
        end_hook_angle=end_hook_angle,
    )

    rotation_axis = AllplanGeo.Line3D(
        AllplanGeo.Point3D(0.0, 0.0, 0.0),
        AllplanGeo.Point3D(0.0, 0.0, 1.0),
    )

    rotation_angle = AllplanGeo.Angle.FromDeg(360.0 / float(bar_count))

    placement = AllplanReinf.BarPlacement(
        position_number,
        bar_count,
        rotation_axis,
        rotation_angle,
        bending_shape,
    )

    elements.append(placement)


def append_pile_vertical_rebar_set(
    elements: ModelEleList,
    position_number: int,
    diameter: float,
    cx: float,
    cy: float,
    radius: float,
    z_bottom: float,
    z_top: float,
    bar_count: int,
    steel_grade: int = -1,
    concrete_grade: int = -1,
) -> None:
    if diameter <= 0.0:
        return

    if bar_count < 2:
        raise ValueError("Rotational pile vertical placement needs at least two bars.")

    if radius <= 0.0:
        raise ValueError("Pile vertical bar axis radius must be positive.")

    if z_top <= z_bottom:
        raise ValueError("Pile vertical bar clear height must be positive.")

    start_point = AllplanGeo.Point3D(cx + radius, cy, z_bottom)
    end_point = AllplanGeo.Point3D(cx + radius, cy, z_top)

    bending_shape = create_straight_rebar_shape_from_points(
        diameter=diameter,
        start_point=start_point,
        end_point=end_point,
        steel_grade=steel_grade,
        concrete_grade=concrete_grade,
    )

    rotation_axis = AllplanGeo.Line3D(
        AllplanGeo.Point3D(cx, cy, z_bottom),
        AllplanGeo.Point3D(cx, cy, z_bottom + 1.0),
    )
    rotation_angle = AllplanGeo.Angle.FromDeg(360.0 / float(bar_count))

    placement = AllplanReinf.BarPlacement(
        position_number,
        bar_count,
        rotation_axis,
        rotation_angle,
        bending_shape,
    )

    elements.append(placement)


def create_straight_rebar_shape_from_points(
    diameter: float,
    start_point: AllplanGeo.Point3D,
    end_point: AllplanGeo.Point3D,
    steel_grade: int = -1,
    concrete_grade: int = -1,
    start_hook_length: float = -1.0,
    start_hook_angle: float = 90.0,
    end_hook_length: float = -1.0,
    end_hook_angle: float = 90.0,
):
    return create_oriented_straight_rebar_shape(
        diameter=diameter,
        start_point=start_point,
        end_point=end_point,
        steel_grade=steel_grade,
        concrete_grade=concrete_grade,
        start_hook_length=start_hook_length,
        start_hook_angle=start_hook_angle,
        end_hook_length=end_hook_length,
        end_hook_angle=end_hook_angle,
    )


def create_oriented_straight_rebar_shape(
    diameter: float,
    start_point: AllplanGeo.Point3D,
    end_point: AllplanGeo.Point3D,
    steel_grade: int = -1,
    concrete_grade: int = -1,
    start_hook_length: float = -1.0,
    start_hook_angle: float = 90.0,
    end_hook_length: float = -1.0,
    end_hook_angle: float = 90.0,
):
    if diameter <= 0.0:
        raise RuntimeError("Rebar diameter must be greater than zero.")

    dx = end_point.X - start_point.X
    dy = end_point.Y - start_point.Y
    dz = end_point.Z - start_point.Z

    length = math.sqrt(dx * dx + dy * dy + dz * dz)

    if length <= 0.001:
        raise RuntimeError("Cannot create rebar with zero length.")

    shape_properties = ReinforcementShapeProperties.rebar(
        diameter=diameter,
        bending_roller=-1,
        steel_grade=steel_grade,
        concrete_grade=concrete_grade,
        bending_shape_type=AllplanReinf.BendingShapeType.LongitudinalBar,
    )

    has_hook = start_hook_length >= 0.0 or end_hook_length >= 0.0
    if has_hook:
        # Local X is the bar axis. Rotating local Y into global Z makes 90-degree
        # radial hooks bend vertically before the seed bar is aligned to the slope.
        bending_shape = GeneralShapeBuilder.create_longitudinal_shape_with_user_hooks(
            length=length,
            model_angles=RotationUtil(90.0, 0.0, 0.0),
            shape_props=shape_properties,
            concrete_cover_props=ConcreteCoverProperties.all(0.0),
            start_hook=start_hook_length,
            end_hook=end_hook_length,
            start_hook_angle=start_hook_angle,
            end_hook_angle=end_hook_angle,
            hook_type_start=-1,
            hook_type_end=-1,
        )
    else:
        # Create the bar locally along +X.
        bending_shape = GeneralShapeBuilder.create_longitudinal_shape_with_anchorage(
            from_point=AllplanGeo.Point3D(0.0, 0.0, 0.0),
            to_point=AllplanGeo.Point3D(length, 0.0, 0.0),
            shape_props=shape_properties,
            concrete_cover_props=ConcreteCoverProperties.all(0.0),
            start_anchorage=0.0,
            end_anchorage=0.0,
        )

    # Rotate local +X into the real 3D bar direction.
    target_x = dx / length
    target_y = dy / length
    target_z = dz / length

    already_local_x = (
        abs(target_x - 1.0) <= 0.000001
        and abs(target_y) <= 0.000001
        and abs(target_z) <= 0.000001
    )

    if not already_local_x:
        target_direction = AllplanGeo.Vector3D(
            target_x,
            target_y,
            target_z,
        )

        rotation_matrix = AllplanGeo.Matrix3D()
        rotation_ok = rotation_matrix.SetRotation(
            AllplanGeo.Vector3D(1.0, 0.0, 0.0),
            target_direction,
        )

        if not rotation_ok:
            raise RuntimeError(
                "Could not rotate radial rebar shape from local X axis to target direction."
            )

        bending_shape.Transform(rotation_matrix)

    # Move the rotated bar to its real start point.
    bending_shape.Move(
        AllplanGeo.Vector3D(
            start_point.X,
            start_point.Y,
            start_point.Z,
        )
    )

    try:
        if not bending_shape.IsValid():
            raise RuntimeError("Created radial rebar bending shape is invalid.")
    except AttributeError:
        pass

    return bending_shape


def append_ring(elements: ModelEleList, bar_radius: float, cx: float, cy: float, radius: float, z: float, segments: int = 72) -> None:
    points = []
    for index in range(segments + 1):
        angle = 2.0 * math.pi * index / segments
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), z))
    append_polyline_cylinders(elements, bar_radius, points)


def append_polyline_cylinders(elements: ModelEleList, radius: float, points: list[tuple[float, float, float]]) -> None:
    for start, end in zip(points, points[1:]):
        append_cylinder_between(elements, radius, start, end)


def append_cylinder_between(elements: ModelEleList, radius: float, start: tuple[float, float, float], end: tuple[float, float, float]) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length == 0.0:
        return

    axis_values = (dx / length, dy / length, dz / length)
    axis = AllplanGeo.Vector3D(*axis_values)
    reference = perpendicular_reference_vector(axis_values)

    placement = AllplanGeo.AxisPlacement3D(point(start), reference, axis)
    elements.append_geometry_3d(AllplanGeo.BRep3D.CreateCylinder(placement, radius, length))


def perpendicular_reference_vector(axis: tuple[float, float, float]):
    candidate = (0.0, 0.0, 1.0)
    if abs(axis[2]) > 0.9:
        candidate = (1.0, 0.0, 0.0)

    ref = cross(candidate, axis)
    length = math.sqrt(ref[0] * ref[0] + ref[1] * ref[1] + ref[2] * ref[2])
    if length == 0.0:
        ref = cross((0.0, 1.0, 0.0), axis)
        length = math.sqrt(ref[0] * ref[0] + ref[1] * ref[1] + ref[2] * ref[2])

    return AllplanGeo.Vector3D(ref[0] / length, ref[1] / length, ref[2] / length)


def cross(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def foundation_top_z(data: dict, radius: float) -> float:
    foundation_radius = data["foundation_diameter"] / 2.0
    pedestal_radius = data["pedestal_diameter"] / 2.0
    edge_h = data["foundation_edge_thickness"]
    center_h = data["foundation_center_thickness"]
    if radius <= pedestal_radius:
        return center_h
    if radius >= foundation_radius:
        return edge_h
    slope_span = max(1.0, foundation_radius - pedestal_radius)
    return center_h - (center_h - edge_h) * (radius - pedestal_radius) / slope_span


def pile_vertical_top_z(data: dict, pile_distance: float) -> float:
    embed_depth = max(0.0, data.get("pile_vertical_embed_depth", 0.0))
    cap_clear_top_z = max(0.0, foundation_top_z(data, pile_distance) - data["cover"])
    return min(embed_depth, cap_clear_top_z)


def outer_radial_hook_length(data: dict) -> float:
    return max(0.0, data["foundation_edge_thickness"] * 0.5)


def inner_radial_hook_length(diameter: float) -> float:
    return max(12.0 * diameter, 100.0)


def pedestal_frame_radius(data: dict) -> float:
    return max(0.0, data["pedestal_diameter"] / 2.0 - data["cover"])


def pedestal_frame_bottom_z(data: dict) -> float:
    center_h = data["foundation_center_thickness"]
    bottom_slab_embed_z = data["foundation_edge_thickness"] * 0.875
    bottom_rebar_clearance_z = data["cover"] + max(
        250.0,
        3.0
        * max(
            data.get("bottom_radial_bar_diameter", 0.0),
            data.get("ring_bar_diameter", 0.0),
            data.get("pedestal_grid_bar_diameter", 0.0),
            data.get("pedestal_tie_diameter", 0.0),
        ),
    )
    return min(
        center_h - data["cover"],
        max(bottom_slab_embed_z, bottom_rebar_clearance_z),
    )


def rectangular_frame_count(radius: float, spacing: float) -> int:
    count = 0
    for offset in positions_between(-radius, radius, spacing):
        chord = 2.0 * math.sqrt(max(0.0, radius * radius - offset * offset))
        if chord > 1.0:
            count += 1
    return count


def positions_between(start: float, end: float, spacing: float) -> list[float]:
    if end < start:
        return []

    span = end - start
    count = int(span // spacing) + 1
    if count <= 1:
        return [(start + end) / 2.0]
    return [start + index * span / (count - 1) for index in range(count)]


def radii_between(start: float, end: float, spacing: float) -> list[float]:
    return positions_between(start, end, spacing)


def point(coords: tuple[float, float, float]):
    return AllplanGeo.Point3D(coords[0], coords[1], coords[2])


def build_result(data: dict, run_id: str, project_name: str) -> dict:
    foundation_radius = data["foundation_diameter"] / 2.0
    pedestal_radius = data["pedestal_diameter"] / 2.0
    cover = data["cover"]
    outer_radius = max(0.0, foundation_radius - cover)
    ring_count = len(radii_between(pedestal_radius + cover, outer_radius, data["ring_spacing"]))
    top_ring_count = len(radii_between(max(cover, pedestal_radius * 0.35), outer_radius, data["ring_spacing"]))
    pile_rebar_bottom_z = -data["pile_depth"] + cover
    pile_hoop_top_z = -cover
    pile_vertical_z_top = pile_vertical_top_z(data, data["pile_ring_radius"])
    pile_hoop_count = len(positions_between(pile_rebar_bottom_z, pile_hoop_top_z, data["pile_hoop_spacing"]))
    frame_radius = pedestal_frame_radius(data)
    pedestal_frame_count = rectangular_frame_count(frame_radius, data["pedestal_grid_spacing"])
    pedestal_tie_count = len(
        positions_between(
            pedestal_frame_bottom_z(data),
            data["foundation_center_thickness"] + data["pedestal_height"] - cover,
            data["pedestal_tie_spacing"],
        )
    )

    return {
        "run_id": run_id,
        "project_name": project_name,
        "drawing_file_number": DRAWING_FILE_NUMBER,
        "created": {
            "circular_foundation": 1,
            "foundation_slope_slices": 0,
            "foundation_slope_frustum": 1 if (
                data["foundation_center_thickness"] > data["foundation_edge_thickness"]
                and foundation_radius > pedestal_radius
            ) else 0,
            "pedestal": 1,
            "piles": len(data["pile_centers"]),
            "base_ring_bars": ring_count,
            "top_cap_ring_bars": top_ring_count,
            "top_real_radial_bars": data["top_radial_bar_count"],
            "bottom_real_radial_bars": data["bottom_radial_bar_count"],
            "top_radial_inner_90_degree_hook_length": inner_radial_hook_length(data["top_radial_bar_diameter"]),
            "bottom_radial_inner_90_degree_hook_length": 0.0,
            "top_radial_outer_90_degree_hook_length": outer_radial_hook_length(data),
            "bottom_radial_outer_90_degree_hook_length": outer_radial_hook_length(data),
            "top_radial_90_degree_hooks_per_bar": 2,
            "bottom_radial_90_degree_hooks_per_bar": 1,
            "pedestal_rectangular_frames": 2 * pedestal_frame_count,
            "pedestal_circular_ties": pedestal_tie_count,
            "pile_real_vertical_bar_placements": len(data["pile_centers"]),
            "pile_real_vertical_bars": len(data["pile_centers"]) * data["pile_vertical_count"],
            "pile_vertical_embed_depth": max(0.0, pile_vertical_z_top),
            "pile_real_hoop_stacks": len(data["pile_centers"]),
            "pile_real_hoops": len(data["pile_centers"]) * pile_hoop_count,
        },
        "inputs": _public_inputs(data),
    }
