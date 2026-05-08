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
MAX_SEARCHES = 10                 # Hard cap on web_search calls per run

SYSTEM_PROMPT = """You are a research analyst writing a weekly briefing for a thermal-fluid mechanical engineer running a startup that develops battery cooling systems for high-power batteries and emerging cell chemistries. The recipient is technically expert; do not over-explain fundamentals.

Produce a briefing structured into THREE sections. Use the most recent week's news (prioritise items from the last 7 days; if nothing notable, expand to 2-3 weeks). Always cite sources with full URLs.

## SECTION 1 - Battery Industry & Commercial Developments
Cover: gigafactory announcements, OEM/automotive partnerships, capacity scale-ups, M&A, notable product launches, supply chain shifts (lithium, nickel, cobalt, graphite). Include numbers (GWh, $, timelines) where reported. Geographic spread: EU, US, China, rest of world.

## SECTION 2 - Battery Technology Watch (most relevant to the recipient)
Sub-sections:
- **Cell chemistries**: solid-state, sodium-ion, LFP advances, silicon anode, lithium-sulfur, anode-free, etc. New papers, prototypes, commercial milestones.
- **Thermal management & cooling**: anything on cell-level cooling, immersion cooling, cold plates, phase-change materials, BTMS for fast-charging or high-power applications, thermal runaway propagation research. This is the recipient's core expertise - prioritise this.
- **Fast-charging & high-power applications**: charging milestones, power density records, relevant to high-power use cases (eVTOL, heavy-duty EV, grid storage with high C-rates).

## SECTION 3 - Energy Transition Status (EU + Global)
Cover: EU policy moves (Net Zero Industry Act, Critical Raw Materials Act, grid investment, capacity auctions), member-state developments, global progress vs. targets (IEA, IRENA data when available), grid storage deployment numbers, renewables capacity additions, notable transition setbacks or accelerations. Frame around what a thermal-fluid energy engineer should know.

## Format rules
- Lead each section with a 1-2 line "this week's headline" if there is one.
- Use bullet points; keep each item to 2-4 sentences.
- ALWAYS cite: include the publication name and full URL inline.
- End with a "Worth Watching" section: 2-3 items to follow next week.
- Total length: aim for 1200-1800 words. Dense, scannable, no fluff.
- Do not invent numbers or sources. If data is unclear, say so.
"""

USER_PROMPT_TEMPLATE = """Generate this week's briefing. Today is {date}. Search for developments from the past 7-14 days. Focus searches on:

1. Battery industry news (gigafactories, automotive deals, scale-ups)
2. New cell chemistry research and commercial milestones (solid-state, sodium-ion, LFP, silicon, etc.)
3. Battery thermal management, cooling, and high-power applications
4. EU energy transition policy and grid/storage deployment
5. Global energy transition status (IEA, IRENA, major markets)

Use multiple targeted searches. Cite all sources with URLs."""


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

    # The response contains a mix of server_tool_use, web_search_tool_result,
    # and text blocks. We only want the final text Claude wrote.
    text_parts = [
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    briefing = "\n\n".join(text_parts).strip()

    # Log usage so the GitHub Actions log shows what each run cost.
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
# Email delivery
# ---------------------------------------------------------------------------

def markdown_to_basic_html(md: str) -> str:
    """Very small markdown->HTML converter so the email renders nicely.
    Keeps things dependency-free; for richer rendering, swap in `markdown` lib.
    """
    import html
    import re

    lines = md.split("\n")
    out = []
    in_list = False

    for line in lines:
        escaped = html.escape(line)
        # Inline: **bold**, [text](url)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
            r'<a href="\2">\1</a>',
            escaped,
        )
        # Auto-link bare URLs
        escaped = re.sub(
            r'(?<!["\'>=])(https?://[^\s<]+)',
            r'<a href="\1">\1</a>',
            escaped,
        )

        stripped = line.strip()
        if stripped.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{escaped.lstrip().lstrip('-*').lstrip()}</li>")
        elif stripped == "":
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("<br>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{escaped}</p>")

    if in_list:
        out.append("</ul>")

    body = "\n".join(out)
    return f"""<!DOCTYPE html><html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:720px;margin:0 auto;padding:16px;line-height:1.5;color:#222;">
{body}
</body></html>"""


def send_email(briefing_md: str) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    subject = f"Weekly Battery & Energy Briefing - {datetime.now():%d %b %Y}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(briefing_md)  # plain-text fallback
    msg.add_alternative(markdown_to_basic_html(briefing_md), subtype="html")

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
