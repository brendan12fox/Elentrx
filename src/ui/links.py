"""Link blocks for trials — CT.gov + news at the appropriate time."""

from __future__ import annotations

import html

from src.ui.brand import ctgov_study_url


def trial_links_html(trial: dict) -> str:
    """Show CT.gov always; news headlines only when cached (full digest)."""
    nct_id = trial.get("nct_id", "")
    ctgov = ctgov_study_url(nct_id)
    news = trial.get("news") or []
    is_preview = bool(trial.get("preview"))

    ctgov_link = ""
    if ctgov:
        ctgov_link = (
            f'<a class="link-row ctgov-link" href="{html.escape(ctgov)}" '
            f'target="_blank" rel="noopener noreferrer">'
            f'<span class="link-icon">↗</span> ClinicalTrials.gov · {html.escape(nct_id)}</a>'
        )

    if news:
        items = ""
        for item in news[:3]:
            title = html.escape(str(item.get("title", "Untitled"))[:120])
            url = html.escape(str(item.get("url", "#")), quote=True)
            source = html.escape(str(item.get("source", "News")))
            date = html.escape(str(item.get("date", ""))[:10])
            meta = f"{source}" + (f" · {date}" if date else "")
            items += (
                f'<a class="link-row news-link" href="{url}" target="_blank" rel="noopener noreferrer">'
                f'<span class="link-title">{title}</span>'
                f'<span class="link-meta">{meta}</span></a>'
            )
        return (
            f'<div class="links-block">'
            f'<div class="links-label">Recent news</div>{items}{ctgov_link}</div>'
        )

    if is_preview:
        hint = "Headlines appear after the daily AI digest runs."
    else:
        hint = "No recent headlines cached for this trial."

    return (
        f'<div class="links-block">'
        f'<div class="links-label">Links</div>{ctgov_link}'
        f'<span class="link-hint">{html.escape(hint)}</span></div>'
    )


def inline_ctgov_link(nct_id: str) -> str:
    url = ctgov_study_url(nct_id)
    if not url:
        return html.escape(nct_id or "")
    return (
        f'<a class="inline-link" href="{html.escape(url)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(nct_id)} ↗</a>'
    )
