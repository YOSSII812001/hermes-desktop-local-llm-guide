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

Important:

- Do not regenerate the OAuth link after the user receives a callback URL.
- Regenerating the link changes the PKCE state and can cause `state mismatch`.
- Do not commit the callback URL.
- Delete temporary OAuth state files after the exchange completes.

## Safety

Do not commit:

- OAuth token
- callback URL
- state file content
- auth store files
- search results that contain private user context
