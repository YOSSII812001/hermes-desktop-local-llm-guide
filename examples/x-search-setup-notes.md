# xAI X Search setup notes

This file is a safe public note.
It intentionally contains no OAuth token, callback URL, user ID, or state file content.

## Goal

Enable Hermes `x_search` so Hermes can search public X posts for research and operational examples.

## Enable the tool

```powershell
$env:HERMES_CONFIG_DIR = "$env:LOCALAPPDATA\hermes"
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" tools enable --platform cli x_search
```

For Discord or another platform, enable and verify the tool for that platform separately.

## Verify OAuth

```powershell
$env:HERMES_CONFIG_DIR = "$env:LOCALAPPDATA\hermes"
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" auth status xai-oauth
```

Expected:

```text
logged in
```

## Verify the tool

```powershell
$env:HERMES_CONFIG_DIR = "$env:LOCALAPPDATA\hermes"
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" tools list --platform cli
```

Expected:

```text
x_search enabled
```

## Smartphone OAuth callback note

If OAuth is approved on a phone, the browser may fail to open `127.0.0.1`.
In that case, copy the callback URL from the browser address bar and exchange the code locally.

Use the helper script from the repository root:

```powershell
$env:HERMES_CONFIG_DIR = "$env:LOCALAPPDATA\hermes"
$python = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"

& $python .\scripts\xai_oauth_manual_helper.py init
```

Open the printed URL. After approval, the phone may show a connection error for `127.0.0.1`.
Copy the full browser address bar URL. It should look like this:

```text
http://127.0.0.1:56121/callback?state=...&code=...
```

Then exchange it locally:

```powershell
& $python .\scripts\xai_oauth_manual_helper.py exchange "http://127.0.0.1:56121/callback?state=...&code=..."
```

The helper saves the OAuth credential to Hermes and deletes its temporary state file after a successful exchange.

Important:

- Do not regenerate the OAuth link after the user receives a callback URL.
- Regenerating the link changes the PKCE state and can cause `state mismatch`.
- Do not commit the callback URL.
- Delete temporary OAuth state files after the exchange completes.

## Direct x_search helper

Hermes should normally call `x_search` as a tool.
If a session does not notice the tool yet, restart Hermes Desktop or open a new chat.

For direct verification from the terminal:

```powershell
$env:HERMES_CONFIG_DIR = "$env:LOCALAPPDATA\hermes"
$python = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"

& $python .\scripts\x_search.py "Hermes Agent x_search" --pretty
& $python .\scripts\x_search.py "Hermes Agent x_search" --handle xai --pretty
```

Date filters and media understanding are available:

```powershell
& $python .\scripts\x_search.py "Hermes Agent" --from-date 2026-06-01 --to-date 2026-06-06 --pretty
& $python .\scripts\x_search.py "Gemma 4" --images --pretty
```

## Safety

Do not commit:

- OAuth token
- callback URL
- state file content
- auth store files
- search results that contain private user context
