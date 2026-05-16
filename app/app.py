import json
import math
import uuid
from pathlib import Path

import viktor as vkt
from viktor.external.python import PythonAnalysis


APP_DIR = Path(__file__).parent
ALLPLAN_WORKER_DIR = APP_DIR / "worker"


class Parametrization(vkt.Parametrization):
    geometry = vkt.Section("Geometry", initially_expanded=True)
    geometry.intro = vkt.Text(
        "# Wind Turbine Foundation\n\n"
        "Visual rebar geometry for a circular pile cap, circular pedestal, and piles. "
        "Dimensions are in millimeters."
    )
    geometry.foundation_diameter = vkt.NumberField("Foundation diameter", default=14000.0, min=5000.0, suffix="mm", flex=50)
    geometry.foundation_edge_thickness = vkt.NumberField("Foundation edge thickness", default=900.0, min=300.0, suffix="mm", flex=50)
    geometry.foundation_center_thickness = vkt.NumberField("Foundation center thickness", default=1800.0, min=500.0, suffix="mm", flex=50)
    geometry.pedestal_diameter = vkt.NumberField("Pedestal diameter", default=4200.0, min=1000.0, suffix="mm", flex=50)
    geometry.pedestal_height = vkt.NumberField("Pedestal height", default=2200.0, min=500.0, suffix="mm", flex=50)
    geometry.pile_count = vkt.NumberField("Pile count", default=12, min=3, max=32, flex=50)
    geometry.pile_ring_radius = vkt.NumberField("Pile ring radius", default=5200.0, min=1000.0, suffix="mm", flex=50)
    geometry.pile_diameter = vkt.NumberField("Pile diameter", default=700.0, min=250.0, suffix="mm", flex=50)
    geometry.pile_depth = vkt.NumberField("Pile depth", default=6000.0, min=1000.0, suffix="mm", flex=50)

    reinforcement = vkt.Section("Reinforcement", initially_expanded=True)
    reinforcement.cover = vkt.NumberField("Concrete cover", default=75.0, min=25.0, max=200.0, suffix="mm", flex=50)
    reinforcement.trim_clearance = vkt.NumberField("Pile trim clearance", default=150.0, min=0.0, suffix="mm", flex=50)
    reinforcement.top_radial_bar_diameter = vkt.NumberField("Top radial bar diameter", default=25.0, min=8.0, suffix="mm", flex=50)
    reinforcement.top_radial_bar_count = vkt.NumberField("Top radial bar count", default=32, min=8, max=96, flex=50)
    reinforcement.bottom_radial_bar_diameter = vkt.NumberField("Bottom radial bar diameter", default=25.0, min=8.0, suffix="mm", flex=50)
    reinforcement.bottom_radial_bar_count = vkt.NumberField("Bottom radial bar count", default=32, min=8, max=96, flex=50)
    reinforcement.ring_bar_diameter = vkt.NumberField("Circular base bar diameter", default=20.0, min=8.0, suffix="mm", flex=50)
    reinforcement.ring_spacing = vkt.NumberField("Circular base bar spacing", default=550.0, min=150.0, suffix="mm", flex=50)
    reinforcement.pedestal_grid_bar_diameter = vkt.NumberField("Pedestal grid bar diameter", default=20.0, min=8.0, suffix="mm", flex=50)
    reinforcement.pedestal_grid_spacing = vkt.NumberField("Pedestal grid spacing", default=350.0, min=100.0, suffix="mm", flex=50)
    reinforcement.pile_vertical_diameter = vkt.NumberField("Pile vertical bar diameter", default=16.0, min=8.0, suffix="mm", flex=50)
    reinforcement.pile_vertical_count = vkt.NumberField("Vertical bars per pile", default=8, min=4, max=24, flex=50)
    reinforcement.pile_hoop_diameter = vkt.NumberField("Pile hoop diameter", default=10.0, min=6.0, suffix="mm", flex=50)
    reinforcement.pile_hoop_spacing = vkt.NumberField("Pile hoop spacing", default=300.0, min=100.0, suffix="mm", flex=50)

    allplan = vkt.Section("Allplan", initially_expanded=True)
    allplan.download = vkt.DownloadButton(
        "Download Allplan project",
        method="download_allplan_project",
        longpoll=True,
        flex=100,
    )


