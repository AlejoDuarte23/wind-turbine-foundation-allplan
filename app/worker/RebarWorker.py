import json
import math
import traceback
from pathlib import Path

import NemAll_Python_BaseElements as AllplanBaseElements
import NemAll_Python_Geometry as AllplanGeo
from CreateElementResult import CreateElementResult
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
        _log("Returning model elements through CreateElementResult.")

        return CreateElementResult(model_elements)

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
        stack_count = 18
        stack_height = slope_height / stack_count
        for index in range(stack_count):
            fraction = (index + 1) / stack_count
            radius = foundation_radius - (foundation_radius - pedestal_radius) * fraction
            append_vertical_cylinder(elements, radius, edge_h + index * stack_height, stack_height)

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
    avoid_radius = data["pile_diameter"] / 2.0 + cover + data["trim_clearance"]

    ring_bar_radius = data["ring_bar_diameter"] / 2.0
    for radius in radii_between(pedestal_radius + cover, outer_radius, data["ring_spacing"]):
        append_trimmed_ring(elements, ring_bar_radius, radius, cover, data, avoid_radius)

    bottom_bar_radius = data["bottom_radial_bar_diameter"] / 2.0
    for index in range(data["bottom_radial_bar_count"]):
        angle = 2.0 * math.pi * index / data["bottom_radial_bar_count"]
        append_trimmed_radial_bar(
            elements,
            bottom_bar_radius,
            angle,
            bottom_inner_radius,
            outer_radius,
            lambda radius: cover,
            data,
            avoid_radius,
        )

    top_bar_radius = data["top_radial_bar_diameter"] / 2.0
    for index in range(data["top_radial_bar_count"]):
        angle = 2.0 * math.pi * index / data["top_radial_bar_count"]
        append_trimmed_radial_bar(
            elements,
            top_bar_radius,
            angle,
            top_inner_radius,
            outer_radius,
            lambda radius: foundation_top_z(data, radius) - cover,
            data,
            avoid_radius,
        )


def add_pedestal_rebar_visual(elements: ModelEleList, data: dict) -> None:
    pedestal_radius = data["pedestal_diameter"] / 2.0
    clear_radius = max(0.0, pedestal_radius - data["cover"])
    reduced_radius = max(0.0, clear_radius - 2.5 * data["pedestal_grid_bar_diameter"])
    bar_radius = data["pedestal_grid_bar_diameter"] / 2.0
    z_low = data["foundation_center_thickness"] + data["cover"]
    z_high = z_low + data["pedestal_grid_bar_diameter"] * 1.7

    for x in positions_between(-reduced_radius, reduced_radius, data["pedestal_grid_spacing"]):
        y_half = math.sqrt(max(0.0, reduced_radius * reduced_radius - x * x))
        append_cylinder_y(elements, bar_radius, x, -y_half, y_half, z_low)

    for y in positions_between(-clear_radius, clear_radius, data["pedestal_grid_spacing"]):
        x_half = math.sqrt(max(0.0, clear_radius * clear_radius - y * y))
        append_cylinder_x(elements, bar_radius, -x_half, x_half, y, z_high)


def add_pile_rebar_visual(elements: ModelEleList, data: dict) -> None:
    radius = data["pile_diameter"] / 2.0 - data["cover"]
    if radius <= 0.0:
        return

    z_min = -data["pile_depth"]
    z_max = data["foundation_center_thickness"] - data["cover"]
    vertical_radius = data["pile_vertical_diameter"] / 2.0
    hoop_radius = data["pile_hoop_diameter"] / 2.0

    for pile in data["pile_centers"]:
        cx = pile["x"]
        cy = pile["y"]

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


def append_ring(elements: ModelEleList, bar_radius: float, cx: float, cy: float, radius: float, z: float, segments: int = 72) -> None:
    points = []
    for index in range(segments + 1):
        angle = 2.0 * math.pi * index / segments
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), z))
    append_polyline_cylinders(elements, bar_radius, points)


def append_trimmed_ring(
    elements: ModelEleList,
    bar_radius: float,
    radius: float,
    z: float,
    data: dict,
    avoid_radius: float,
    segments: int = 96,
) -> None:
    current_points = []
    for index in range(segments + 1):
        angle = 2.0 * math.pi * index / segments
        point_coords = (radius * math.cos(angle), radius * math.sin(angle), z)

        if index == segments:
            keep = bool(current_points) and not point_clashes_with_piles(point_coords[0], point_coords[1], data, avoid_radius)
        else:
            midpoint_angle = angle + math.pi / segments
            mx = radius * math.cos(midpoint_angle)
            my = radius * math.sin(midpoint_angle)
            keep = not point_clashes_with_piles(mx, my, data, avoid_radius)

        if keep:
            current_points.append(point_coords)
        else:
            if len(current_points) > 1:
                append_polyline_cylinders(elements, bar_radius, current_points)
            current_points = []

    if len(current_points) > 1:
        append_polyline_cylinders(elements, bar_radius, current_points)


