# UwUConverter Slack Bot

A small Slack bot that wraps the installed `UwUConverter` CLI.

It does not import the converter internals. Every actual conversion operation is launched through the same CLI that can be used from a terminal.

## Commands

Upload or share a file in a channel containing the bot, then run:

```text
/uwu convert <format>
/uwu help
```

Examples:

```text
/uwu convert webp
/uwu convert mp4
/uwu convert wav
```

The bot remembers the latest file shared by each user in each channel.

## Slack setup

The easiest setup uses Socket Mode, so the bot does not need a public HTTP endpoint.

1. Go to Slack app settings.
2. Create a new app from `slack_manifest.yaml`.
3. Install the app to your workspace.
4. Copy the Bot User OAuth Token into `SLACK_BOT_TOKEN`.
5. Open Basic Information -> App-Level Tokens.
6. Create an app-level token with the `connections:write` scope.
7. Put that token into `SLACK_APP_TOKEN`.
8. Invite the bot to any channel where it should process files.

The bot scopes in the manifest are:

```text
commands
chat:write
files:read
files:write
```

## Requirements

UwUConverter must already be installed and available as:

```text
UwUConverter
```

Check:

```bash
UwUConverter --version
```

If it is installed somewhere else, set:

```text
UWU_CLI_PATH=/full/path/to/UwUConverter
```

## Install the bot

Create a virtual environment:

```bash
python3 -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Fish:

```fish
source .venv/bin/activate.fish
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install:

```bash
pip install -r requirements-slack.txt
```

Copy `.env.example` values into your environment.

Linux/Fish example:

```fish
set -x SLACK_BOT_TOKEN "xoxb-..."
set -x SLACK_APP_TOKEN "xapp-..."
python slack_bot.py
```

Windows PowerShell example:

```powershell
$env:SLACK_BOT_TOKEN = "xoxb-..."
$env:SLACK_APP_TOKEN = "xapp-..."
python .\slack_bot.py
```

## File flow

For a normal conversion:

```text
Slack file
  -> temporary local file
  -> UwUConverter CLI
  -> converted local file
  -> Slack file upload
  -> temporary directory deleted
```

Slack files are downloaded using their private download URL and the bot token. Results are uploaded with Slack's v2 file upload API.

## Limits

By default:

```text
Maximum Slack input file: 200 MB
CLI timeout: 1800 seconds
```

Override them with:

```text
UWU_MAX_FILE_MB
UWU_TIMEOUT_SECONDS
```

This is intentionally a small first implementation. It keeps recent-file state only in memory, so restarting the bot forgets which file each user most recently shared.

## Security notes

Do not commit Slack tokens.

The bot passes command arguments to `subprocess.run()` as an argument list rather than through a shell.

Temporary job directories are deleted automatically after each job.

The bot only downloads files Slack exposes to its bot token.
