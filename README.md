# 747

# 747 movements alerts — cloud-hosted setup

This folder contains everything you need to run the 747 check on GitHub's
servers, twice a day, with no laptop required. You don't need to write code
or open a terminal — you can do the whole setup in your web browser.

## What you're building

A GitHub Actions workflow that fires twice a day, calls the AeroDataBox flight
API for Auckland and Sydney arrivals + departures over the next ~24 hours,
filters anything that's a Boeing 747, and posts the result as a Slack message.

## Files in this folder

- `check_747s.py` — the script that does the check (Python, no dependencies)
- `.github/workflows/check.yml` — tells GitHub when and how to run the script
- `requirements.txt` — a placeholder (the script uses only Python's standard library)
- `README.md` — this guide

---

## One-time setup (about 20 minutes)

### Step 1 — Create a GitHub account (skip if you have one)

Go to https://github.com and sign up. The free plan is enough.

### Step 2 — Create a new private repository

1. After signing in, click the **+** at the top right → **New repository**.
2. Name it whatever you like, e.g. `747-alerts`.
3. Set it to **Private** (no need for the world to see it).
4. Tick **Add a README file**.
5. Click **Create repository**.

### Step 3 — Upload the three files

You'll add three files: the script, the workflow, and the requirements file.

For each file:

1. In your new repo, click **Add file** → **Create new file**.
2. Type the filename (exactly — including the path with slashes for the workflow).
3. Paste the contents from this folder.
4. Scroll down and click **Commit changes**.

The exact filenames you need to create:

| Filename | What to paste |
|---|---|
| `check_747s.py` | the contents of `check_747s.py` |
| `.github/workflows/check.yml` | the contents of `.github/workflows/check.yml` |
| `requirements.txt` | the contents of `requirements.txt` |

> **Tip:** When you type `.github/workflows/check.yml` into the filename box,
> GitHub will automatically create the nested folders for you. Make sure to
> include the slashes exactly as shown.

### Step 4 — Sign up for AeroDataBox and grab an API key

1. Go to https://rapidapi.com/aedbx-aedbx/api/aerodatabox.
2. If you don't have a RapidAPI account, click **Sign Up** (top right) and
   create one. You can use Google or email.
3. Once logged in, on the AeroDataBox page click **Subscribe to Test**.
4. The free plan ("BASIC") covers ~100 calls/month. With twice-daily runs
   that's not quite enough, so once you've confirmed the setup works, switch
   to **PRO** (~$10/month, 1000 calls) by clicking **Subscribe**.
5. Back on the AeroDataBox API page, look in the right-hand column for the
   header **`X-RapidAPI-Key`**. The long string of letters and numbers next
   to it is your API key. Copy it.

### Step 5 — Create a Slack incoming webhook

1. Go to https://api.slack.com/apps and click **Create New App** →
   **From scratch**.
2. Name it something like "747 Alerts" and pick your Slack workspace.
3. On the next screen, under **Add features and functionality**, click
   **Incoming Webhooks**.
4. Toggle **Activate Incoming Webhooks** to **On**.
5. Click **Add New Webhook to Workspace** (at the bottom).
6. Pick the channel where you want the alerts posted. If you want them in
   your own DMs, you'll need to create a private channel just for yourself
   first (Slack doesn't allow webhooks to post into the Slackbot DM
   directly).
7. Slack shows you a **Webhook URL** starting with `https://hooks.slack.com/...`.
   Copy it.

### Step 6 — Add both secrets to your GitHub repo

1. Go to your `747-alerts` repo on GitHub.
2. Click **Settings** (top tab inside the repo, not the global one).
3. In the left sidebar, click **Secrets and variables** → **Actions**.
4. Click **New repository secret** and add the first one:
   - **Name:** `RAPIDAPI_KEY`
   - **Secret:** paste the AeroDataBox key from Step 4.
5. Click **Add secret**, then **New repository secret** again:
   - **Name:** `SLACK_WEBHOOK_URL`
   - **Secret:** paste the Slack webhook URL from Step 5.
6. Click **Add secret**.

### Step 7 — Run it once manually to confirm it works

1. In your repo, click the **Actions** tab.
2. In the left sidebar, click **747 movements check**.
3. Click **Run workflow** → **Run workflow**.
4. After a few seconds a yellow dot appears next to the new run. Click into
   it to watch the progress.
5. When the run finishes (green tick), check your Slack channel — the
   message should be waiting.

If something failed, click the failed step in the GitHub Actions log to see
the error. The most common issues:

- Wrong secret name (must be exactly `RAPIDAPI_KEY` and `SLACK_WEBHOOK_URL`)
- AeroDataBox subscription is on the wrong plan or hasn't activated yet
- Webhook URL points to a channel the Slack app doesn't have access to

### Step 8 — Done

From here on, GitHub fires the workflow automatically at the scheduled times.
No laptop, no Chrome, no Cowork required.

---

## Customising

- **Change the schedule** — edit `.github/workflows/check.yml`, the `cron`
  lines. GitHub Actions cron runs in UTC; today's settings (`30 20 * * *` and
  `30 4 * * *`) fire at 08:30 and 16:30 NZ winter time.
- **Change the lookahead** — edit `LOOK_AHEAD_HOURS` in `check_747s.py`.
- **Add more airports** — add entries to the `AIRPORTS` list at the top of
  `check_747s.py`. Use ICAO codes (e.g. `WSSS` = Singapore Changi).
- **Suppress "no 747s found" messages** — at the end of `main()`, only call
  `post_to_slack` if `total > 0`.
- **Different alert content** — modify `format_message` in `check_747s.py`.

## Why AeroDataBox instead of FlightRadar24?

FlightRadar24 doesn't offer a public API for scheduled flight data, and
scraping their web UI from a server hits Cloudflare's bot protection.
AeroDataBox aggregates the same airline schedule data into a clean JSON
endpoint with aircraft type included — no anti-bot games.

## Cost summary

- GitHub Actions: **free** (this workflow uses ~5 minutes/month of the
  2,000-minute monthly allowance)
- AeroDataBox via RapidAPI: **free for first 100 calls/month**, then ~$10/mo
  for PRO (1000 calls) if you keep twice-daily runs
- Slack: **free** (webhooks are included in every Slack plan)

So $0/month if you drop to one run/day, ~$10/month for twice-daily.
