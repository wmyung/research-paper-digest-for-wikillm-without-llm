import json
import subprocess
import sys
from pathlib import Path


def fixture_route() -> str:
    return """import express from "express";\nimport { authMiddleware } from "../middleware/auth";\nimport { RateLimiterMode } from "../types";\nimport { countryCheck } from "../middleware/country";\nimport { checkCreditsMiddleware } from "../middleware/credits";\nimport { wrap } from "../lib/wrap";\nimport {\n  parseController,\n  parseMultipartPayloadMiddleware,\n} from "../controllers/v2/parse";\n\nconst v2Router = express.Router();\n\nv2Router.post(\n  "/parse/upload-url",\n  authMiddleware(RateLimiterMode.Scrape, { allowKeyless: true }),\n  countryCheck,\n  wrap(parseController),\n);\n"""


def test_overlay_installer_is_idempotent(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    firecrawl = tmp_path / "firecrawl"
    route = firecrawl / "apps/api/src/routes/v2.ts"
    route.parent.mkdir(parents=True)
    route.write_text(fixture_route(), encoding="utf-8")
    (firecrawl / "docker-compose.yaml").write_text("services:\n  api: {}\n", encoding="utf-8")
    command = [sys.executable, str(root / "scripts/apply-firecrawl-overlay.py"), str(firecrawl)]
    first = subprocess.run(command, check=False, text=True, capture_output=True)
    assert first.returncode == 0, first.stdout + first.stderr
    second = subprocess.run(command, check=False, text=True, capture_output=True)
    assert second.returncode == 0, second.stdout + second.stderr
    text = route.read_text(encoding="utf-8")
    assert text.count('"/paper-digest"') == 1
    assert text.count("paperDigestController") == 2
    assert (firecrawl / "apps/paper-digest/pyproject.toml").is_file()
    assert (firecrawl / "docker-compose.paper-digest.yml").is_file()
    report = json.loads(second.stdout)
    assert str(route) in report["unchanged"]
