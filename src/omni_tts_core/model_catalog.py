"""Model catalog HTML generator — reads catalog_info from models.yaml, produces self-contained HTML."""
from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path
from typing import Any

from omni_tts_core.config import load_yaml_config

_CATEGORY_LABELS = {
    "official-cpu": "Official",
    "official-gpu": "Official",
    "community": "Community",
    "experimental": "Thử nghiệm / Legacy",
    "multilingual": "Đa ngôn ngữ",
    "support": "Model hỗ trợ",
}

_CATEGORY_COLORS = {
    "official-cpu": "#3b82f6",
    "official-gpu": "#10b981",
    "community": "#f59e0b",
    "experimental": "#ef4444",
    "multilingual": "#8b5cf6",
    "support": "#6b7280",
}


def _stars(score: int, filled_color: str = "#facc15") -> str:
    filled = "★" * max(0, min(5, score))
    empty = "☆" * (5 - max(0, min(5, score)))
    return f'<span style="color:{filled_color}">{filled}</span><span style="color:#4b5563">{empty}</span>'


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color}22;color:{color};border:1px solid {color}66;'
        f'border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600">{text}</span>'
    )


def _hardware_tag(vram_mb: int, ram_mb: int) -> str:
    if vram_mb > 0:
        vram_str = f"{vram_mb // 1024:.1f}GB" if vram_mb >= 1024 else f"{vram_mb}MB"
        return f'<span style="color:#10b981;font-size:12px">GPU {vram_str} VRAM · {ram_mb // 1024:.1f}GB RAM</span>'
    return f'<span style="color:#94a3b8;font-size:12px">CPU only · {ram_mb // 1024:.1f}GB RAM</span>'


def _model_card(model_id: str, spec: dict[str, Any], info: dict[str, Any]) -> str:
    category = info.get("category", "")
    color = _CATEGORY_COLORS.get(category, "#6b7280")
    display_name = spec.get("display_name", model_id)
    description = info.get("description", "")
    highlight = info.get("highlight", "")
    origin = info.get("origin", "")
    variant = info.get("variant", "")
    base_model = info.get("base_model", "")
    risk = info.get("risk", "")
    source_repo = info.get("source_repo", "")
    quality = int(info.get("quality_score", 0))
    speed = int(info.get("speed_score", 0))
    vram_mb = int(info.get("vram_mb", 0))
    ram_mb = int(info.get("ram_mb", 0))
    recommend = info.get("recommend_for", "")
    install_note = info.get("install_note", "")
    hf_repo = spec.get("hf_repo", "")
    provider = spec.get("provider", "")
    lang = spec.get("language_priority", "")

    quality_html = _stars(quality) if quality > 0 else '<span style="color:#4b5563">—</span>'
    speed_html = _stars(speed, "#34d399") if speed > 0 else '<span style="color:#4b5563">—</span>'

    install_html = ""
    if install_note:
        install_html = (
            f'<div style="margin-top:8px;padding:6px 10px;background:#1e293b;border-radius:4px;'
            f'font-size:11px;color:#94a3b8;font-family:monospace">'
            f'⚙ {install_note}</div>'
        )
    detail_bits = []
    if origin:
        detail_bits.append(f"Nguồn: {origin}")
    if variant:
        detail_bits.append(f"Biến thể: {variant}")
    if base_model:
        detail_bits.append(f"Base: {base_model}")
    if source_repo:
        detail_bits.append(f"Repo: {source_repo}")
    if risk:
        detail_bits.append(f"Mức: {risk}")
    detail_html = ""
    if detail_bits:
        detail_html = (
            '<div style="font-size:11px;color:#64748b;line-height:1.5">'
            + " · ".join(detail_bits)
            + "</div>"
        )

    return f"""
    <div class="card" data-category="{category}" style="
        background:#1e293b;border:1px solid #334155;border-radius:10px;
        padding:16px;display:flex;flex-direction:column;gap:8px;
        border-left:3px solid {color}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div>
          <div style="font-weight:700;font-size:14px;color:#f1f5f9">{display_name}</div>
          <div style="font-size:11px;color:#64748b;margin-top:2px">{model_id} · {provider} · {lang}</div>
        </div>
        <div style="flex-shrink:0">{_badge(highlight, color) if highlight else ""}</div>
      </div>
      <div style="font-size:13px;color:#94a3b8;line-height:1.5">{description}</div>
      {detail_html}
      <div style="display:flex;gap:16px;font-size:12px;color:#64748b">
        <span>Chất lượng: {quality_html}</span>
        <span>Tốc độ: {speed_html}</span>
      </div>
      <div>{_hardware_tag(vram_mb, ram_mb)}</div>
      {"<div style='font-size:12px;color:#64748b'>✓ " + recommend + "</div>" if recommend else ""}
      {install_html}
      <div style="margin-top:4px">
        <a href="https://huggingface.co/{hf_repo}" target="_blank"
           style="font-size:11px;color:#3b82f6;text-decoration:none">
          🤗 {hf_repo}
        </a>
      </div>
    </div>"""


