"""RES-001: dashboard inline handlers must not interpolate raw identifiers.

encodeURIComponent leaves ' ( ) unencoded, so a crafted channel_id/URL broke
out of the single-quoted handler and executed on operator click. Identifiers
now travel via inlineArg() (JSON-stringified + HTML-escaped).
"""
import re
import subprocess
from pathlib import Path


def _template():
    return (Path(__file__).resolve().parents[2] / "templates" / "gui.html").read_text(
        encoding="utf-8"
    )


def test_no_raw_identifier_in_inline_handlers():
    content = _template()
    assert "encodeURIComponent(identifier)" not in content
    assert "${deleteId}" not in content
    assert "decodeURIComponent(encodedIdentifier)" not in content
    assert "togglePodcast(${safeIdentifier}, this)" in content
    assert "deleteSource(${safeIdentifier})" in content


def test_inline_arg_neutralizes_breakout():
    node_script = """
    const fs = require('fs');
    const html = fs.readFileSync('./desktop/templates/gui.html', 'utf8');
    function extract(name) {
      const start = html.indexOf('function ' + name + '(');
      if (start < 0) throw new Error('missing ' + name);
      const end = html.indexOf('\\n        }', start);
      if (end < 0) throw new Error('unterminated ' + name);
      return html.slice(start, end + '\\n        }'.length);
    }
    eval(extract('escapeHtml') + '\\n' + extract('inlineArg'));
    const armed = inlineArg("x');alert(1);//");
    if (armed !== '&quot;x&#39;);alert(1);//&quot;') {
      throw new Error('inlineArg breakout wrong: ' + armed);
    }
    const stripped = armed.replace(/&(quot|#39|amp|lt|gt);/g, '');
    if (stripped.includes("'") || stripped.includes('"')) {
      throw new Error('raw quote survived: ' + armed);
    }
    process.stdout.write('OK_GUI_INLINEARG');
    """
    res = subprocess.run(
        ["node", "-e", node_script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node gui.html probe failed: {res.stderr}"
    assert "OK_GUI_INLINEARG" in res.stdout


def test_all_dynamic_handlers_use_safe_arg_helpers():
    """Every onclick/onchange carrying source data must use an escape helper."""
    content = _template()
    # Pre-sanitized variables (each assigned from an escape helper elsewhere).
    assert "const safeIdentifier = inlineArg(identifier);" in content
    allowed_bare = {"safeIdentifier"}
    # Both quote styles: a single-quoted handler must never slip past the scan.
    handlers = (
        re.findall(r"on(?:click|change)=\"([^\"]+)\"", content)
        + re.findall(r"on(?:click|change)='([^']+)'", content)
    )
    assert handlers, "handler scan found nothing — the template changed shape"
    for handler in handlers:
        exprs = re.findall(r"\$\{([^}]+)\}", handler)
        if not exprs:
            continue
        for expr in exprs:
            expr = expr.strip()
            assert (
                "inlineArg(" in expr or "escapeHtml(" in expr or expr in allowed_bare
            ), f"{handler[:100]} :: ${{{expr}}}"
