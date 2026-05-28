import json
import math
import traceback
from pathlib import Path

import NemAll_Python_BaseElements as AllplanBaseElements
import NemAll_Python_Geometry as AllplanGeo
import NemAll_Python_Reinforcement as AllplanReinf
import StdReinfShapeBuilder.GeneralReinfShapeBuilder as GeneralShapeBuilder
from CreateElementResult import CreateElementResult
from StdReinfShapeBuilder.ConcreteCoverProperties import ConcreteCoverProperties
from StdReinfShapeBuilder.ReinforcementShapeProperties import ReinforcementShapeProperties
from TypeCollections.Curve3DList import Curve3DList
from TypeCollections.ModelEleList import ModelEleList


PROJECT_NAME = "viktor-template"
DRAWING_FILE_NUMBER = 1


def _log(message: str) -> None:
    log_path = Path(__file__).with_name("worker_log.txt")
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{message}\n")


def _write_error(error: BaseException) -> None:
    error_path = Path(__file__).with_name("worker_error.txt")
    error_path.write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )


def check_allplan_version(build_ele, version: float) -> bool:
    return True


def _load_inputs() -> dict:
    with Path(__file__).with_name("inputs.json").open("r", encoding="utf-8") as file:
        return json.load(file)


def _open_project(doc) -> None:
    current_project_name, host_name = AllplanBaseElements.ProjectService.GetCurrentProjectNameAndHost()

    if current_project_name == PROJECT_NAME:
        _log(f"Project '{PROJECT_NAME}' is already active.")
        return

    open_result = AllplanBaseElements.ProjectService.OpenProject(
        doc,
        host_name,
        PROJECT_NAME,
    )

    _log(f"OpenProject returned: {open_result}")

    if open_result not in ("Project opened", "Active project", "project opened"):
        raise RuntimeError(
            f"Could not open Allplan project '{PROJECT_NAME}'. "
            f"Current project was '{current_project_name}'. "
            f"Allplan returned: '{open_result}'."
        )


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

        done_marker = Path(__file__).with_name("worker_done.txt")
        result_path = Path(__file__).with_name("result.json")

        _log(f"Run ID: {run_id}.")
        _log("Opening project.")
        _open_project(doc)

        _log("Project opened.")
        _log(f"Loading drawing file {DRAWING_FILE_NUMBER}.")
        _load_drawing_file(doc)

        _log("Drawing file loaded.")
        _log("Creating circular foundation, piles, and visual rebar geometry.")
        model_elements = create_model_elements(data)

        _log_model_elements(model_elements)

        result = build_result(data, run_id)
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
    )


def add_pedestal_rebar_visual(elements: ModelEleList, data: dict) -> None:
    pedestal_radius = data["pedestal_diameter"] / 2.0
    clear_radius = max(0.0, pedestal_radius - data["cover"])
    bar_radius = data["pedestal_grid_bar_diameter"] / 2.0
    z_bottom = data["foundation_center_thickness"] + data["cover"]
    z_top = data["foundation_center_thickness"] + data["pedestal_height"] - data["cover"]

    for x in positions_between(-clear_radius, clear_radius, data["pedestal_grid_spacing"]):
        y_half = math.sqrt(max(0.0, clear_radius * clear_radius - x * x))
        append_vertical_rect_frame_y(elements, bar_radius, x, -y_half, y_half, z_bottom, z_top)

    for y in positions_between(-clear_radius, clear_radius, data["pedestal_grid_spacing"]):
        x_half = math.sqrt(max(0.0, clear_radius * clear_radius - y * y))
        append_vertical_rect_frame_x(elements, bar_radius, -x_half, x_half, y, z_bottom, z_top)

    append_vertical_circular_rebar_stack(
        elements=elements,
        position_number=201,
        diameter=data["pedestal_tie_diameter"],
        cx=0.0,
        cy=0.0,
        radius=clear_radius,
        z_start=z_bottom,
        z_end=z_top,
        spacing=data["pedestal_tie_spacing"],
    )


def add_pile_rebar_visual(elements: ModelEleList, data: dict) -> None:
    radius = data["pile_diameter"] / 2.0 - data["cover"]
    if radius <= 0.0:
        return

    z_min = -data["pile_depth"]
    vertical_radius = data["pile_vertical_diameter"] / 2.0
    hoop_radius = data["pile_hoop_diameter"] / 2.0

    for pile in data["pile_centers"]:
        cx = pile["x"]
        cy = pile["y"]
        pile_distance = math.hypot(cx, cy)
        z_max = pile_rebar_extension(data, pile_distance)

        for index in range(data["pile_vertical_count"]):
            angle = 2.0 * math.pi * index / data["pile_vertical_count"]
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            append_cylinder_z(elements, vertical_radius, x, y, z_min, z_max)

        for z in positions_between(z_min, 0.0, data["pile_hoop_spacing"]):
            append_ring(elements, hoop_radius, cx, cy, radius, z, segments=20)


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