def _section(category: str, cards_html: str) -> str:
    label = _CATEGORY_LABELS.get(category, category)
    color = _CATEGORY_COLORS.get(category, "#6b7280")
    return f"""
    <div class="section" data-section="{category}">
      <h2 style="color:{color};font-size:16px;font-weight:700;margin:24px 0 12px;
                 padding-bottom:6px;border-bottom:1px solid #334155">
        {label}
      </h2>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px">
        {cards_html}
      </div>
    </div>"""


def _build_html(app_name: str, sections: str, model_count: int) -> str:
    filter_buttons = "".join(
        f'<button onclick="filter(\'{cat}\')" id="btn-{cat}" style="'
        f'background:{color}22;color:{color};border:1px solid {color}66;'
        f'border-radius:6px;padding:5px 14px;font-size:12px;font-weight:600;cursor:pointer">'
        f'{label}</button>'
        for cat, label in _CATEGORY_LABELS.items()
        for color in [_CATEGORY_COLORS.get(cat, "#6b7280")]
    )
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Model Catalog — {app_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0 }}
    body {{ background: #0f172a; color: #e2e8f0; font-family: system-ui, sans-serif; padding: 24px }}
    a {{ color: #3b82f6 }}
    button:hover {{ opacity: 0.8 }}
    .card:hover {{ border-color: #475569 !important }}
  </style>
</head>
<body>
  <div style="max-width:1200px;margin:0 auto">
    <div style="margin-bottom:24px">
      <h1 style="font-size:22px;font-weight:800;color:#f1f5f9">{app_name} — Model Catalog</h1>
      <p style="color:#64748b;font-size:13px;margin-top:4px">{model_count} models khả dụng</p>
    </div>

    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px">
      <button onclick="filter('all')" id="btn-all" style="
        background:#f1f5f922;color:#f1f5f9;border:1px solid #33415566;
        border-radius:6px;padding:5px 14px;font-size:12px;font-weight:600;cursor:pointer">
        Tất cả
      </button>
      {filter_buttons}
    </div>

    <div id="catalog">{sections}</div>
  </div>

  <script>
    function filter(cat) {{
      document.querySelectorAll('.card').forEach(el => {{
        el.style.display = (cat === 'all' || el.dataset.category === cat) ? '' : 'none';
      }});
      document.querySelectorAll('.section').forEach(el => {{
        const visible = el.querySelectorAll('.card:not([style*="none"])').length;
        el.style.display = (cat === 'all' || el.dataset.section === cat) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""


def _raw_models_data(config_path: str = "config/models.yaml") -> dict[str, tuple[dict, dict]]:
    data = load_yaml_config(config_path)
    merged: dict[str, dict] = {}
    merged.update(data.get("tts_models", {}) or {})
    merged.update(data.get("support_models", {}) or {})
    result: dict[str, tuple[dict, dict]] = {}
    for model_id, spec in merged.items():
        info = spec.get("catalog_info") or {}
        if info:
            result[model_id] = (spec, info)
    return result


def generate_catalog_html(app_name: str = "Colin TTS Local") -> str:
    models = _raw_models_data()
    by_category: dict[str, list[str]] = {cat: [] for cat in _CATEGORY_LABELS}

    for model_id, (spec, info) in models.items():
        cat = info.get("category", "support")
        by_category.setdefault(cat, []).append(
            _model_card(model_id, spec, info)
        )

    sections_html = "".join(
        _section(cat, "".join(cards))
        for cat, cards in by_category.items()
        if cards
    )
    return _build_html(app_name, sections_html, len(models))


def open_catalog(app_name: str = "Colin TTS Local") -> Path:
    html = generate_catalog_html(app_name)
    tmp = Path(tempfile.mktemp(prefix="tts_catalog_", suffix=".html"))
    tmp.write_text(html, encoding="utf-8")
    webbrowser.open(tmp.as_uri())
    return tmp