def append_trimmed_radial_bar(
    elements: ModelEleList,
    bar_radius: float,
    angle: float,
    r_start: float,
    r_end: float,
    z_at_radius,
    data: dict,
    avoid_radius: float,
) -> None:
    if r_end <= r_start:
        return

    for start, end in radial_clear_segments(angle, r_start, r_end, data, avoid_radius):
        start_point = radial_point(angle, start, z_at_radius(start))
        end_point = radial_point(angle, end, z_at_radius(end))
        append_cylinder_between(elements, bar_radius, start_point, end_point)


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

    axis = AllplanGeo.Vector3D(dx / length, dy / length, dz / length)
    reference = AllplanGeo.Vector3D(0.0, 0.0, 1.0)
    if abs(axis.Z) > 0.99:
        reference = AllplanGeo.Vector3D(1.0, 0.0, 0.0)

    placement = AllplanGeo.AxisPlacement3D(point(start), reference, axis)
    elements.append_geometry_3d(AllplanGeo.BRep3D.CreateCylinder(placement, radius, length))


def radial_clear_segments(angle: float, r_start: float, r_end: float, data: dict, avoid_radius: float) -> list[tuple[float, float]]:
    segments = [(r_start, r_end)]
    pile_ring_radius = data["pile_ring_radius"]

    for pile in data["pile_centers"]:
        pile_angle = pile["angle"]
        delta = normalize_angle(angle - pile_angle)
        distance_to_ray = abs(pile_ring_radius * math.sin(delta))
        projection = pile_ring_radius * math.cos(delta)

        if distance_to_ray >= avoid_radius or projection <= r_start or projection >= r_end:
            continue

        half_gap = math.sqrt(max(0.0, avoid_radius * avoid_radius - distance_to_ray * distance_to_ray))
        segments = subtract_interval(segments, projection - half_gap, projection + half_gap)

    return segments


def subtract_interval(segments: list[tuple[float, float]], cut_start: float, cut_end: float) -> list[tuple[float, float]]:
    remaining = []
    for start, end in segments:
        if cut_end <= start or cut_start >= end:
            remaining.append((start, end))
            continue

        if cut_start > start:
            remaining.append((start, min(cut_start, end)))
        if cut_end < end:
            remaining.append((max(cut_end, start), end))

    return [(start, end) for start, end in remaining if end - start > 1.0]


def point_clashes_with_piles(x: float, y: float, data: dict, avoid_radius: float) -> bool:
    avoid_square = avoid_radius * avoid_radius
    for pile in data["pile_centers"]:
        dx = x - pile["x"]
        dy = y - pile["y"]
        if dx * dx + dy * dy < avoid_square:
            return True
    return False


def radial_point(angle: float, radius: float, z: float) -> tuple[float, float, float]:
    return (radius * math.cos(angle), radius * math.sin(angle), z)


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


def normalize_angle(angle: float) -> float:
    while angle <= -math.pi:
        angle += 2.0 * math.pi
    while angle > math.pi:
        angle -= 2.0 * math.pi
    return angle


def point(coords: tuple[float, float, float]):
    return AllplanGeo.Point3D(coords[0], coords[1], coords[2])


def build_result(data: dict, run_id: str) -> dict:
    foundation_radius = data["foundation_diameter"] / 2.0
    pedestal_radius = data["pedestal_diameter"] / 2.0
    cover = data["cover"]
    outer_radius = max(0.0, foundation_radius - cover)
    ring_count = len(radii_between(pedestal_radius + cover, outer_radius, data["ring_spacing"]))
    pile_hoop_count = len(positions_between(-data["pile_depth"], 0.0, data["pile_hoop_spacing"]))
    pedestal_clear_radius = max(0.0, pedestal_radius - cover)
    reduced_grid_radius = max(0.0, pedestal_clear_radius - 2.5 * data["pedestal_grid_bar_diameter"])
    pedestal_grid_upper = len(positions_between(-pedestal_clear_radius, pedestal_clear_radius, data["pedestal_grid_spacing"]))
    pedestal_grid_lower = len(positions_between(-reduced_grid_radius, reduced_grid_radius, data["pedestal_grid_spacing"]))

    return {
        "run_id": run_id,
        "project_name": PROJECT_NAME,
        "drawing_file_number": DRAWING_FILE_NUMBER,
        "created": {
            "circular_foundation": 1,
            "foundation_slope_slices": 18 if data["foundation_center_thickness"] > data["foundation_edge_thickness"] else 0,
            "pedestal": 1,
            "piles": len(data["pile_centers"]),
            "base_ring_bars": ring_count,
            "top_radial_bars_before_trimming": data["top_radial_bar_count"],
            "bottom_radial_bars_before_trimming": data["bottom_radial_bar_count"],
            "pedestal_grid_bars": pedestal_grid_upper + pedestal_grid_lower,
            "pile_visual_vertical_bars": len(data["pile_centers"]) * data["pile_vertical_count"],
            "pile_visual_hoops": len(data["pile_centers"]) * pile_hoop_count,
        },
        "inputs": data,
    }
