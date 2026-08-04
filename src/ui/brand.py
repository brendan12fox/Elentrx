"""Elentrx brand assets (inline SVG — no external files)."""

LOGO_SVG = """
<svg class="elentrx-logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="elx-g" x1="8" y1="4" x2="40" y2="44" gradientUnits="userSpaceOnUse">
      <stop stop-color="#5eead4"/>
      <stop offset="0.5" stop-color="#2dd4bf"/>
      <stop offset="1" stop-color="#6366f1"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="40" height="40" rx="12" fill="url(#elx-g)" opacity="0.15"/>
  <path d="M14 24c0-5.523 4.477-10 10-10s10 4.477 10 10" stroke="url(#elx-g)" stroke-width="3" stroke-linecap="round"/>
  <path d="M14 24c0 5.523 4.477 10 10 10" stroke="url(#elx-g)" stroke-width="3" stroke-linecap="round" opacity="0.55"/>
  <circle cx="24" cy="24" r="3.5" fill="url(#elx-g)"/>
  <path d="M24 10v4M24 34v4M10 24h4M34 24h4" stroke="#99f6e4" stroke-width="2" stroke-linecap="round" opacity="0.8"/>
</svg>
"""

LOGO_SVG_LIGHT = LOGO_SVG.replace('class="elentrx-logo"', 'class="elentrx-logo elentrx-logo-lg"')

BRAND_NAME = "Elentrx"
TAGLINE = "Clinical trial intelligence"