class Controller(vkt.Controller):
    label = "Wind Turbine Foundation"
    parametrization = Parametrization(width=36)

    @vkt.WebView("Foundation sketch", duration_guess=1)
    def rebar_sketch(self, params, **kwargs):
        data = self._worker_input(params)
        html = self._build_rebar_html(data)
        return vkt.WebResult(html=html)

    @vkt.TableView("Visual geometry schedule")
    def bar_schedule(self, params, **kwargs):
        rows = self._bar_schedule(self._worker_input(params))
        return vkt.TableResult(
            rows,
            column_headers=[
                "Item",
                "Geometry",
                "Diameter [mm]",
                "Spacing / count",
                "Quantity",
                "Unit length [m]",
                "Total length [m]",
            ],
            enable_sorting_and_filtering=False,
        )

    def download_allplan_project(self, params, **kwargs):
        worker_input = self._worker_input(params)
        run_id = uuid.uuid4().hex
        worker_input["run_id"] = run_id

        files = [
            ("inputs.json", vkt.File.from_data(json.dumps(worker_input, indent=2))),
            ("template_project.zip", vkt.File.from_path(ALLPLAN_WORKER_DIR / "viktor-template.prj.zip")),
            ("RebarWorker.pyp", vkt.File.from_path(ALLPLAN_WORKER_DIR / "RebarWorker.pyp")),
            ("RebarWorker.py", vkt.File.from_path(ALLPLAN_WORKER_DIR / "RebarWorker.py")),
        ]

        analysis = PythonAnalysis(
            script=vkt.File.from_path(ALLPLAN_WORKER_DIR / "run_allplan_model.py"),
            files=files,
            output_filenames=["result_project.zip", "result.json", "worker_log.txt"],
        )
        vkt.progress_message("Starting Allplan visual rebar worker.")
        analysis.execute(timeout=900)
        result_project_zip = analysis.get_output_file("result_project.zip")
        analysis.get_output_file("result.json")
        analysis.get_output_file("worker_log.txt")

        return vkt.DownloadResult(result_project_zip, f"wind_turbine_foundation_{run_id}.zip")

    @classmethod
    def _worker_input(cls, params) -> dict:
        foundation_diameter = float(params.geometry.foundation_diameter)
        pedestal_diameter = min(float(params.geometry.pedestal_diameter), foundation_diameter - 2.0 * float(params.reinforcement.cover))
        foundation_radius = foundation_diameter / 2.0
        pile_diameter = float(params.geometry.pile_diameter)
        cover = float(params.reinforcement.cover)
        max_pile_ring_radius = max(0.0, foundation_radius - pile_diameter / 2.0 - cover)
        pile_ring_radius = min(float(params.geometry.pile_ring_radius), max_pile_ring_radius)
        edge_thickness = float(params.geometry.foundation_edge_thickness)
        center_thickness = max(float(params.geometry.foundation_center_thickness), edge_thickness)

        return {
            "foundation_diameter": foundation_diameter,
            "foundation_edge_thickness": edge_thickness,
            "foundation_center_thickness": center_thickness,
            "pedestal_diameter": pedestal_diameter,
            "pedestal_height": float(params.geometry.pedestal_height),
            "pile_count": int(params.geometry.pile_count),
            "pile_ring_radius": pile_ring_radius,
            "pile_diameter": pile_diameter,
            "pile_depth": float(params.geometry.pile_depth),
            "pile_centers": cls.get_pile_centers(int(params.geometry.pile_count), pile_ring_radius),
            "cover": cover,
            "trim_clearance": float(params.reinforcement.trim_clearance),
            "top_radial_bar_diameter": float(params.reinforcement.top_radial_bar_diameter),
            "top_radial_bar_count": int(params.reinforcement.top_radial_bar_count),
            "bottom_radial_bar_diameter": float(params.reinforcement.bottom_radial_bar_diameter),
            "bottom_radial_bar_count": int(params.reinforcement.bottom_radial_bar_count),
            "ring_bar_diameter": float(params.reinforcement.ring_bar_diameter),
            "ring_spacing": float(params.reinforcement.ring_spacing),
            "pedestal_grid_bar_diameter": float(params.reinforcement.pedestal_grid_bar_diameter),
            "pedestal_grid_spacing": float(params.reinforcement.pedestal_grid_spacing),
            "pile_vertical_diameter": float(params.reinforcement.pile_vertical_diameter),
            "pile_vertical_count": int(params.reinforcement.pile_vertical_count),
            "pile_hoop_diameter": float(params.reinforcement.pile_hoop_diameter),
            "pile_hoop_spacing": float(params.reinforcement.pile_hoop_spacing),
        }

    @staticmethod
    def get_pile_centers(pile_count: int, pile_ring_radius: float) -> list[dict[str, float | str]]:
        centers = []
        for index in range(pile_count):
            angle = 2.0 * math.pi * index / pile_count
            centers.append(
                {
                    "id": f"P{index + 1}",
                    "x": pile_ring_radius * math.cos(angle),
                    "y": pile_ring_radius * math.sin(angle),
                    "angle": angle,
                }
            )
        return centers

    @classmethod
    def _bar_schedule(cls, data: dict) -> list[list[str | int | float]]:
        foundation_radius = data["foundation_diameter"] / 2.0
        pedestal_radius = data["pedestal_diameter"] / 2.0
        cover = data["cover"]
        outer_radius = max(0.0, foundation_radius - cover)
        inner_ring_radius = pedestal_radius + cover
        ring_radii = cls._radii_between(inner_ring_radius, outer_radius, data["ring_spacing"])
        ring_total = sum(2.0 * math.pi * radius for radius in ring_radii)

        top_inner_radius = max(cover, pedestal_radius * 0.35)
        top_length = cls._sloped_radial_length(data, top_inner_radius, outer_radius)
        bottom_length = max(0.0, outer_radius - cover)

        pedestal_clear_radius = max(0.0, pedestal_radius - cover)
        reduced_grid_radius = max(0.0, pedestal_clear_radius - 2.5 * data["pedestal_grid_bar_diameter"])
        pedestal_grid_x_lengths = cls._grid_bar_lengths(pedestal_clear_radius, data["pedestal_grid_spacing"])
        pedestal_grid_y_lengths = cls._grid_bar_lengths(reduced_grid_radius, data["pedestal_grid_spacing"])

        pile_hoop_count = cls._bar_count(data["pile_depth"], data["pile_hoop_spacing"])
        pile_hoop_radius = max(0.0, data["pile_diameter"] / 2.0 - cover)
        pile_hoop_length = 2.0 * math.pi * pile_hoop_radius
        pile_vertical_length = data["pile_depth"] + data["foundation_center_thickness"] - cover

        rows = [
            [
                "R1",
                "Base circular rings",
                data["ring_bar_diameter"],
                f"@ {data['ring_spacing']:.0f} mm",
                len(ring_radii),
                ring_total / len(ring_radii) if ring_radii else 0.0,
                ring_total,
            ],
            [
                "R2",
                "Bottom radial bars to center",
                data["bottom_radial_bar_diameter"],
                f"{data['bottom_radial_bar_count']} bars",
                data["bottom_radial_bar_count"],
                bottom_length,
                data["bottom_radial_bar_count"] * bottom_length,
            ],
            [
                "R3",
                "Top radial bars entering pedestal",
                data["top_radial_bar_diameter"],
                f"{data['top_radial_bar_count']} bars",
                data["top_radial_bar_count"],
                top_length,
                data["top_radial_bar_count"] * top_length,
            ],
            [
                "P1",
                "Pedestal grid, upper direction",
                data["pedestal_grid_bar_diameter"],
                f"@ {data['pedestal_grid_spacing']:.0f} mm",
                len(pedestal_grid_x_lengths),
                cls._average(pedestal_grid_x_lengths),
                sum(pedestal_grid_x_lengths),
            ],
            [
                "P2",
                "Pedestal grid, reduced lower direction",
                data["pedestal_grid_bar_diameter"],
                f"@ {data['pedestal_grid_spacing']:.0f} mm",
                len(pedestal_grid_y_lengths),
                cls._average(pedestal_grid_y_lengths),
                sum(pedestal_grid_y_lengths),
            ],
            [
                "C1",
                "Pile verticals",
                data["pile_vertical_diameter"],
                f"{data['pile_vertical_count']} per pile",
                data["pile_count"] * data["pile_vertical_count"],
                pile_vertical_length,
                data["pile_count"] * data["pile_vertical_count"] * pile_vertical_length,
            ],
            [
                "C2",
                "Pile hoops",
                data["pile_hoop_diameter"],
                f"@ {data['pile_hoop_spacing']:.0f} mm",
                data["pile_count"] * pile_hoop_count,
                pile_hoop_length,
                data["pile_count"] * pile_hoop_count * pile_hoop_length,
            ],
        ]

        return [
            [mark, element, diameter, spacing, quantity, round(unit_length / 1000.0, 2), round(total_length / 1000.0, 2)]
            for mark, element, diameter, spacing, quantity, unit_length, total_length in rows
        ]

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _bar_count(span: float, spacing: float) -> int:
        return int(span // spacing) + 1

    @classmethod
    def _build_rebar_html(cls, data: dict) -> str:
        schedule = cls._bar_schedule(data)
        total_length = sum(row[-1] for row in schedule)

        plan = cls._plan_svg(data)
        elevation = cls._section_svg(data)

        return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      margin: 0;
      background: #ffffff;
      color: #111111;
      font-family: Inter, Arial, sans-serif;
    }}
    .sheet {{
      padding: 24px;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 24px;
      margin-bottom: 16px;
      border-bottom: 1px solid #d9d9d9;
      padding-bottom: 12px;
    }}
    h1 {{
      font-size: 22px;
      font-weight: 650;
      margin: 0;
      letter-spacing: 0;
    }}
    .meta {{
      display: flex;
      gap: 20px;
      color: #333333;
      font-size: 13px;
      white-space: nowrap;
    }}
    svg {{
      width: 100%;
      max-width: 1120px;
      height: auto;
      display: block;
      background: #ffffff;
      border: 1px solid #d9d9d9;
    }}
    .caption {{
      margin-top: 10px;
      color: #444444;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="sheet">
    <div class="header">
      <h1>Wind Turbine Foundation</h1>
      <div class="meta">
        <span>Cover {data["cover"]:.0f} mm</span>
        <span>Piles {data["pile_count"]}</span>
        <span>Foundation Ø {data["foundation_diameter"]:.0f} mm</span>
        <span>Total visual length {total_length:.1f} m</span>
      </div>
    </div>
    <svg viewBox="0 0 1120 720" role="img" aria-label="Plan and section rebar sketch">
      {plan}
      {elevation}
    </svg>
    <div class="caption">Grayscale sketch is intentionally simplified. Allplan export uses visual 3D entities for concrete, piles, and rebar.</div>
  </div>
</body>
</html>
"""

    @classmethod
    def _plan_svg(cls, data: dict) -> str:
        panel_x, panel_y, panel_w = 40.0, 72.0, 500.0
        foundation_radius = data["foundation_diameter"] / 2.0
        pedestal_radius = data["pedestal_diameter"] / 2.0
        scale = min(430.0 / data["foundation_diameter"], 430.0 / data["foundation_diameter"])
        cx = panel_x + panel_w / 2.0
        cy = panel_y + 285.0
        outer_r = foundation_radius * scale
        ped_r = pedestal_radius * scale
        cover_r = max(0.0, (foundation_radius - data["cover"]) * scale)

        ring_marks = []
        ring_radii = cls._sample_positions(
            cls._radii_between(pedestal_radius + data["cover"], foundation_radius - data["cover"], data["ring_spacing"]),
            max_count=7,
        )
        for radius in ring_radii:
            ring_marks.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius * scale:.2f}" '
                f'fill="none" stroke="#969696" stroke-width="1"/>'
            )

        bottom_radials = []
        for angle in cls._sample_angles(data["bottom_radial_bar_count"], 10, phase=math.pi / data["bottom_radial_bar_count"]):
            x2 = cx + cover_r * math.cos(angle)
            y2 = cy - cover_r * math.sin(angle)
            bottom_radials.append(
                f'<line x1="{cx:.2f}" y1="{cy:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="#b7b7b7" stroke-width="1"/>'
            )

        top_radials = []
        top_inner = max(data["cover"], pedestal_radius * 0.35) * scale
        for angle in cls._sample_angles(data["top_radial_bar_count"], 16):
            x1 = cx + top_inner * math.cos(angle)
            y1 = cy - top_inner * math.sin(angle)
            x2 = cx + cover_r * math.cos(angle)
            y2 = cy - cover_r * math.sin(angle)
            top_radials.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="#575757" stroke-width="1.4"/>'
            )

        pile_marks = []
        pile_r = data["pile_diameter"] * scale / 2.0
        for pile in data["pile_centers"]:
            px = cx + pile["x"] * scale
            py = cy - pile["y"] * scale
            pile_marks.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{pile_r:.2f}" '
                f'fill="none" stroke="#686868" stroke-width="1" stroke-dasharray="6 5"/>'
            )

        pedestal_grid = cls._pedestal_grid_svg(cx, cy, pedestal_radius - data["cover"], data["pedestal_grid_spacing"], scale)

        return f"""
      <text x="{panel_x:.0f}" y="{panel_y:.0f}" font-size="16" font-weight="650" fill="#111">Plan</text>
      <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{outer_r:.2f}" fill="#fbfbfb" stroke="#1f1f1f" stroke-width="3"/>
      {''.join(ring_marks)}
      {''.join(bottom_radials)}
      {''.join(top_radials)}
      {''.join(pile_marks)}
      <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ped_r:.2f}" fill="none" stroke="#1f1f1f" stroke-width="2.4"/>
      {pedestal_grid}
      <line x1="{cx - outer_r:.2f}" y1="{cy + outer_r + 38.0:.2f}" x2="{cx + outer_r:.2f}" y2="{cy + outer_r + 38.0:.2f}" stroke="#111" stroke-width="1"/>
      <text x="{cx:.2f}" y="{cy + outer_r + 60.0:.2f}" text-anchor="middle" font-size="12" fill="#111">Ø {data["foundation_diameter"]:.0f} mm</text>
"""

    @classmethod
    def _pedestal_grid_svg(cls, cx: float, cy: float, radius: float, spacing: float, scale: float) -> str:
        marks = []
        values = cls._sample_positions(cls._positions_between(-radius, radius, spacing), max_count=5)
        for y in values:
            half = math.sqrt(max(0.0, radius * radius - y * y))
            marks.append(
                f'<line x1="{cx - half * scale:.2f}" y1="{cy - y * scale:.2f}" '
                f'x2="{cx + half * scale:.2f}" y2="{cy - y * scale:.2f}" stroke="#3d3d3d" stroke-width="1.3"/>'
            )

        reduced_radius = max(0.0, radius * 0.86)
        values = cls._sample_positions(cls._positions_between(-reduced_radius, reduced_radius, spacing), max_count=5)
        for x in values:
            half = math.sqrt(max(0.0, reduced_radius * reduced_radius - x * x))
            marks.append(
                f'<line x1="{cx + x * scale:.2f}" y1="{cy - half * scale:.2f}" '
                f'x2="{cx + x * scale:.2f}" y2="{cy + half * scale:.2f}" stroke="#646464" stroke-width="1.1"/>'
            )
        return "".join(marks)

    @classmethod
    def _section_svg(cls, data: dict) -> str:
        panel_x, panel_y = 610.0, 72.0
        foundation_radius = data["foundation_diameter"] / 2.0
        pedestal_radius = data["pedestal_diameter"] / 2.0
        edge_h = data["foundation_edge_thickness"]
        center_h = data["foundation_center_thickness"]
        pedestal_h = data["pedestal_height"]
        total_h = data["pile_depth"] + center_h + pedestal_h
        scale = min(430.0 / data["foundation_diameter"], 555.0 / total_h)
        cx = panel_x + 250.0
        base_y = panel_y + 565.0 - data["pile_depth"] * scale

        def sx(radius: float) -> float:
            return cx + radius * scale

        def sy(z: float) -> float:
            return base_y - z * scale

        concrete_points = [
            (-foundation_radius, 0.0),
            (foundation_radius, 0.0),
            (foundation_radius, edge_h),
            (pedestal_radius, center_h),
            (pedestal_radius, center_h + pedestal_h),
            (-pedestal_radius, center_h + pedestal_h),
            (-pedestal_radius, center_h),
            (-foundation_radius, edge_h),
        ]
        concrete_path = " ".join(f"{sx(x):.2f},{sy(z):.2f}" for x, z in concrete_points)

        pile_lines = []
        pile_r = data["pile_diameter"] / 2.0
        for x in [-data["pile_ring_radius"], data["pile_ring_radius"]]:
            pile_lines.append(
                f'<line x1="{sx(x - pile_r):.2f}" y1="{sy(0.0):.2f}" x2="{sx(x - pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="#6a6a6a" stroke-width="1" stroke-dasharray="6 5"/>'
            )
            pile_lines.append(
                f'<line x1="{sx(x + pile_r):.2f}" y1="{sy(0.0):.2f}" x2="{sx(x + pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="#6a6a6a" stroke-width="1" stroke-dasharray="6 5"/>'
            )

        cover = data["cover"]
        outer = foundation_radius - cover
        top_inner = max(cover, pedestal_radius * 0.35)
        bottom_y = sy(cover)
        bottom_rebar = (
            f'<line x1="{sx(-outer):.2f}" y1="{bottom_y:.2f}" x2="{sx(0.0):.2f}" y2="{bottom_y:.2f}" stroke="#949494" stroke-width="2"/>'
            f'<line x1="{sx(0.0):.2f}" y1="{bottom_y:.2f}" x2="{sx(outer):.2f}" y2="{bottom_y:.2f}" stroke="#949494" stroke-width="2"/>'
        )
        top_left = cls._section_top_polyline(data, -outer, -top_inner, scale, cx, base_y)
        top_right = cls._section_top_polyline(data, top_inner, outer, scale, cx, base_y)
        top_rebar = (
            f'<polyline points="{top_left}" fill="none" stroke="#3f3f3f" stroke-width="2"/>'
            f'<polyline points="{top_right}" fill="none" stroke="#3f3f3f" stroke-width="2"/>'
        )

        ring_dots = []
        ring_radii = cls._sample_positions(cls._radii_between(pedestal_radius + cover, outer, data["ring_spacing"]), max_count=5)
        for radius in ring_radii:
            for side in [-1.0, 1.0]:
                ring_dots.append(
                    f'<circle cx="{sx(side * radius):.2f}" cy="{bottom_y:.2f}" r="3.2" fill="#707070"/>'
                )

        grid_z = center_h + cover
        grid_half = pedestal_radius - cover
        grid_marks = [
            f'<line x1="{sx(-grid_half):.2f}" y1="{sy(grid_z):.2f}" x2="{sx(grid_half):.2f}" y2="{sy(grid_z):.2f}" stroke="#3d3d3d" stroke-width="2"/>',
            f'<line x1="{sx(-grid_half * 0.82):.2f}" y1="{sy(grid_z + data["pedestal_grid_bar_diameter"] * 1.7):.2f}" x2="{sx(grid_half * 0.82):.2f}" y2="{sy(grid_z + data["pedestal_grid_bar_diameter"] * 1.7):.2f}" stroke="#626262" stroke-width="1.6"/>',
        ]

        return f"""
      <text x="{panel_x:.0f}" y="{panel_y:.0f}" font-size="16" font-weight="650" fill="#111">Section</text>
      <polygon points="{concrete_path}" fill="#fbfbfb" stroke="#1f1f1f" stroke-width="3"/>
      {''.join(pile_lines)}
      {bottom_rebar}
      {top_rebar}
      {''.join(ring_dots)}
      {''.join(grid_marks)}
      <line x1="{sx(0.0):.2f}" y1="{sy(-data["pile_depth"]):.2f}" x2="{sx(0.0):.2f}" y2="{sy(center_h + pedestal_h):.2f}" stroke="#7e7e7e" stroke-width="1" stroke-dasharray="8 6"/>
      <text x="{sx(0.0) + 12.0:.2f}" y="{sy(center_h + pedestal_h) + 18.0:.2f}" font-size="12" fill="#333">axis</text>
"""

    @classmethod
    def _section_top_polyline(
        cls,
        data: dict,
        start_radius: float,
        end_radius: float,
        scale: float,
        cx: float,
        base_y: float,
        points_count: int = 8,
    ) -> str:
        points = []
        for index in range(points_count):
            fraction = index / (points_count - 1)
            radius = start_radius + (end_radius - start_radius) * fraction
            z = cls._foundation_top_z(data, abs(radius)) - data["cover"]
            points.append(f"{cx + radius * scale:.2f},{base_y - z * scale:.2f}")
        return " ".join(points)

    @staticmethod
    def _foundation_top_z(data: dict, radius: float) -> float:
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

    @classmethod
    def _sloped_radial_length(cls, data: dict, start_radius: float, end_radius: float) -> float:
        length = 0.0
        segments = 16
        previous = (start_radius, cls._foundation_top_z(data, start_radius) - data["cover"])
        for index in range(1, segments + 1):
            radius = start_radius + (end_radius - start_radius) * index / segments
            current = (radius, cls._foundation_top_z(data, radius) - data["cover"])
            length += math.dist(previous, current)
            previous = current
        return length

    @staticmethod
    def _grid_bar_lengths(radius: float, spacing: float) -> list[float]:
        lengths = []
        for offset in Controller._positions_between(-radius, radius, spacing):
            lengths.append(2.0 * math.sqrt(max(0.0, radius * radius - offset * offset)))
        return lengths

    @staticmethod
    def _positions_between(start: float, end: float, spacing: float) -> list[float]:
        if end < start:
            return []
        span = end - start
        count = int(span // spacing) + 1
        if count <= 1:
            return [(start + end) / 2.0]
        return [start + index * span / (count - 1) for index in range(count)]

    @staticmethod
    def _radii_between(start: float, end: float, spacing: float) -> list[float]:
        return Controller._positions_between(start, end, spacing)

    @staticmethod
    def _sample_positions(values: list[float], max_count: int = 7) -> list[float]:
        if len(values) <= max_count:
            return values

        last_index = len(values) - 1
        return [values[round(index * last_index / (max_count - 1))] for index in range(max_count)]

    @staticmethod
    def _sample_angles(count: int, max_count: int, phase: float = 0.0) -> list[float]:
        display_count = min(count, max_count)
        return [phase + 2.0 * math.pi * index / display_count for index in range(display_count)]
