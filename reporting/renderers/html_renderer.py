# reporting/renderers/html_renderer.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from reporting.models.report_model import ReportModel


class HtmlRenderer:
    def __init__(self, templates_dir: Path | None = None):
        if templates_dir is None:
            # Resolve templates relative to THIS file, not workspace
            templates_dir = Path(__file__).resolve().parent.parent / "templates"

        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"])
        )

    def render(self, report: ReportModel, output_path: Path):
        template = self.env.get_template("base.html")

        html = template.render(report=report)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")