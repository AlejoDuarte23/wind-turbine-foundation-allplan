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
    geometry.pile_depth = vkt.NumberField("Pile depth", default=12000.0, min=1000.0, suffix="mm", flex=50)

    reinforcement = vkt.Section("Reinforcement", initially_expanded=True)
    reinforcement.cover = vkt.NumberField("Concrete cover", default=75.0, min=25.0, max=200.0, suffix="mm", flex=50)
    reinforcement.use_symmetric_radial_bars = vkt.BooleanField("Use same top and bottom radial bars", default=True, flex=100)
    reinforcement.top_radial_bar_diameter = vkt.NumberField("Top radial bar diameter", default=25.0, min=8.0, suffix="mm", flex=50)
    reinforcement.top_radial_bar_count = vkt.NumberField("Top radial bar count", default=32, min=8, max=96, flex=50)
    reinforcement.bottom_radial_bar_diameter = vkt.NumberField(
        "Bottom radial bar diameter",
        default=25.0,
        min=8.0,
        suffix="mm",
        flex=50,
        visible=vkt.IsFalse(vkt.Lookup("reinforcement.use_symmetric_radial_bars")),
    )
    reinforcement.bottom_radial_bar_count = vkt.NumberField(
        "Bottom radial bar count",
        default=32,
        min=8,
        max=96,
        flex=50,
        visible=vkt.IsFalse(vkt.Lookup("reinforcement.use_symmetric_radial_bars")),
    )
    reinforcement.ring_bar_diameter = vkt.NumberField("Circular base bar diameter", default=20.0, min=8.0, suffix="mm", flex=50)
    reinforcement.ring_spacing = vkt.NumberField("Circular base bar spacing", default=550.0, min=150.0, suffix="mm", flex=50)
    reinforcement.pedestal_grid_bar_diameter = vkt.NumberField("Pedestal grid bar diameter", default=20.0, min=8.0, suffix="mm", flex=50)
    reinforcement.pedestal_grid_spacing = vkt.NumberField("Pedestal grid spacing", default=350.0, min=100.0, suffix="mm", flex=50)
    reinforcement.pedestal_tie_diameter = vkt.NumberField("Pedestal tie diameter", default=12.0, min=6.0, suffix="mm", flex=50)
    reinforcement.pedestal_tie_spacing = vkt.NumberField("Pedestal tie spacing", default=250.0, min=75.0, suffix="mm", flex=50)
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

    @vkt.GeometryView("Concrete geometry", duration_guess=1, x_axis_to_right=True)
    def visual_model(self, params, **kwargs):
        data = self._worker_input(params)
        geometry = self._geometry_model(data)
        return vkt.GeometryResult(geometry=geometry)

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
        use_symmetric_radial_bars = bool(params.reinforcement.use_symmetric_radial_bars)
        top_radial_bar_diameter = float(params.reinforcement.top_radial_bar_diameter)
        top_radial_bar_count = int(params.reinforcement.top_radial_bar_count)
        bottom_radial_bar_diameter = (
            top_radial_bar_diameter
            if use_symmetric_radial_bars
            else float(params.reinforcement.bottom_radial_bar_diameter)
        )
        bottom_radial_bar_count = (
            top_radial_bar_count
            if use_symmetric_radial_bars
            else int(params.reinforcement.bottom_radial_bar_count)
        )

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
            "use_symmetric_radial_bars": use_symmetric_radial_bars,
            "top_radial_bar_diameter": top_radial_bar_diameter,
            "top_radial_bar_count": top_radial_bar_count,
            "bottom_radial_bar_diameter": bottom_radial_bar_diameter,
            "bottom_radial_bar_count": bottom_radial_bar_count,
            "ring_bar_diameter": float(params.reinforcement.ring_bar_diameter),
            "ring_spacing": float(params.reinforcement.ring_spacing),
            "pedestal_grid_bar_diameter": float(params.reinforcement.pedestal_grid_bar_diameter),
            "pedestal_grid_spacing": float(params.reinforcement.pedestal_grid_spacing),
            "pedestal_tie_diameter": float(params.reinforcement.pedestal_tie_diameter),
            "pedestal_tie_spacing": float(params.reinforcement.pedestal_tie_spacing),
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
        top_ring_radii = cls._radii_between(top_inner_radius, outer_radius, data["ring_spacing"])
        top_ring_total = sum(2.0 * math.pi * radius for radius in top_ring_radii)
        top_slope_start_radius = min(max(pedestal_radius + cover, top_inner_radius), outer_radius)
        top_length = cls._sloped_radial_length(data, top_slope_start_radius, outer_radius) + 2.0 * cls._radial_hook_length(data["top_radial_bar_diameter"])
        bottom_length = max(0.0, outer_radius - cover) + 2.0 * cls._radial_hook_length(data["bottom_radial_bar_diameter"])

        pedestal_clear_radius = max(0.0, pedestal_radius - cover)
        pedestal_grid_x_lengths = cls._grid_bar_lengths(pedestal_clear_radius, data["pedestal_grid_spacing"])
        pedestal_grid_y_lengths = cls._grid_bar_lengths(pedestal_clear_radius, data["pedestal_grid_spacing"])
        pedestal_tie_count = cls._bar_count(data["pedestal_height"] - 2.0 * cover, data["pedestal_tie_spacing"])
        pedestal_tie_length = 2.0 * math.pi * pedestal_clear_radius

        pile_rebar_height = max(0.0, data["pile_depth"] - 2.0 * cover)
        pile_hoop_count = cls._bar_count(pile_rebar_height, data["pile_hoop_spacing"])
        pile_hoop_radius = max(0.0, data["pile_diameter"] / 2.0 - cover - data["pile_hoop_diameter"] / 2.0)
        pile_hoop_length = 2.0 * math.pi * pile_hoop_radius
        pile_vertical_length = pile_rebar_height

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
                "R4",
                "Top circular cap rings",
                data["ring_bar_diameter"],
                f"@ {data['ring_spacing']:.0f} mm",
                len(top_ring_radii),
                top_ring_total / len(top_ring_radii) if top_ring_radii else 0.0,
                top_ring_total,
            ],
            [
                "P1",
                "Pedestal grid X, top and bottom",
                data["pedestal_grid_bar_diameter"],
                f"@ {data['pedestal_grid_spacing']:.0f} mm",
                2 * len(pedestal_grid_x_lengths),
                cls._average(pedestal_grid_x_lengths),
                2.0 * sum(pedestal_grid_x_lengths),
            ],
            [
                "P2",
                "Pedestal grid Y, top and bottom",
                data["pedestal_grid_bar_diameter"],
                f"@ {data['pedestal_grid_spacing']:.0f} mm",
                2 * len(pedestal_grid_y_lengths),
                cls._average(pedestal_grid_y_lengths),
                2.0 * sum(pedestal_grid_y_lengths),
            ],
            [
                "P3",
                "Pedestal circular ties",
                data["pedestal_tie_diameter"],
                f"@ {data['pedestal_tie_spacing']:.0f} mm",
                pedestal_tie_count,
                pedestal_tie_length,
                pedestal_tie_count * pedestal_tie_length,
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
        section = cls._section_svg(data)
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
      {section}
    </svg>
    <div class="caption">Grayscale sketch uses deliberately spaced rebar markers for readability. The concrete geometry is shown in the 3D view, and the Allplan export carries the full visual reinforcement model.</div>
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

        pitch_r = data["pile_ring_radius"] * scale
        ring_marks = []
        ring_radii = cls._sample_positions(
            cls._radii_between(pedestal_radius + data["cover"], foundation_radius - data["cover"], data["ring_spacing"]),
            max_count=14,
        )
        for radius in ring_radii:
            ring_marks.append(cls._trimmed_ring_svg(cx, cy, radius, data, scale))

        bottom_radials = []
        for angle in cls._sample_angles(data["bottom_radial_bar_count"], 32, phase=math.pi / data["bottom_radial_bar_count"]):
            bottom_radials.append(
                cls._trimmed_radial_svg(
                    cx,
                    cy,
                    angle,
                    data["cover"],
                    foundation_radius - data["cover"],
                    data,
                    scale,
                    "#b7b7b7",
                    1.45,
                )
            )

        top_radials = []
        top_inner = max(data["cover"], pedestal_radius * 0.35)
        for angle in cls._sample_angles(data["top_radial_bar_count"], 44):
            top_radials.append(
                cls._trimmed_radial_svg(
                    cx,
                    cy,
                    angle,
                    top_inner,
                    foundation_radius - data["cover"],
                    data,
                    scale,
                    "#575757",
                    1.85,
                )
            )

        pile_marks = []
        pile_r = data["pile_diameter"] * scale / 2.0
        cage_r = max(0.0, (data["pile_diameter"] / 2.0 - data["cover"]) * scale)
        dot_r = max(2.7, data["pile_vertical_diameter"] * scale * 1.1)
        display_pile_bars = min(max(data["pile_vertical_count"], 8), 16)
        for pile in data["pile_centers"]:
            px = cx + pile["x"] * scale
            py = cy - pile["y"] * scale
            pile_marks.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{pile_r:.2f}" '
                f'fill="none" stroke="#686868" stroke-width="1.2" stroke-dasharray="6 5"/>'
            )
            pile_marks.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{cage_r:.2f}" '
                f'fill="none" stroke="#505050" stroke-width="1.25"/>'
            )
            for bar_index in range(display_pile_bars):
                angle = 2.0 * math.pi * bar_index / display_pile_bars
                bx = px + cage_r * math.cos(angle)
                by = py - cage_r * math.sin(angle)
                pile_marks.append(f'<circle cx="{bx:.2f}" cy="{by:.2f}" r="{dot_r:.2f}" fill="#3d3d3d"/>')

        pedestal_grid = cls._pedestal_grid_svg(cx, cy, pedestal_radius - data["cover"], data["pedestal_grid_spacing"], scale)
        pedestal_rebar = cls._pedestal_rebar_svg(cx, cy, pedestal_radius, data, scale)

        return f"""
      <text x="{panel_x:.0f}" y="{panel_y:.0f}" font-size="16" font-weight="650" fill="#111">Plan</text>
      <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{outer_r:.2f}" fill="#fbfbfb" stroke="#1f1f1f" stroke-width="3"/>
      <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{cover_r:.2f}" fill="none" stroke="#dedede" stroke-width="1" stroke-dasharray="4 5"/>
      <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{pitch_r:.2f}" fill="none" stroke="#8c8c8c" stroke-width="1" stroke-dasharray="10 7"/>
      {''.join(ring_marks)}
      {''.join(bottom_radials)}
      {''.join(top_radials)}
      {''.join(pile_marks)}
      <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ped_r:.2f}" fill="none" stroke="#1f1f1f" stroke-width="2.4"/>
      {pedestal_grid}
      {pedestal_rebar}
      <line x1="{cx - outer_r:.2f}" y1="{cy + outer_r + 38.0:.2f}" x2="{cx + outer_r:.2f}" y2="{cy + outer_r + 38.0:.2f}" stroke="#111" stroke-width="1"/>
      <text x="{cx:.2f}" y="{cy + outer_r + 60.0:.2f}" text-anchor="middle" font-size="12" fill="#111">Ø {data["foundation_diameter"]:.0f} mm</text>
"""

    @classmethod
    def _pedestal_grid_svg(cls, cx: float, cy: float, radius: float, spacing: float, scale: float) -> str:
        marks = []
        values = cls._sample_positions(cls._positions_between(-radius, radius, spacing), max_count=11)
        for y in values:
            half = math.sqrt(max(0.0, radius * radius - y * y))
            marks.append(
                f'<line x1="{cx - half * scale:.2f}" y1="{cy - y * scale:.2f}" '
                f'x2="{cx + half * scale:.2f}" y2="{cy - y * scale:.2f}" stroke="#3d3d3d" stroke-width="1.65"/>'
            )

        reduced_radius = max(0.0, radius * 0.86)
        values = cls._sample_positions(cls._positions_between(-reduced_radius, reduced_radius, spacing), max_count=11)
        for x in values:
            half = math.sqrt(max(0.0, reduced_radius * reduced_radius - x * x))
            marks.append(
                f'<line x1="{cx + x * scale:.2f}" y1="{cy - half * scale:.2f}" '
                f'x2="{cx + x * scale:.2f}" y2="{cy + half * scale:.2f}" stroke="#646464" stroke-width="1.35"/>'
            )
        return "".join(marks)

    @classmethod
    def _pedestal_rebar_svg(cls, cx: float, cy: float, pedestal_radius: float, data: dict, scale: float) -> str:
        marks = []
        clear_radius = max(0.0, pedestal_radius - data["cover"])
        dot_radius = max(2.8, data["pedestal_grid_bar_diameter"] * scale * 1.35)

        offsets = cls._sample_positions(
            cls._positions_between(-clear_radius, clear_radius, data["pedestal_grid_spacing"]),
            max_count=17,
        )
        for offset in offsets:
            half_length = math.sqrt(max(0.0, clear_radius * clear_radius - offset * offset))
            marks.append(
                f'<line x1="{cx - half_length * scale:.2f}" y1="{cy - offset * scale:.2f}" '
                f'x2="{cx + half_length * scale:.2f}" y2="{cy - offset * scale:.2f}" '
                f'stroke="#202020" stroke-width="1.5"/>'
            )
            marks.append(
                f'<line x1="{cx + offset * scale:.2f}" y1="{cy - half_length * scale:.2f}" '
                f'x2="{cx + offset * scale:.2f}" y2="{cy + half_length * scale:.2f}" '
                f'stroke="#4f4f4f" stroke-width="1.25"/>'
            )
            for x, y in [
                (cx - half_length * scale, cy - offset * scale),
                (cx + half_length * scale, cy - offset * scale),
                (cx + offset * scale, cy - half_length * scale),
                (cx + offset * scale, cy + half_length * scale),
            ]:
                marks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{dot_radius:.2f}" fill="#1f1f1f"/>')

        return "".join(marks)

    @classmethod
    def _trimmed_radial_svg(
        cls,
        cx: float,
        cy: float,
        angle: float,
        r_start: float,
        r_end: float,
        data: dict,
        scale: float,
        stroke: str,
        stroke_width: float,
    ) -> str:
        parts = []
        avoid_radius = data["pile_diameter"] / 2.0 + data["cover"]
        for start, end in cls._radial_clear_segments(angle, r_start, r_end, data, avoid_radius):
            x1 = cx + start * scale * math.cos(angle)
            y1 = cy - start * scale * math.sin(angle)
            x2 = cx + end * scale * math.cos(angle)
            y2 = cy - end * scale * math.sin(angle)
            parts.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>'
            )
        return "".join(parts)

    @classmethod
    def _trimmed_ring_svg(cls, cx: float, cy: float, radius: float, data: dict, scale: float) -> str:
        avoid_radius = data["pile_diameter"] / 2.0 + data["cover"]
        segments = cls._ring_clear_angle_segments(radius, data, avoid_radius)
        parts = []
        for start_angle, end_angle in segments:
            if end_angle - start_angle < 0.02:
                continue
            parts.append(cls._arc_svg(cx, cy, radius * scale, start_angle, end_angle, "#969696", 1.35))
        return "".join(parts)

    @staticmethod
    def _arc_svg(
        cx: float,
        cy: float,
        radius: float,
        start_angle: float,
        end_angle: float,
        stroke: str,
        stroke_width: float,
    ) -> str:
        sweep = end_angle - start_angle
        if sweep >= 2.0 * math.pi - 0.001:
            return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" fill="none" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>'

        x1 = cx + radius * math.cos(start_angle)
        y1 = cy - radius * math.sin(start_angle)
        x2 = cx + radius * math.cos(end_angle)
        y2 = cy - radius * math.sin(end_angle)
        large_arc = 1 if sweep > math.pi else 0
        return (
            f'<path d="M {x1:.2f} {y1:.2f} A {radius:.2f} {radius:.2f} 0 {large_arc} 0 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>'
        )

    @classmethod
    def _ring_clear_angle_segments(cls, radius: float, data: dict, avoid_radius: float) -> list[tuple[float, float]]:
        segments = [(0.0, 2.0 * math.pi)]
        if radius <= 0.0:
            return []

        for pile in data["pile_centers"]:
            distance = math.hypot(pile["x"], pile["y"])
            if distance <= 0.0:
                continue

            radial_gap = abs(distance - radius)
            if radial_gap >= avoid_radius:
                continue

            half_gap = math.asin(min(1.0, avoid_radius / max(radius, distance)))
            segments = cls._subtract_angle_interval(segments, pile["angle"] - half_gap, pile["angle"] + half_gap)

        return segments

    @classmethod
    def _subtract_angle_interval(
        cls,
        segments: list[tuple[float, float]],
        cut_start: float,
        cut_end: float,
    ) -> list[tuple[float, float]]:
        cuts = []
        for start, end in cls._normalize_angle_interval(cut_start, cut_end):
            cuts.append((start, end))

        remaining = segments
        for start, end in cuts:
            next_remaining = []
            for segment_start, segment_end in remaining:
                if end <= segment_start or start >= segment_end:
                    next_remaining.append((segment_start, segment_end))
                    continue
                if start > segment_start:
                    next_remaining.append((segment_start, min(start, segment_end)))
                if end < segment_end:
                    next_remaining.append((max(end, segment_start), segment_end))
            remaining = next_remaining

        return remaining

    @staticmethod
    def _normalize_angle_interval(start: float, end: float) -> list[tuple[float, float]]:
        full_turn = 2.0 * math.pi
        start = start % full_turn
        end = end % full_turn
        if start <= end:
            return [(start, end)]
        return [(start, full_turn), (0.0, end)]

    @classmethod
    def _pile_projection_svg(cls, data: dict) -> str:
        panel_x, panel_y = 610.0, 72.0
        pile_r = data["pile_diameter"] / 2.0
        pile_cage_r = max(0.0, pile_r - data["cover"])
        half_width = data["pile_ring_radius"] + pile_r
        scale = min(430.0 / max(1.0, 2.0 * half_width), 455.0 / max(1.0, data["pile_depth"]))
        cx = panel_x + 250.0
        top_y = panel_y + 115.0

        def sx(x: float) -> float:
            return cx + x * scale

        def sy(z: float) -> float:
            return top_y - z * scale

        projected_pile_lines = []
        projected_x_values = []
        for pile in sorted(data["pile_centers"], key=lambda item: item["x"]):
            if any(abs(pile["x"] - value) < data["pile_diameter"] * 0.35 for value in projected_x_values):
                continue
            projected_x_values.append(pile["x"])
            stroke = "#c9c9c9"
            width = 0.9
            dash = ' stroke-dasharray="7 7"'
            if abs(abs(pile["x"]) - data["pile_ring_radius"]) < data["pile_diameter"] * 0.15:
                stroke = "#7a7a7a"
                width = 1.2
                dash = ' stroke-dasharray="6 5"'
            projected_pile_lines.append(
                f'<line x1="{sx(pile["x"] - pile_r):.2f}" y1="{sy(0.0):.2f}" '
                f'x2="{sx(pile["x"] - pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="{stroke}" stroke-width="{width:.1f}"{dash}/>'
            )
            projected_pile_lines.append(
                f'<line x1="{sx(pile["x"] + pile_r):.2f}" y1="{sy(0.0):.2f}" '
                f'x2="{sx(pile["x"] + pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="{stroke}" stroke-width="{width:.1f}"{dash}/>'
            )

        detailed_piles = []
        hoop_count = cls._bar_count(data["pile_depth"], data["pile_hoop_spacing"])
        hoop_positions = [
            -data["pile_depth"] + cls._fraction(index, min(hoop_count, 13)) * data["pile_depth"]
            for index in range(min(hoop_count, 13))
        ]
        for x in [-data["pile_ring_radius"], data["pile_ring_radius"]]:
            detailed_piles.append(
                f'<rect x="{sx(x - pile_r):.2f}" y="{sy(0.0):.2f}" '
                f'width="{2.0 * pile_r * scale:.2f}" height="{data["pile_depth"] * scale:.2f}" '
                f'fill="none" stroke="#4f4f4f" stroke-width="1.2"/>'
            )
            for side in [-1.0, 1.0]:
                cage_x = x + side * pile_cage_r
                detailed_piles.append(
                    f'<line x1="{sx(cage_x):.2f}" y1="{sy(0.0):.2f}" '
                    f'x2="{sx(cage_x):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                    f'stroke="#2f2f2f" stroke-width="1.8"/>'
                )
            for z in hoop_positions:
                detailed_piles.append(
                    f'<line x1="{sx(x - pile_cage_r):.2f}" y1="{sy(z):.2f}" '
                    f'x2="{sx(x + pile_cage_r):.2f}" y2="{sy(z):.2f}" '
                    f'stroke="#747474" stroke-width="1.0"/>'
                )

        return f"""
      <text x="{panel_x:.0f}" y="{panel_y:.0f}" font-size="16" font-weight="650" fill="#111">Pile projection</text>
      <line x1="{sx(-half_width):.2f}" y1="{sy(0.0):.2f}" x2="{sx(half_width):.2f}" y2="{sy(0.0):.2f}" stroke="#d8d8d8" stroke-width="1"/>
      {''.join(projected_pile_lines)}
      {''.join(detailed_piles)}
      <line x1="{sx(0.0):.2f}" y1="{sy(-data["pile_depth"]):.2f}" x2="{sx(0.0):.2f}" y2="{sy(0.0):.2f}" stroke="#9a9a9a" stroke-width="1" stroke-dasharray="8 6"/>
      <text x="{sx(0.0) + 12.0:.2f}" y="{sy(0.0) + 18.0:.2f}" font-size="12" fill="#333">axis</text>
"""

    @classmethod
    def _geometry_model(cls, data: dict):
        objects = []
        concrete = vkt.Material(color=(213, 213, 208), opacity=0.62, roughness=1.0, metalness=0.0)
        pile_concrete = vkt.Material(color=(188, 188, 184), opacity=0.72, roughness=1.0, metalness=0.0)

        foundation_radius = data["foundation_diameter"] / 2.0
        pedestal_radius = data["pedestal_diameter"] / 2.0
        edge_h = data["foundation_edge_thickness"]
        center_h = data["foundation_center_thickness"]

        cls._add_concrete_cylinder(objects, foundation_radius, 0.0, edge_h, concrete, "foundation-edge-cylinder")

        slope_height = max(0.0, center_h - edge_h)
        if slope_height > 0.0 and foundation_radius > pedestal_radius:
            cls._add_concrete_frustum(
                objects=objects,
                bottom_radius=foundation_radius,
                top_radius=pedestal_radius,
                z_min=edge_h,
                height=slope_height,
                material=concrete,
                identifier="foundation-slope-frustum",
                segments=96,
            )

        cls._add_concrete_cylinder(
            objects,
            pedestal_radius,
            center_h,
            data["pedestal_height"],
            concrete,
            "pedestal-cylinder",
        )

        for index, pile in enumerate(data["pile_centers"]):
            cls._add_concrete_cylinder(
                objects,
                data["pile_diameter"] / 2.0,
                -data["pile_depth"],
                data["pile_depth"],
                pile_concrete,
                f"pile-{index}",
                center=(pile["x"], pile["y"]),
                segments=32,
            )

        return vkt.Group(objects)

    @classmethod
    def _add_concrete_cylinder(
        cls,
        objects: list,
        radius: float,
        z_min: float,
        height: float,
        material,
        identifier: str,
        center: tuple[float, float] = (0.0, 0.0),
        segments: int = 72,
    ) -> None:
        if radius <= 0.0 or height <= 0.0:
            return

        line = vkt.Line(vkt.Point(center[0], center[1], z_min), vkt.Point(center[0], center[1], z_min + height))
        objects.append(vkt.Extrusion(cls._circle_profile(radius, segments), line, material=material, identifier=identifier))

    @classmethod
    def _add_concrete_frustum(
        cls,
        objects: list,
        bottom_radius: float,
        top_radius: float,
        z_min: float,
        height: float,
        material,
        identifier: str,
        center: tuple[float, float] = (0.0, 0.0),
        segments: int = 96,
    ) -> None:
        if bottom_radius <= 0.0 or top_radius <= 0.0 or height <= 0.0:
            return

        cx, cy = center
        z_bottom = z_min
        z_top = z_min + height

        bottom_center = vkt.Point(cx, cy, z_bottom)
        top_center = vkt.Point(cx, cy, z_top)

        bottom_points = []
        top_points = []

        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            bottom_points.append(
                vkt.Point(
                    cx + bottom_radius * cos_a,
                    cy + bottom_radius * sin_a,
                    z_bottom,
                )
            )
            top_points.append(
                vkt.Point(
                    cx + top_radius * cos_a,
                    cy + top_radius * sin_a,
                    z_top,
                )
            )

        triangles = []

        for index in range(segments):
            next_index = (index + 1) % segments

            b0 = bottom_points[index]
            b1 = bottom_points[next_index]
            t0 = top_points[index]
            t1 = top_points[next_index]

            triangles.append(vkt.Triangle(b0, b1, t1))
            triangles.append(vkt.Triangle(b0, t1, t0))

            triangles.append(vkt.Triangle(bottom_center, b1, b0))
            triangles.append(vkt.Triangle(top_center, t0, t1))

        try:
            objects.append(
                vkt.TriangleAssembly(
                    triangles,
                    material=material,
                    skip_duplicate_vertices_check=True,
                    identifier=identifier,
                )
            )
        except TypeError:
            objects.append(
                vkt.TriangleAssembly(
                    triangles,
                    material=material,
                    skip_duplicate_vertices_check=True,
                )
            )

    @staticmethod
    def _circle_profile(radius: float, segments: int) -> list:
        points = [
            vkt.Point(radius * math.cos(2.0 * math.pi * index / segments), radius * math.sin(2.0 * math.pi * index / segments), 0.0)
            for index in range(segments)
        ]
        points.append(vkt.Point(radius, 0.0, 0.0))
        return points

    @classmethod
    def _add_pedestal_geometry(cls, objects: list, data: dict, steel, secondary_steel) -> None:
        pedestal_radius = data["pedestal_diameter"] / 2.0
        clear_radius = max(0.0, pedestal_radius - data["cover"])
        z_bottom = data["foundation_center_thickness"] + data["cover"]
        z_top = data["foundation_center_thickness"] + data["pedestal_height"] - data["cover"]
        frame_size = cls._visual_bar_size(data["pedestal_grid_bar_diameter"], multiplier=4.0, minimum=70.0)
        tie_size = cls._visual_bar_size(data["pedestal_tie_diameter"], multiplier=4.0, minimum=55.0)

        offsets = cls._sample_positions(
            cls._positions_between(-clear_radius, clear_radius, data["pedestal_grid_spacing"]),
            max_count=13,
        )
        for index, x in enumerate(offsets):
            y_half = math.sqrt(max(0.0, clear_radius * clear_radius - x * x))
            cls._add_vertical_rect_y(objects, x, -y_half, y_half, z_bottom, z_top, frame_size, steel, f"ped-y-frame-{index}")

        for index, y in enumerate(offsets):
            x_half = math.sqrt(max(0.0, clear_radius * clear_radius - y * y))
            cls._add_vertical_rect_x(objects, -x_half, x_half, y, z_bottom, z_top, frame_size, steel, f"ped-x-frame-{index}")

        tie_positions = cls._sample_positions(
            cls._positions_between(z_bottom, z_top, data["pedestal_tie_spacing"]),
            max_count=10,
        )
        for index, z in enumerate(tie_positions):
            cls._add_geometry_ring(objects, clear_radius, z, tie_size, secondary_steel, 36, f"pedestal-tie-{index}")

    @classmethod
    def _add_pile_geometry(cls, objects: list, data: dict, steel, light_steel) -> None:
        pile_vertical_axis_radius = max(
            0.0,
            data["pile_diameter"] / 2.0 - data["cover"] - data["pile_vertical_diameter"] / 2.0,
        )
        pile_hoop_axis_radius = max(
            0.0,
            data["pile_diameter"] / 2.0 - data["cover"] - data["pile_hoop_diameter"] / 2.0,
        )
        if pile_vertical_axis_radius <= 0.0 or pile_hoop_axis_radius <= 0.0:
            return

        vertical_size = cls._visual_bar_size(data["pile_vertical_diameter"], multiplier=3.5, minimum=50.0)
        hoop_size = cls._visual_bar_size(data["pile_hoop_diameter"], multiplier=3.5, minimum=45.0)
        vertical_count = min(max(data["pile_vertical_count"], 4), 8)
        z_bottom = -data["pile_depth"] + data["cover"]
        z_top = -data["cover"]
        hoop_positions = cls._sample_positions(
            cls._positions_between(z_bottom, z_top, data["pile_hoop_spacing"]),
            max_count=4,
        )

        for pile_index, pile in enumerate(data["pile_centers"]):
            cx = pile["x"]
            cy = pile["y"]
            for bar_index in range(vertical_count):
                angle = 2.0 * math.pi * bar_index / vertical_count
                x = cx + pile_vertical_axis_radius * math.cos(angle)
                y = cy + pile_vertical_axis_radius * math.sin(angle)
                cls._add_geometry_bar(
                    objects,
                    (x, y, z_bottom),
                    (x, y, z_top),
                    vertical_size,
                    steel,
                    f"pile-{pile_index}-vertical-{bar_index}",
                )
            for hoop_index, z in enumerate(hoop_positions):
                cls._add_geometry_ring(
                    objects,
                    pile_hoop_axis_radius,
                    z,
                    hoop_size,
                    light_steel,
                    16,
                    f"pile-{pile_index}-hoop-{hoop_index}",
                    center=(cx, cy),
                )

    @staticmethod
    def _visual_bar_size(diameter: float, multiplier: float = 3.2, minimum: float = 50.0, maximum: float = 120.0) -> float:
        return min(maximum, max(minimum, diameter * multiplier))

    @classmethod
    def _add_vertical_rect_y(
        cls,
        objects: list,
        x: float,
        y_min: float,
        y_max: float,
        z_bottom: float,
        z_top: float,
        size: float,
        material,
        identifier: str,
    ) -> None:
        cls._add_geometry_bar(objects, (x, y_min, z_bottom), (x, y_max, z_bottom), size, material, f"{identifier}-bottom")
        cls._add_geometry_bar(objects, (x, y_min, z_top), (x, y_max, z_top), size, material, f"{identifier}-top")
        cls._add_geometry_bar(objects, (x, y_min, z_bottom), (x, y_min, z_top), size, material, f"{identifier}-side-a")
        cls._add_geometry_bar(objects, (x, y_max, z_bottom), (x, y_max, z_top), size, material, f"{identifier}-side-b")

    @classmethod
    def _add_vertical_rect_x(
        cls,
        objects: list,
        x_min: float,
        x_max: float,
        y: float,
        z_bottom: float,
        z_top: float,
        size: float,
        material,
        identifier: str,
    ) -> None:
        cls._add_geometry_bar(objects, (x_min, y, z_bottom), (x_max, y, z_bottom), size, material, f"{identifier}-bottom")
        cls._add_geometry_bar(objects, (x_min, y, z_top), (x_max, y, z_top), size, material, f"{identifier}-top")
        cls._add_geometry_bar(objects, (x_min, y, z_bottom), (x_min, y, z_top), size, material, f"{identifier}-side-a")
        cls._add_geometry_bar(objects, (x_max, y, z_bottom), (x_max, y, z_top), size, material, f"{identifier}-side-b")

    @classmethod
    def _add_geometry_ring(
        cls,
        objects: list,
        radius: float,
        z: float,
        size: float,
        material,
        segments: int,
        identifier: str,
        center: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        if radius <= 0.0:
            return

        cx, cy = center
        for index in range(segments):
            start_angle = 2.0 * math.pi * index / segments
            end_angle = 2.0 * math.pi * (index + 1) / segments
            start = (cx + radius * math.cos(start_angle), cy + radius * math.sin(start_angle), z)
            end = (cx + radius * math.cos(end_angle), cy + radius * math.sin(end_angle), z)
            cls._add_geometry_bar(objects, start, end, size, material, f"{identifier}-{index}")

    @staticmethod
    def _add_geometry_bar(
        objects: list,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        size: float,
        material,
        identifier: str,
    ) -> None:
        if math.dist(start, end) < 1.0:
            return

        line = vkt.Line(vkt.Point(start[0], start[1], start[2]), vkt.Point(end[0], end[1], end[2]))
        objects.append(vkt.RectangularExtrusion(size, size, line, material=material, identifier=identifier))

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

        pile_r = data["pile_diameter"] / 2.0
        projected_pile_lines = []
        projected_x_values = []
        for pile in data["pile_centers"]:
            if abs(abs(pile["x"]) - data["pile_ring_radius"]) < 1.0 and abs(pile["y"]) < 1.0:
                continue
            if any(abs(pile["x"] - value) < data["pile_diameter"] * 0.25 for value in projected_x_values):
                continue
            projected_x_values.append(pile["x"])
            projected_pile_lines.append(
                f'<line x1="{sx(pile["x"] - pile_r):.2f}" y1="{sy(0.0):.2f}" '
                f'x2="{sx(pile["x"] - pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="#dedede" stroke-width="0.65" stroke-dasharray="5 8"/>'
            )
            projected_pile_lines.append(
                f'<line x1="{sx(pile["x"] + pile_r):.2f}" y1="{sy(0.0):.2f}" '
                f'x2="{sx(pile["x"] + pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="#dedede" stroke-width="0.65" stroke-dasharray="5 8"/>'
            )

        pile_lines = []
        pile_vertical_axis_r = max(0.0, pile_r - data["cover"] - data["pile_vertical_diameter"] / 2.0)
        pile_hoop_axis_r = max(0.0, pile_r - data["cover"] - data["pile_hoop_diameter"] / 2.0)
        pile_rebar_bottom_z = -data["pile_depth"] + data["cover"]
        pile_rebar_top_z = -data["cover"]
        pile_rebar_height = max(0.0, pile_rebar_top_z - pile_rebar_bottom_z)
        hoop_count = cls._bar_count(pile_rebar_height, data["pile_hoop_spacing"])
        for x in [-data["pile_ring_radius"], data["pile_ring_radius"]]:
            pile_lines.append(
                f'<line x1="{sx(x - pile_r):.2f}" y1="{sy(0.0):.2f}" x2="{sx(x - pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="#6a6a6a" stroke-width="1" stroke-dasharray="6 5"/>'
            )
            pile_lines.append(
                f'<line x1="{sx(x + pile_r):.2f}" y1="{sy(0.0):.2f}" x2="{sx(x + pile_r):.2f}" y2="{sy(-data["pile_depth"]):.2f}" '
                f'stroke="#6a6a6a" stroke-width="1" stroke-dasharray="6 5"/>'
            )
            for side in [-1.0, 1.0]:
                cage_x = x + side * pile_vertical_axis_r
                pile_lines.append(
                    f'<line x1="{sx(cage_x):.2f}" y1="{sy(pile_rebar_top_z):.2f}" '
                    f'x2="{sx(cage_x):.2f}" y2="{sy(pile_rebar_bottom_z):.2f}" '
                    f'stroke="#3f3f3f" stroke-width="1.4"/>'
                )
            for hoop_index in range(min(hoop_count, 10)):
                fraction = cls._fraction(hoop_index, min(hoop_count, 10))
                z = pile_rebar_bottom_z + fraction * pile_rebar_height
                pile_lines.append(
                    f'<line x1="{sx(x - pile_hoop_axis_r):.2f}" y1="{sy(z):.2f}" '
                    f'x2="{sx(x + pile_hoop_axis_r):.2f}" y2="{sy(z):.2f}" '
                    f'stroke="#8a8a8a" stroke-width="0.9"/>'
                )

        cover = data["cover"]
        outer = foundation_radius - cover
        top_inner = max(cover, pedestal_radius * 0.35)
        top_slope_start = min(max(pedestal_radius + cover, top_inner), outer)
        top_slope_start_z = cls._foundation_top_z(data, top_slope_start) - cover
        bottom_hook_length = cls._radial_hook_length(data["bottom_radial_bar_diameter"])
        top_hook_length = cls._radial_hook_length(data["top_radial_bar_diameter"])
        bottom_y = sy(cover)
        bottom_hook_top_y = sy(cover + bottom_hook_length)
        bottom_rebar = (
            f'<line x1="{sx(-outer):.2f}" y1="{bottom_y:.2f}" x2="{sx(-cover):.2f}" y2="{bottom_y:.2f}" stroke="#777777" stroke-width="2.1"/>'
            f'<line x1="{sx(cover):.2f}" y1="{bottom_y:.2f}" x2="{sx(outer):.2f}" y2="{bottom_y:.2f}" stroke="#777777" stroke-width="2.1"/>'
            f'<line x1="{sx(-outer):.2f}" y1="{bottom_y:.2f}" x2="{sx(-outer):.2f}" y2="{bottom_hook_top_y:.2f}" stroke="#777777" stroke-width="2.1"/>'
            f'<line x1="{sx(-cover):.2f}" y1="{bottom_y:.2f}" x2="{sx(-cover):.2f}" y2="{bottom_hook_top_y:.2f}" stroke="#777777" stroke-width="2.1"/>'
            f'<line x1="{sx(cover):.2f}" y1="{bottom_y:.2f}" x2="{sx(cover):.2f}" y2="{bottom_hook_top_y:.2f}" stroke="#777777" stroke-width="2.1"/>'
            f'<line x1="{sx(outer):.2f}" y1="{bottom_y:.2f}" x2="{sx(outer):.2f}" y2="{bottom_hook_top_y:.2f}" stroke="#777777" stroke-width="2.1"/>'
        )
        top_left = cls._section_top_polyline(data, -outer, -top_slope_start, scale, cx, base_y)
        top_right = cls._section_top_polyline(data, top_slope_start, outer, scale, cx, base_y)
        top_outer_z = cls._foundation_top_z(data, outer) - cover
        top_hook_bottom_y = sy(top_slope_start_z - top_hook_length)
        top_outer_hook_bottom_y = sy(top_outer_z - top_hook_length)
        top_rebar = (
            f'<polyline points="{top_left}" fill="none" stroke="#3f3f3f" stroke-width="2.1"/>'
            f'<polyline points="{top_right}" fill="none" stroke="#3f3f3f" stroke-width="2.1"/>'
            f'<line x1="{sx(-outer):.2f}" y1="{sy(top_outer_z):.2f}" x2="{sx(-outer):.2f}" y2="{top_outer_hook_bottom_y:.2f}" stroke="#3f3f3f" stroke-width="2.1"/>'
            f'<line x1="{sx(-top_slope_start):.2f}" y1="{sy(top_slope_start_z):.2f}" x2="{sx(-top_slope_start):.2f}" y2="{top_hook_bottom_y:.2f}" stroke="#3f3f3f" stroke-width="2.1"/>'
            f'<line x1="{sx(top_slope_start):.2f}" y1="{sy(top_slope_start_z):.2f}" x2="{sx(top_slope_start):.2f}" y2="{top_hook_bottom_y:.2f}" stroke="#3f3f3f" stroke-width="2.1"/>'
            f'<line x1="{sx(outer):.2f}" y1="{sy(top_outer_z):.2f}" x2="{sx(outer):.2f}" y2="{top_outer_hook_bottom_y:.2f}" stroke="#3f3f3f" stroke-width="2.1"/>'
        )

        section_rebar_marks = []
        slope_gap = max(300.0, data["pile_diameter"] * 0.35)
        for x_offset in cls._equal_values(-outer, -(pedestal_radius + slope_gap), 8):
            top_z = cls._foundation_top_z(data, abs(x_offset)) - cover
            section_rebar_marks.append(cls._section_drop_line(sx(x_offset), sy(top_z), bottom_y))
            section_rebar_marks.append(cls._section_dot(sx(x_offset), sy(top_z), 2.85, "#4d4d4d"))
        for x_offset in cls._equal_values(pedestal_radius + slope_gap, outer, 8):
            top_z = cls._foundation_top_z(data, abs(x_offset)) - cover
            section_rebar_marks.append(cls._section_drop_line(sx(x_offset), sy(top_z), bottom_y))
            section_rebar_marks.append(cls._section_dot(sx(x_offset), sy(top_z), 2.85, "#4d4d4d"))

        bottom_dots = []
        for x_offset in cls._equal_values(-outer, outer, 21):
            bottom_dots.append(cls._section_dot(sx(x_offset), bottom_y, 2.75, "#6f6f6f"))

        pedestal_section_rebar = []
        grid_half = pedestal_radius - cover
        grid_bottom_z = center_h + cover
        grid_top_z = center_h + pedestal_h - cover
        dot_radius = 3.05
        pedestal_section_rebar.append(
            f'<rect x="{sx(-grid_half):.2f}" y="{sy(grid_top_z):.2f}" '
            f'width="{2.0 * grid_half * scale:.2f}" height="{(grid_top_z - grid_bottom_z) * scale:.2f}" '
            f'fill="none" stroke="#2f2f2f" stroke-width="1.5"/>'
        )
        tie_positions = cls._equal_values(grid_bottom_z + data["pedestal_tie_spacing"] * 0.5, grid_top_z - data["pedestal_tie_spacing"] * 0.5, 5)
        for z in tie_positions:
            pedestal_section_rebar.append(
                f'<line x1="{sx(-grid_half):.2f}" y1="{sy(z):.2f}" '
                f'x2="{sx(grid_half):.2f}" y2="{sy(z):.2f}" '
                f'stroke="#777777" stroke-width="0.85" stroke-dasharray="7 5"/>'
            )
        section_bar_positions = cls._equal_values(-grid_half + 160.0, grid_half - 160.0, 10)
        for x_offset in section_bar_positions:
            for z in [grid_top_z, grid_bottom_z]:
                pedestal_section_rebar.append(cls._section_dot(sx(x_offset), sy(z), dot_radius, "#4d4d4d", stroke="#222222"))

        return f"""
      <text x="{panel_x:.0f}" y="{panel_y:.0f}" font-size="16" font-weight="650" fill="#111">Section</text>
      <polygon points="{concrete_path}" fill="#fbfbfb" stroke="#1f1f1f" stroke-width="3"/>
      {''.join(projected_pile_lines)}
      {''.join(pile_lines)}
      {''.join(section_rebar_marks)}
      {bottom_rebar}
      {top_rebar}
      {''.join(bottom_dots)}
      {''.join(pedestal_section_rebar)}
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
    def _section_dot(x: float, y: float, radius: float, fill: str, stroke: str | None = None) -> str:
        stroke_part = f' stroke="{stroke}" stroke-width="0.65"' if stroke else ""
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{fill}"{stroke_part}/>'

    @staticmethod
    def _section_drop_line(x: float, y_top: float, y_bottom: float) -> str:
        return (
            f'<line x1="{x:.2f}" y1="{y_top:.2f}" x2="{x:.2f}" y2="{y_bottom:.2f}" '
            f'stroke="#c7c7c7" stroke-width="0.65"/>'
        )

    @staticmethod
    def _equal_values(start: float, end: float, count: int) -> list[float]:
        if count <= 1:
            return [(start + end) / 2.0]
        return [start + (end - start) * index / (count - 1) for index in range(count)]

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
    def _radial_hook_length(diameter: float) -> float:
        return max(12.0 * diameter, 100.0)

    @staticmethod
    def _grid_bar_lengths(radius: float, spacing: float) -> list[float]:
        lengths = []
        for offset in Controller._positions_between(-radius, radius, spacing):
            lengths.append(2.0 * math.sqrt(max(0.0, radius * radius - offset * offset)))
        return lengths

    @classmethod
    def _radial_clear_segments(
        cls,
        angle: float,
        r_start: float,
        r_end: float,
        data: dict,
        avoid_radius: float,
    ) -> list[tuple[float, float]]:
        segments = [(r_start, r_end)]
        pile_ring_radius = data["pile_ring_radius"]

        for pile in data["pile_centers"]:
            delta = cls._normalize_signed_angle(angle - pile["angle"])
            distance_to_ray = abs(pile_ring_radius * math.sin(delta))
            projection = pile_ring_radius * math.cos(delta)

            if distance_to_ray >= avoid_radius or projection <= r_start or projection >= r_end:
                continue

            half_gap = math.sqrt(max(0.0, avoid_radius * avoid_radius - distance_to_ray * distance_to_ray))
            segments = cls._subtract_interval(segments, projection - half_gap, projection + half_gap)

        return segments

    @staticmethod
    def _subtract_interval(segments: list[tuple[float, float]], cut_start: float, cut_end: float) -> list[tuple[float, float]]:
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

    @staticmethod
    def _normalize_signed_angle(angle: float) -> float:
        while angle <= -math.pi:
            angle += 2.0 * math.pi
        while angle > math.pi:
            angle -= 2.0 * math.pi
        return angle

    @staticmethod
    def _fraction(index: int, count: int) -> float:
        return index / (count - 1) if count > 1 else 0.5

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
