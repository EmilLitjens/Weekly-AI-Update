"""
Weekly Battery & Energy Transition Briefing
Calls the Claude API with web search, then emails the result via Gmail SMTP.

Environment variables required (set as GitHub Actions secrets):
  ANTHROPIC_API_KEY   - your Anthropic API key
  GMAIL_ADDRESS       - the sender Gmail address
  GMAIL_APP_PASSWORD  - 16-char Gmail app password (NOT your normal password)
  RECIPIENT_EMAIL     - where the briefing should be delivered
"""

import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-6"       # Good cost/quality balance for this task
MAX_TOKENS = 4096                 # Plenty of room for a thorough briefing
MAX_SEARCHES = 12                 # Hard cap on web_search calls per run

SYSTEM_PROMPT = """You are a research analyst writing a weekly briefing for a thermal-fluid mechanical engineer running a startup that develops battery cooling systems for high-power batteries and emerging cell chemistries. The recipient is based in the Netherlands and is technically expert; do not over-explain fundamentals.

Produce a briefing structured into FOUR sections plus a TL;DR. Use the most recent week's news (prioritise items from the last 7 days; if nothing notable, expand to 2-3 weeks). Always cite sources with full URLs.

## TL;DR (top of briefing)
3-5 bullet points capturing the single most important development in each section. Each bullet: one sentence, max 25 words. This is the "if you read nothing else" summary.

## SECTION 1 - Battery Industry & Commercial Developments
Cover: gigafactory announcements, OEM/automotive partnerships, capacity scale-ups, M&A, notable product launches. Include numbers (GWh, $, timelines) where reported. Geographic spread: EU, US, China, rest of world.
Do NOT cover raw-materials markets (lithium/nickel/cobalt/graphite pricing or supply news). Skip those entirely.

## SECTION 2 - Battery Technology Watch
Sub-sections in this order of priority:
- **Thermal management & cooling** (HIGHEST PRIORITY - recipient's core expertise): cell-level cooling, immersion cooling (single-phase and two-phase dielectric), cold plates, microchannel designs, phase-change materials, BTMS for fast-charging or high-power applications, thermal runaway propagation research, new dielectric fluids, predictive thermal modeling. Cover at least 2-3 items here if anything is available.
- **Cell chemistries**: solid-state, sodium-ion, LFP advances, silicon anode, lithium-sulfur, anode-free, etc. New papers, prototypes, commercial milestones.
- **Fast-charging & high-power applications**: charging milestones, power density records, eVTOL/heavy-duty EV/grid storage with high C-rates.

## SECTION 3 - Energy Transition: Netherlands & Benelux Focus
This is a dedicated NL section. Cover:
- **Grid & congestion**: TenneT updates, transport schaarste, congestion management auctions, grid investment plans, new substations or HV upgrades
- **Policy & subsidies**: RVO schemes (SDE++, DEI+, MOOI, MIA/VAMIL), Dutch climate plan (Klimaatplan), provincial RES updates, Rijksoverheid announcements
- **Projects**: Battery storage projects (Giga Storage, S4 Energy, Eneco, Vattenfall, Return, etc.), hydrogen projects (Holland Hydrogen 1, NortH2, Djewels), North Sea wind tenders (Hollandse Kust, IJmuiden Ver, Nederwiek), heat networks
- **Industry**: Dutch battery/cleantech startups, TU Delft / TU/e / Wageningen research, Brainport / Eindhoven cluster
- **Benelux spillover**: Significant Belgian or Luxembourgish developments only if directly relevant

## SECTION 4 - Energy Transition: EU & Global Status
Cover: EU policy moves (Net Zero Industry Act, Critical Raw Materials Act, capacity markets, grid investment), member-state developments outside NL (Germany, France, Spain, Nordics most relevant), global progress vs. targets (IEA, IRENA data when available), grid storage deployment numbers, renewables capacity additions, notable transition setbacks or accelerations.

## Worth Watching (end of briefing)
2-3 specific items, events, or decisions to follow next week. One sentence each.

## Format rules
- Use Markdown formatting (## for section headings, ### for subsections, ** for bold, - for bullets)
- Each item: 2-4 sentences max. Lead with the headline fact.
- ALWAYS cite: at the end of each item, write "Source: [Publication Name](https://full-url)". One source per item.
- If you have multiple sources for one item, pick the strongest primary source.
- Bold the key numbers, company names, or technology names in each item for scannability.
- Total length: 1400-2000 words. Dense, scannable, no fluff.
- Do not invent numbers or sources. If data is unclear, say so explicitly.
- Write in clear, technical English suitable for a mechanical engineer.
"""

USER_PROMPT_TEMPLATE = """Generate this week's briefing. Today is {date}. Search for developments from the past 7-14 days.

Run targeted searches across these areas (use multiple queries, don't try to cover everything in one search):

1. Battery industry / gigafactory / OEM deals (skip raw materials pricing)
2. Battery thermal management, immersion cooling, BTMS research
3. New cell chemistry developments (solid-state, sodium-ion, LFP, silicon, etc.)
4. Fast-charging milestones and high-power battery applications
5. Netherlands energy transition: TenneT, netcongestie, RVO, SDE++, Dutch battery storage projects
6. Netherlands hydrogen and offshore wind (Hollandse Kust, NortH2, etc.)
7. EU energy transition policy and major member-state developments
8. Global energy transition status, IEA/IRENA data

Be specific in your searches. Use Dutch terms when searching for Dutch content (e.g. "netcongestie", "batterijopslag Nederland", "SDE++ 2026"). Cite all sources with full URLs."""


