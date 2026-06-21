# Claude / stop-slop 復旧メモ

このメモは、Hermes 周辺で Claude 系エージェントを使うときに、API retry が多発したり `stop-slop` skill が見つからなかったりした場合の復旧手順です。

公開 repo 向けなので、API key、token、debug log全文、個人プロンプト全文は載せません。

## 事象

見た目には次のような失敗になります。

- `API failed after 3 retries`
- `Connection error`
- `Request timed out`
- `Skill(s) not found and skipped: ...`

ただし retry 表示だけでは原因を切り分けられません。今回の実例では、debug log 側に `404 model_not_found` が出ており、既定モデルに無効な名前が入っていました。

## 結論

- Claude Code / Clawd on Desk 系の実体は、Hermes の `.hermes` ではなく `%USERPROFILE%\.claude` 側にあることがある。
- `claude-fable-5[1m]` のような provider alias を既定モデルへ入れると、UI では接続エラーに見えても API では `model_not_found` になることがある。
- Opus 4.8 を使う場合の設定値は `claude-opus-4-8` にする。
- `claude-opus-4.8` のようなドット表記や、別モデルへの置き換えは避ける。
- `stop-slop` は利用する runtime ごとの skill directory へ置く。
- Claude Desktop の local agent mode は `%APPDATA%\Claude\local-agent-mode-sessions\skills-plugin` 配下の manifest を使うことがある。`.claude\skills` だけでは Desktop 側から見えない場合がある。

## 1. 実プロファイルを確認する

まず Hermes 側だけを見ず、Claude 側も確認します。

```powershell
Test-Path "$env:USERPROFILE\.claude"
Test-Path "$env:USERPROFILE\.claude\settings.json"
Get-ChildItem "$env:USERPROFILE\.claude\debug" -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 Name, LastWriteTime, Length
```

`%LOCALAPPDATA%\hermes` や `%USERPROFILE%\.hermes` が存在しない場合でも、`.claude` 側に設定と debug log が残っていることがあります。

## 2. debug log は必要な語だけ検索する

debug log や provider 設定には秘密情報が混ざる可能性があります。全文を貼らず、必要な語だけ検索します。

```powershell
Select-String `
  -Path "$env:USERPROFILE\.claude\debug\*.txt" `
  -Pattern "model_not_found|model=|API Error|Request timed out|Connection error" |
  Select-Object -First 50
```

`model_not_found` と無効な model 名が一緒に出ていれば、ネットワークより先に model 設定を直します。

## 3. Claude 既定モデルを Opus 4.8 にする

`%USERPROFILE%\.claude\settings.json` の `model` を `claude-opus-4-8` にします。

```powershell
$settingsPath = "$env:USERPROFILE\.claude\settings.json"
$settings = Get-Content -Raw -Encoding UTF8 $settingsPath | ConvertFrom-Json
$settings.model = "claude-opus-4-8"
$settings | ConvertTo-Json -Depth 64 | Set-Content -Encoding UTF8 $settingsPath
```

注意:

- `claude-sonnet-4-6` は別モデルなので、Opus 4.8 指定の代替にしない。
- `claude-opus-4.8` ではなく `claude-opus-4-8` を使う。
- `claude-fable-5[1m]` のような一時 alias を既定値に残さない。

## 4. stop-slop を skill directory へ導入する

この repo の helper script を使います。

```powershell
.\scripts\install-stop-slop-skills.ps1
```

既定の導入先:

```text
%USERPROFILE%\.claude\skills\stop-slop
%USERPROFILE%\.codex\skills\stop-slop
%USERPROFILE%\.agents\skills\stop-slop
%APPDATA%\Claude\local-agent-mode-sessions\skills-plugin\...\skills\stop-slop
```

dry run:

```powershell
.\scripts\install-stop-slop-skills.ps1 -DryRun
```

導入後、最低限のファイルがあることを確認します。

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\skills\stop-slop"
Get-ChildItem "$env:USERPROFILE\.codex\skills\stop-slop"
Get-ChildItem "$env:USERPROFILE\.agents\skills\stop-slop"
```

Claude Desktop local agent mode で使われる skills plugin も確認します。

```powershell
$pluginBase = Join-Path $env:APPDATA "Claude\local-agent-mode-sessions\skills-plugin"
$manifest = Get-ChildItem -LiteralPath $pluginBase -Recurse -Filter manifest.json |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
$pluginRoot = Split-Path -Parent $manifest
$json = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
@($json.skills | Where-Object { $_.name -eq "stop-slop" -and $_.enabled }).Count
Test-Path (Join-Path $pluginRoot "skills\stop-slop\SKILL.md")
```

manifest を更新した後は、Claude Desktop の local agent session を開き直してください。Desktop 側が古い skills-plugin cache を保持している場合があります。

## 5. 動作確認

Opus は初期コンテキスト見積もりが大きいことがあるため、疎通確認の budget は低くしすぎないでください。

```powershell
claude -p "OK とだけ返して" --output-format json --max-budget-usd 1.00
```

確認ポイント:

- command が exit 0 で終わる。
- JSON 内の `modelUsage` に `claude-opus-4-8` が出る。
- debug log に新しい `model_not_found` が増えない。

`--max-budget-usd 0.25` などで失敗し、`1.00` で成功する場合は、認証や model 名ではなく budget 上限に当たっている可能性があります。

## 6. `personal-mentor-secretary` が見つからない場合

`Skill(s) not found and skipped: personal-mentor-secretary` が出ても、空の placeholder skill で握りつぶさないでください。

正しい対応:

- 起動元 prompt や cron job が本当にその skill を要求しているか確認する。
- 正規の `SKILL.md` 配布元を確認する。
- 見つからない場合は、skill 名を prompt から外すか、正規ソースを導入する。

公開 repo には、個人秘書 skill の実本文や private prompt をそのまま入れません。必要なら `examples/SOUL.private-mentor-secretary.md` のような秘匿情報なしのサンプルに留めます。

## 7. 再発時の切り分け順

1. debug log で `model_not_found` を検索する。
2. `%USERPROFILE%\.claude\settings.json` の `model` を確認する。
3. `claude -p ... --output-format json --max-budget-usd 1.00` で単体疎通を見る。
4. `stop-slop` の user skill directory 3か所を確認する。
5. Claude Desktop local agent mode の `skills-plugin` manifest に `stop-slop` があるか確認する。
6. `personal-mentor-secretary` は正規ソース確認まで作らない。
7. `daily_conversation_context.py` の timeout が再発する場合は、LLM 起動待ち、`ensure_llm.py`、cron output、`checkin_skips.jsonl` を見る。
