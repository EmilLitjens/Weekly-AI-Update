# Weekly Battery & Energy Transition Briefing

Automated weekly research briefing on:

1. **Battery industry & commercial developments** — gigafactories, OEM deals, scale-ups
2. **Battery technology** — cell chemistries, thermal management, fast-charging
3. **Energy transition status** — EU policy, grid storage, global progress

The script calls the Claude API with the built-in web search tool, then emails
the result via Gmail SMTP. Runs on GitHub Actions every Monday for free.

Estimated cost: **~$0.20–0.40 per run** (~$10–20/year). GitHub Actions cron
runs are free for public repos and within the generous free tier for private
ones.

---

## Setup (one-time, ~15 minutes)

### 1. Fork or push this repo to your own GitHub account

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create battery-briefing --private --source=. --push
```

(or create the repo through the GitHub UI and push normally)

### 2. Get an Anthropic API key

- Go to <https://console.anthropic.com/>
- Sign up / log in, add a payment method (it's prepaid — load $5 to start)
- Settings → API Keys → Create Key. Copy it.

### 3. Create a Gmail "app password" for SMTP sending

You can't use your normal Gmail password. You need an **app password**:

1. Enable 2-Step Verification on your Google account (required):
   <https://myaccount.google.com/security>
2. Then go to: <https://myaccount.google.com/apppasswords>
3. Create one named "Battery Briefing". You'll get a 16-character password
   like `abcd efgh ijkl mnop`. **Copy it without the spaces.**

If you don't see the App Passwords option, your Workspace admin may have
disabled it, or 2-Step Verification isn't enabled yet.

### 4. Add the four secrets to your GitHub repo

In your repo on GitHub: **Settings → Secrets and variables → Actions →
New repository secret**. Add these four:

| Secret name           | Value                                   |
| --------------------- | --------------------------------------- |
| `ANTHROPIC_API_KEY`   | Your Anthropic key (starts with `sk-`)  |
| `GMAIL_ADDRESS`       | The Gmail address sending the email     |
| `GMAIL_APP_PASSWORD`  | The 16-char app password (no spaces)    |
| `RECIPIENT_EMAIL`     | Where the briefing should arrive        |

The sender and recipient can be the same address — that's fine.

### 5. Test it manually before waiting for Monday

In your repo on GitHub: **Actions → Weekly Battery Briefing → Run workflow**.

It should complete in 1–2 minutes and the briefing should land in your inbox.
If it fails, click into the run to see the log.

### 6. (Optional) Adjust the schedule

The default is Monday 06:00 UTC. To change it, edit
`.github/workflows/weekly.yml` and update the cron line. The format is
`minute hour day-of-month month day-of-week` — examples:

- `0 6 * * 1` → every Monday at 06:00 UTC (current default)
- `0 7 * * 5` → every Friday at 07:00 UTC
- `30 5 * * 1,4` → every Monday and Thursday at 05:30 UTC

GitHub uses UTC. CET = UTC+1, CEST = UTC+2.

---

## Tweaking the briefing

The prompt that defines what goes in the briefing lives in `briefing.py` as
`SYSTEM_PROMPT`. Edit it freely — for example to:

- Add a section on a specific competitor or technology
- Change the geographic focus
- Change tone or length
- Add specific journals/sources to prioritise

Commit and push, and the next run uses your new prompt.

You can also adjust:

- `MODEL` — `claude-sonnet-4-6` is the recommended default. `claude-haiku-4-5`
  is cheaper but less thorough; `claude-opus-4-7` is overkill for this task.
- `MAX_SEARCHES` — default 10. Lowering reduces cost; raising can give more
  thorough coverage but each search is $0.01 + extra tokens.

---

## Troubleshooting

**SMTP authentication fails** — the app password is wrong or 2FA isn't
enabled. Regenerate the app password and make sure you copy it without
spaces.

**`web_search_tool_result_error: max_uses_exceeded`** in the log — Claude
wanted to search more than `MAX_SEARCHES` allows. The briefing is still
generated from the searches it did run; raise the cap if you want.

**Workflow doesn't run on schedule** — GitHub disables scheduled workflows on
repos with no activity for 60 days. Push a commit (even a README tweak) to
re-enable it. Or set a calendar reminder to manually trigger it occasionally.

**The briefing feels generic** — tighten the system prompt with specific
companies, technologies, and journals you care about. The more specific the
prompt, the better the searches.

---

## What this costs

Per run, roughly:

- 8–10 web searches × $0.01 = **$0.08–0.10**
- Sonnet 4.6 tokens (search results are billed as input):
  ~50K input + ~3K output ≈ **$0.15–0.30**
- **Total: ~$0.25–0.40 per week**, or **~$13–20 per year**

GitHub Actions: free for public repos. Private repos get 2,000 free minutes
per month — this job uses ~2 minutes per week, so ~8 minutes/month. Free.