# ---------------------------------------------------------------------------
# Briefing generation
# ---------------------------------------------------------------------------

def generate_briefing() -> str:
    """Call Claude with the web search tool and return the briefing markdown."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = datetime.now().strftime("%A, %d %B %Y")

    print(f"[{today}] Generating briefing with {MODEL}...", flush=True)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_SEARCHES,
        }],
        messages=[{
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(date=today),
        }],
    )

    text_parts = [
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    briefing = "\n\n".join(text_parts).strip()

    usage = response.usage
    searches = getattr(usage, "server_tool_use", None)
    n_searches = getattr(searches, "web_search_requests", 0) if searches else 0
    print(
        f"Tokens: input={usage.input_tokens}, output={usage.output_tokens}, "
        f"web_searches={n_searches}",
        flush=True,
    )

    if not briefing:
        raise RuntimeError("Claude returned no text content. Full response: "
                           f"{response.model_dump()}")

    return briefing


# ---------------------------------------------------------------------------
# Email layout — improved HTML rendering
# ---------------------------------------------------------------------------

def markdown_to_html(md: str) -> str:
    """Convert briefing markdown to nicely-styled email HTML.

    Dependency-free; handles headings, bullets, bold, links. The styling
    aims for: clear hierarchy, generous spacing, readable line-length,
    professional but not boring.
    """
    import html
    import re

    lines = md.split("\n")
    out = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        # Don't escape yet — we need to handle markdown patterns first
        stripped = line.strip()

        # Headings
        if stripped.startswith("## "):
            close_list()
            text = html.escape(stripped[3:])
            out.append(f'<h2 style="color:#0b3d2e;border-bottom:2px solid #0b3d2e;'
                       f'padding-bottom:6px;margin-top:32px;margin-bottom:12px;'
                       f'font-size:20px;font-weight:600;">{text}</h2>')
            continue

        if stripped.startswith("### "):
            close_list()
            text = html.escape(stripped[4:])
            out.append(f'<h3 style="color:#1a5e44;margin-top:20px;margin-bottom:8px;'
                       f'font-size:16px;font-weight:600;">{text}</h3>')
            continue

        if stripped.startswith("# "):
            close_list()
            text = html.escape(stripped[2:])
            out.append(f'<h1 style="color:#0b3d2e;font-size:24px;font-weight:700;'
                       f'margin-top:0;margin-bottom:16px;">{text}</h1>')
            continue

        # Empty line
        if stripped == "":
            close_list()
            continue

        # Process inline formatting: bold and links, then escape what's left.
        # Strategy: escape the whole line, then convert escaped markdown back.
        escaped = html.escape(line)
        # **bold** -> <strong>
        escaped = re.sub(r"\*\*(.+?)\*\*", r'<strong style="color:#0b3d2e;">\1</strong>', escaped)
        # [text](url) — but careful, html.escape converted () to () already (no change),
        # but the brackets are still intact
        escaped = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
            r'<a href="\2" style="color:#0b6cb5;text-decoration:underline;">\1</a>',
            escaped,
        )
        # Auto-link bare URLs that weren't in markdown link form
        escaped = re.sub(
            r'(?<![">])(https?://[^\s<]+)',
            r'<a href="\1" style="color:#0b6cb5;text-decoration:underline;">\1</a>',
            escaped,
        )

        # Bullet list item
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append('<ul style="margin:8px 0 12px 0;padding-left:22px;">')
                in_list = True
            # Strip the leading bullet marker from the escaped content
            content = re.sub(r"^\s*[-*]\s+", "", escaped)
            out.append(f'<li style="margin-bottom:8px;line-height:1.55;">{content}</li>')
            continue

        # Regular paragraph
        close_list()
        out.append(f'<p style="margin:8px 0 12px 0;line-height:1.6;">{escaped}</p>')

    close_list()
    body = "\n".join(out)

    today = datetime.now().strftime("%A, %d %B %Y")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f5f5f0;font-family:-apple-system,'Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif;color:#222;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f5f5f0;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:720px;background-color:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
          <tr>
            <td style="padding:28px 32px 8px 32px;border-bottom:1px solid #e0e0d8;">
              <div style="font-size:11px;letter-spacing:1.5px;color:#7a7a6e;text-transform:uppercase;margin-bottom:4px;">Weekly Briefing</div>
              <div style="font-size:22px;font-weight:700;color:#0b3d2e;">Battery & Energy Transition</div>
              <div style="font-size:13px;color:#7a7a6e;margin-top:4px;">{today}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 32px 32px;font-size:15px;line-height:1.6;color:#222;">
{body}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px;border-top:1px solid #e0e0d8;font-size:12px;color:#7a7a6e;text-align:center;">
              Generated by Claude · sources cited inline · tweak <code style="background:#f5f5f0;padding:1px 5px;border-radius:3px;">briefing.py</code> to refocus
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def send_email(briefing_md: str) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    subject = f"Battery & Energy Briefing — {datetime.now():%d %b %Y}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(briefing_md)  # plain-text fallback
    msg.add_alternative(markdown_to_html(briefing_md), subtype="html")

    print(f"Sending email to {recipient}...", flush=True)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print("Email sent.", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    required = ["ANTHROPIC_API_KEY", "GMAIL_ADDRESS",
                "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: missing env vars: {missing}", file=sys.stderr)
        return 1

    try:
        briefing = generate_briefing()
        send_email(briefing)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
