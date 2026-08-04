"""Link blocks for trials — CT.gov + news at the appropriate time."""

from __future__ import annotations

import html

from src.ui.brand import ctgov_study_url

_LINKS_BLOCK = "border-top:1px solid #dce4ec;padding-top:0.75rem;margin-top:0.75rem;"
_LINK_ROW = (
    "display:block;font-size:0.78rem;color:#001d3d;text-decoration:none;"
    "padding:0.55rem 0.65rem;line-height:1.45;border:1px solid #eef2f6;"
    "border-radius:10px;margin-bottom:0.45rem;background:#ffffff;"
)


def trial_links_html(trial: dict) -> str:
    """Show CT.gov always; news headlines only when cached (full digest)."""
    nct_id = trial.get("nct_id", "")
    ctgov = ctgov_study_url(nct_id)
    news = trial.get("news") or []
    is_preview = bool(trial.get("preview"))

    ctgov_link = ""
    if ctgov:
        ctgov_link = (
            f'<a class="link-row ctgov-link" style="{_LINK_ROW}" href="{html.escape(ctgov)}" '
            f'target="_blank" rel="noopener noreferrer">'
            f'<span class="link-icon">↗</span> ClinicalTrials.gov · {html.escape(nct_id)}</a>'
        )

    if news:
        items = ""
        for item in news[:2]:
            title = html.escape(str(item.get("title", "Untitled"))[:100])
            url = html.escape(str(item.get("url", "#")), quote=True)
            source = html.escape(str(item.get("source", "News")))
            date = html.escape(str(item.get("date", ""))[:10])
            meta = f"{source}" + (f" · {date}" if date else "")
            items += (
                f'<a class="link-row news-link" style="{_LINK_ROW}" href="{url}" '
                f'target="_blank" rel="noopener noreferrer">'
                f'<span class="link-title" style="display:block;font-weight:600;">{title}</span>'
                f'<span class="link-meta" style="color:#94a3b8;font-size:0.7rem;">{meta}</span></a>'
            )
        more = ""
        if len(news) > 2:
            more = f'<span class="link-hint" style="color:#94a3b8;font-size:0.7rem;">+{len(news) - 2} more headlines</span>'
        return (
            f'<div class="links-block" style="{_LINKS_BLOCK}">'
            f'<div class="links-label" style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.08em;color:#4a6278;margin-bottom:0.45rem;">Recent news</div>'
            f'{items}{more}{ctgov_link}</div>'
        )

    if is_preview:
        hint = "Headlines appear after the daily AI digest runs."
    else:
        hint = "No recent headlines cached for this trial."

    return (
        f'<div class="links-block" style="{_LINKS_BLOCK}">'
        f'<div class="links-label" style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.08em;color:#4a6278;margin-bottom:0.45rem;">Links</div>'
        f'{ctgov_link}'
        f'<span class="link-hint" style="display:block;margin-top:0.35rem;color:#94a3b8;font-size:0.7rem;">'
        f'{html.escape(hint)}</span></div>'
    )


def inline_ctgov_link(nct_id: str) -> str:
    url = ctgov_study_url(nct_id)
    if not url:
        return html.escape(nct_id or "")
    return (
        f'<a class="inline-link" href="{html.escape(url)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(nct_id)} ↗</a>'
    )
