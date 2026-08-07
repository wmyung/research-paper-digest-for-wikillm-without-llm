import json
import subprocess
from pathlib import Path


def test_typescript_controller_transpiles_without_syntax_diagnostics():
    root = Path(__file__).resolve().parents[1]
    path = root / "overlay/apps/api/src/controllers/v2/paper-digest.ts"
    script = r"""
const fs = require("fs");
const ts = require("typescript");
const source = fs.readFileSync(process.argv[1], "utf8");
const result = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
    esModuleInterop: true,
    strict: true,
  },
  reportDiagnostics: true,
  fileName: process.argv[1],
});
const errors = (result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).map(d => ts.flattenDiagnosticMessageText(d.messageText, "\n"));
console.log(JSON.stringify({errors}));
process.exit(errors.length ? 1 : 0);
"""
    completed = subprocess.run(["node", "-e", script, str(path)], text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["errors"] == []