def append_cylinder_x(elements: ModelEleList, radius: float, x_min: float, x_max: float, y: float, z: float) -> None:
    if x_max <= x_min:
        return

    placement = AllplanGeo.AxisPlacement3D(
        AllplanGeo.Point3D(x_min, y, z),
        AllplanGeo.Vector3D(0.0, 1.0, 0.0),
        AllplanGeo.Vector3D(1.0, 0.0, 0.0),
    )
    elements.append_geometry_3d(AllplanGeo.BRep3D.CreateCylinder(placement, radius, x_max - x_min))


def append_cylinder_y(elements: ModelEleList, radius: float, x: float, y_min: float, y_max: float, z: float) -> None:
    if y_max <= y_min:
        return

    placement = AllplanGeo.AxisPlacement3D(
        AllplanGeo.Point3D(x, y_min, z),
        AllplanGeo.Vector3D(1.0, 0.0, 0.0),
        AllplanGeo.Vector3D(0.0, 1.0, 0.0),
    )
    elements.append_geometry_3d(AllplanGeo.BRep3D.CreateCylinder(placement, radius, y_max - y_min))


def append_cylinder_z(elements: ModelEleList, radius: float, x: float, y: float, z_min: float, z_max: float) -> None:
    if z_max <= z_min:
        return

    placement = AllplanGeo.AxisPlacement3D(
        AllplanGeo.Point3D(x, y, z_min),
        AllplanGeo.Vector3D(1.0, 0.0, 0.0),
        AllplanGeo.Vector3D(0.0, 0.0, 1.0),
    )
    elements.append_geometry_3d(AllplanGeo.BRep3D.CreateCylinder(placement, radius, z_max - z_min))


def append_vertical_rect_frame_y(
    elements: ModelEleList,
    radius: float,
    x: float,
    y_min: float,
    y_max: float,
    z_bottom: float,
    z_top: float,
) -> None:
    if y_max <= y_min or z_top <= z_bottom:
        return

    append_cylinder_y(elements, radius, x, y_min, y_max, z_bottom)
    append_cylinder_y(elements, radius, x, y_min, y_max, z_top)
    append_cylinder_z(elements, radius, x, y_min, z_bottom, z_top)
    append_cylinder_z(elements, radius, x, y_max, z_bottom, z_top)


def append_vertical_rect_frame_x(
    elements: ModelEleList,
    radius: float,
    x_min: float,
    x_max: float,
    y: float,
    z_bottom: float,
    z_top: float,
) -> None:
    if x_max <= x_min or z_top <= z_bottom:
        return

    append_cylinder_x(elements, radius, x_min, x_max, y, z_bottom)
    append_cylinder_x(elements, radius, x_min, x_max, y, z_top)
    append_cylinder_z(elements, radius, x_min, y, z_bottom, z_top)
    append_cylinder_z(elements, radius, x_max, y, z_bottom, z_top)


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


def create_straight_rebar_shape_from_points(
    diameter: float,
    start_point: AllplanGeo.Point3D,
    end_point: AllplanGeo.Point3D,
):
    return create_oriented_straight_rebar_shape(
        diameter=diameter,
        start_point=start_point,
        end_point=end_point,
    )


def create_oriented_straight_rebar_shape(
    diameter: float,
    start_point: AllplanGeo.Point3D,
    end_point: AllplanGeo.Point3D,
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
        steel_grade=-1,
        concrete_grade=-1,
        bending_shape_type=AllplanReinf.BendingShapeType.LongitudinalBar,
    )

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


def pile_rebar_extension(data: dict, radius: float) -> float:
    local_cap_thickness = foundation_top_z(data, radius)
    return max(0.0, min(local_cap_thickness - data["cover"], local_cap_thickness * 0.45))


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


def build_result(data: dict, run_id: str) -> dict:
    foundation_radius = data["foundation_diameter"] / 2.0
    pedestal_radius = data["pedestal_diameter"] / 2.0
    cover = data["cover"]
    outer_radius = max(0.0, foundation_radius - cover)
    ring_count = len(radii_between(pedestal_radius + cover, outer_radius, data["ring_spacing"]))
    top_ring_count = len(radii_between(max(cover, pedestal_radius * 0.35), outer_radius, data["ring_spacing"]))
    pile_hoop_count = len(positions_between(-data["pile_depth"], 0.0, data["pile_hoop_spacing"]))
    pedestal_clear_radius = max(0.0, pedestal_radius - cover)
    pedestal_frame_count = len(positions_between(-pedestal_clear_radius, pedestal_clear_radius, data["pedestal_grid_spacing"]))
    pedestal_tie_count = len(
        positions_between(
            data["foundation_center_thickness"] + cover,
            data["foundation_center_thickness"] + data["pedestal_height"] - cover,
            data["pedestal_tie_spacing"],
        )
    )

    return {
        "run_id": run_id,
        "project_name": PROJECT_NAME,
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
            "pedestal_rectangular_frames": 2 * pedestal_frame_count,
            "pedestal_circular_ties": pedestal_tie_count,
            "pile_visual_vertical_bars": len(data["pile_centers"]) * data["pile_vertical_count"],
            "pile_visual_hoops": len(data["pile_centers"]) * pile_hoop_count,
        },
        "inputs": data,
    }
