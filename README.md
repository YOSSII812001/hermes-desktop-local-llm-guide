# Hermes Agent Desktop にローカルLLMを導入する手順

Hermes Agent Desktop を、LM Studio なしでローカルLLMにつなぐための手順です。

このREADMEは、Windows環境で実際にかなり苦戦しながら構築した内容をまとめています。
結論から言うと、`Hermes Agent Desktop + llama-server + GGUFモデル` の構成で動きます。

Discord DM、Obsidian、Codex skills、各種Tool useまで含めた個人メンター秘書運用は、次の詳細メモに分けています。

- [Hermes Agent Desktop を個人メンター秘書として運用する設定メモ](docs/personal-mentor-discord-obsidian-gemma4.md)
- [Hermes Agent Desktop 自律実行とGateway運用メモ](docs/autonomous-codex-gateway-ops.md)
- [Hermes Agent Desktop セットアップ学びチェックリスト](docs/setup-lessons-checklist.md)
- [安全な設定サンプル](examples/)

## AIへ渡すとき

別のAIにセットアップを依頼するときは、このREADMEと詳細メモを両方読ませてください。

依頼文の例:

```text
このリポジトリを読んで、Windows環境のHermes Agent Desktopを
Gemma 4ローカルLLM、Discord DM、Obsidian、Codex skills連携込みで
セットアップしてください。

まずREADME.mdを読み、次に docs/personal-mentor-discord-obsidian-gemma4.md と
docs/autonomous-codex-gateway-ops.md と docs/setup-lessons-checklist.md を読んでください。
必要に応じて examples/ の設定サンプルを使ってください。
秘密情報や実パスは推測せず、必要なものだけ私に確認してください。
```

このリポジトリには、Bot Token、DiscordユーザーID、DMチャンネルID、個人ノート本文は入れていません。
AIは手順を再現できますが、秘密情報と実ファイルパスはユーザーのローカル環境で入力する必要があります。

## できること

- Hermes Agent Desktop 単体でローカルLLMを使う
- LM Studioを起動せずにGGUFモデルを使う
- Hermes Desktop起動時に `llama-server` も自動起動する
- Hermes Desktopを閉じたら `llama-server` も自動終了する
- Gemma 4の思考を有効化し、制限なし寄りで動かす
- Discord DMで個人メンター秘書として使う
- Obsidian Vaultを参照し、成果物を専用フォルダへ出す
- Obsidianの `hermes/homework` にNext Actionsを宿題としてためる
- 5分cronでCodex自律runnerを動かし、空き時間に宿題を進める
- 宿題完了時にDiscordへ報告し、Obsidianファイル名へ `[完了] ` を付ける
- Gatewayの自己再起動を外側Scheduled Taskで安全に実行する
- xAI OAuthと `x_search` でXの公開投稿を検索する
- Discord向け内部思考ガードでローカルLLMの漏れを抑える
- Gateway外側watchdogでGateway停止を復旧する
- Codex skillsをHermes側でも参照する
- `approvals.mode: off` で承認なしのYOLO運用にする

## 全体構成

```mermaid
flowchart LR
    User["ユーザー"]
    Shortcut["Hermes Desktop (local LLM) ショートカット"]
    Launcher["PowerShell ランチャー"]
    Hermes["Hermes Agent Desktop"]
    Server["llama-server"]
    Model["GGUFモデル"]

    User --> Shortcut
    Shortcut --> Launcher
    Launcher --> Hermes
    Launcher --> Server
    Server --> Model
    Hermes -->|"OpenAI互換API http://127.0.0.1:8080/v1"| Server
```

`llama-server` は、llama.cppに含まれるOpenAI互換のHTTPサーバーです。
Hermes Desktop側から見ると、ローカルにあるOpenAI互換エンドポイントへ接続しているだけです。

参考:

- [llama.cpp Server documentation](https://www.mintlify.com/ggml-org/llama.cpp/inference/server)
- [google/gemma-4-12B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf)

## 検証環境

今回の検証環境です。

| 項目 | 内容 |
|---|---|
| OS | Windows |
| GPU | NVIDIA GeForce RTX 4070 Ti SUPER 16GB |
| Hermes Agent Desktop | v0.15.1 |
| llama.cpp | CUDA対応版 b9498 |
| モデル | `gemma-4-12b-it-qat-q4_0.gguf` |
| コンテキスト長 | 262144 |
| KVキャッシュ | `q8_0` |
| APIエンドポイント | `http://127.0.0.1:8080/v1` |

最初はQ8とQ6_Kを使いました。
現在は公式Google QAT Q4_0モデルを使い、256Kコンテキストで運用しています。

## 重要な結論

今回の一番大きな学びはここです。

Hermes CLI用の設定と、Hermes Desktop用の設定は別の場所を見ていることがあります。

```text
CLIで見ていた設定:
C:\Users\<USER>\.hermes\config.yaml

Desktopが見ていた設定:
C:\Users\<USER>\AppData\Local\hermes\config.yaml
```

Desktopがどの設定を読んでいるかは、次のAPIで確認できます。

```powershell
Invoke-RestMethod http://127.0.0.1:9120/api/status | ConvertTo-Json -Depth 5
```

`config_path` に出るパスが、Desktopが実際に読んでいる設定です。
ここを見ずに `.hermes\config.yaml` だけ直すと、CLIでは動くのにDesktopでは無反応になります。

## 1. GGUFモデルを用意する

今回はGoogle公式のGemma 4 12B Instruct QAT GGUFを使いました。

標準にするモデルはこれです。

```text
gemma-4-12b-it-qat-q4_0.gguf
```

Hugging Face repo:

```text
google/gemma-4-12B-it-qat-q4_0-gguf
```

Q8とQ6_Kも動きました。
ただし、現在は公式QAT Q4_0を採用しています。

配置例:

```text
C:\Users\<USER>\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf
```

`huggingface-cli download` などでローカルへ保存しておけば使えます。
LM Studio本体を起動する必要はありません。

## 2. Gemma 4対応のllama-serverを用意する

古いllama.cppでは、Gemma 4を読み込めない場合があります。
今回、古いllama.cppでは次のようなエラーが出ました。

```text
unknown model architecture: 'gemma4'
```

この場合は、新しいllama.cppを使ってください。
今回の検証では、CUDA 12.4対応の `llama.cpp b9498` で動きました。

配置例:

```text
C:\Users\<USER>\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe
```

## 3. llama-serverを起動する

最小構成は次のようなコマンドです。

```powershell
& "C:\Users\<USER>\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe" `
  -m "C:\Users\<USER>\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf" `
  --alias gemma-4-12b-it `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 262144 `
  --parallel 1 `
  --reasoning on `
  --reasoning-budget -1 `
  --reasoning-format deepseek `
  --cache-type-k q8_0 `
  --cache-type-v q8_0
```

ポイントは `--alias` です。
Hermes側ではこの名前をモデル名として使います。

`--reasoning on` と `--reasoning-budget -1` は、Gemma 4の思考を有効にして制限なし寄りにする設定です。
思考が不要な場合は `--reasoning off` に戻せます。

256KコンテキストではKVキャッシュのVRAM使用量が増えます。
今回の環境では `--cache-type-k q8_0` と `--cache-type-v q8_0` を使い、公式QAT Q4_0モデルを256Kで起動できました。

起動確認:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/v1/models | ConvertTo-Json -Depth 5
```

`id` に `gemma-4-12b-it` が出ればOKです。

## 4. Hermes Desktop側のconfig.yamlを変更する

まず、Desktopが読んでいる設定ファイルを確認します。

```powershell
Invoke-RestMethod http://127.0.0.1:9120/api/status | ConvertTo-Json -Depth 5
```

今回の環境では、次のファイルでした。

```text
C:\Users\<USER>\AppData\Local\hermes\config.yaml
```

このファイルの `model` と `approvals` を次のように変更します。

```yaml
model:
  base_url: http://127.0.0.1:8080/v1
  default: gemma-4-12b-it
  provider: custom
  context_length: 262144
  api_key: not-needed

approvals:
  mode: off
```

`approvals.mode: off` は、Hermesにツール実行を承認なしで任せる設定です。
便利ですが、危険なコマンドも承認なしで実行されます。
自分だけのローカル環境で、リスクを理解したうえで使ってください。

## 5. 64K以上のコンテキストが必要

Hermes Agentは、モデルのコンテキスト長が短いと起動できないことがあります。
今回、32768では次のエラーが出ました。

```text
Model gemma-4-12b-it has a context window of 32,768 tokens,
which is below the minimum 64,000 required by Hermes Agent.
```

そのため、`llama-server` とHermes設定の両方を64K以上にします。
現在は公式QAT Q4_0モデルで、256Kにそろえて運用しています。

`llama-server`:

```powershell
--ctx-size 262144
--cache-type-k q8_0
--cache-type-v q8_0
```

Hermes:

```yaml
model:
  context_length: 262144
```

## 6. Hermes Desktopを再起動する

設定を変更したら、Hermes Desktopを再起動します。

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "Hermes.exe" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

その後、通常通りHermes Desktopを起動します。

## 7. 動作確認

Hermes側の認識を確認します。

```powershell
Invoke-RestMethod http://127.0.0.1:9120/api/model/info | ConvertTo-Json -Depth 5
```

期待する出力:

```json
{
  "model": "gemma-4-12b-it",
  "provider": "custom",
  "config_context_length": 262144,
  "effective_context_length": 262144
}
```

Hermes Desktopで `ハロー` と送って返事が返れば成功です。

## 8. Desktopで無反応に見えるとき

まずログを見ます。

```powershell
Get-Content "C:\Users\<USER>\AppData\Local\hermes\logs\agent.log" -Tail 100
Get-Content "C:\Users\<USER>\AppData\Local\hermes\logs\errors.log" -Tail 100
```

今回の失敗では、裏で次のエラーが出ていました。

```text
provider=copilot base_url=https://api.githubcopilot.com model=claude-opus-4.8
The requested model is not supported.
```

つまり、Desktopがまだ古い `claude-opus-4.8` を握っていました。

## 9. 既存セッションが古いモデルを握る問題

Hermes Desktopの既存チャットは、セッションDBにモデル名を持つことがあります。
設定をGemmaに変えても、古いチャットだけ `claude-opus-4.8` のまま失敗することがあります。

セッションDBの場所:

```text
C:\Users\<USER>\AppData\Local\hermes\state.db
```

確認例:

```powershell
@'
import sqlite3, json
path = r"C:\Users\<USER>\AppData\Local\hermes\state.db"
con = sqlite3.connect(path)
con.row_factory = sqlite3.Row
rows = con.execute("""
select id, source, model, billing_provider, billing_base_url, message_count, started_at
from sessions
order by started_at desc
limit 10
""").fetchall()
for row in rows:
    print(json.dumps(dict(row), ensure_ascii=False, default=str))
con.close()
'@ | py -X utf8 -
```

修正する場合は、必ずバックアップを取ってからにしてください。

```powershell
Copy-Item `
  "C:\Users\<USER>\AppData\Local\hermes\state.db" `
  "C:\Users\<USER>\AppData\Local\hermes\state.db.bak"
```

新規チャットを作るだけで回避できる場合もあります。

## 10. LM Studioを閉じる

LM Studioが同じGPUや同じモデルを握っていると、遅くなります。
今回もLM Studioや別のTTSプロセスを止めたあと、応答速度が大きく改善しました。

ローカルLLMをHermesで使うときは、GPUを使う常駐プロセスを減らしてください。

確認例:

```powershell
nvidia-smi
```

## 11. 公式QAT Q4_0へ確定した理由

Q8は品質寄りですが、16GB VRAMでは余裕が少なかったです。
Q6_Kでも運用できましたが、現在はGoogle公式のQAT Q4_0モデルへ確定しました。

QAT Q4_0は公式repoで配布され、256Kコンテキストに対応しています。
Hermes側のモデル名は互換性のため `gemma-4-12b-it` のままにし、モデルファイルだけQATへ差し替えます。

この構成なら、Desktop既存設定と `llama-server` のaliasを大きく変えずに移行できます。

## 12. 自動起動ショートカットを作る

毎回手動で `llama-server` を起動するのは面倒です。
そこで、次の流れをPowerShellで自動化します。

1. ショートカットを押す
2. `llama-server` を起動する
3. Hermes Desktopを起動する
4. Hermes Desktopを閉じる
5. `llama-server` も自動終了する

このリポジトリには、次のスクリプト例を入れています。

```text
scripts/start-gemma-llama-server.ps1
scripts/stop-gemma-llama-server.ps1
scripts/start-hermes-desktop-with-local-llm.ps1
scripts/watch-hermes-process-and-stop-gemma.ps1
scripts/xai_oauth_manual_helper.py
scripts/x_search.py
```

まず `scripts/start-gemma-llama-server.ps1` の先頭を自分の環境に合わせます。

```powershell
$ServerExe = "C:\Users\<USER>\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe"
$ModelPath = "C:\Users\<USER>\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf"
```

次にショートカットを作ります。

```powershell
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Hermes Desktop (Local LLM).lnk"
$scriptPath = "C:\Users\<USER>\path\to\scripts\start-hermes-desktop-with-local-llm.ps1"
$powershell = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$hermesExe = "C:\Users\<USER>\AppData\Local\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
$shortcut.WorkingDirectory = Split-Path -Parent $hermesExe
$shortcut.IconLocation = "$hermesExe,0"
$shortcut.Description = "Start Hermes Desktop with local llama-server"
$shortcut.Save()
```

## 13. 自動起動でハマったこと

最初の自動起動スクリプトでは、`llama-server` の準備完了を待ってからHermes Desktopを開いていました。
この作りだと、モデル読み込み中に何も表示されません。
ユーザーから見ると「起動しない」ように見えます。

さらに、待ちきれずショートカットを複数回押すと、`llama-server` が二重起動しました。

対策:

- `llama-server` 起動後、すぐHermes Desktopを表示する
- モデル準備完了の確認は裏側ログで行う
- 二重ランチャーを検出して、後から起動したほうを終了する
- 既に対象モデルの `llama-server` が起動中なら再利用する

この対策を入れたものが `scripts/start-hermes-desktop-with-local-llm.ps1` です。

## 14. xAI OAuth と X検索 helper

Hermesの `x_search` は、xAI OAuthまたは `XAI_API_KEY` があると使えます。
通常はHermes Desktopの画面や `hermes auth add xai-oauth` でログインします。

スマホやリモート環境では、OAuth後に `127.0.0.1` へ戻れず「サーバーに接続できません」と表示されることがあります。
その場合は、次のhelperで認可URLを作り、callback URLをローカルで交換します。

```powershell
$python = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"
& $python .\scripts\xai_oauth_manual_helper.py init
```

表示されたURLを開き、許可後にブラウザのアドレスバーから `callback?...` URLをコピーします。
そのURLを次のコマンドへ渡します。

```powershell
& $python .\scripts\xai_oauth_manual_helper.py exchange "http://127.0.0.1:56121/callback?state=...&code=..."
```

注意点:

- `callback` URLを受け取った後に `init` を再実行しない
- `init` を再実行するとPKCE stateが変わり、`state mismatch` になる
- token、callback URL、一時stateファイルはコミットしない

`x_search` をHermesのtool callではなく、terminalから直接試す場合は次を使います。

```powershell
& $python .\scripts\x_search.py "Hermes Agent x_search" --pretty
& $python .\scripts\x_search.py "Hermes Agent x_search" --handle xai --pretty
```

詳しい手順は `examples/x-search-setup-notes.md` にまとめています。

## 15. トラブルシュート

### Hermes Desktopが返答しない

確認するもの:

```powershell
Invoke-RestMethod http://127.0.0.1:9120/api/model/info | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8080/v1/models | ConvertTo-Json -Depth 5
```

見るポイント:

- Hermesの `provider` が `custom` か
- Hermesの `model` が `gemma-4-12b-it` か
- `llama-server` の `/v1/models` に同じモデル名が出るか
- Desktopが読んでいる `config_path` が想定通りか

### `model_not_supported` が出る

Desktopが古いモデル設定を握っています。

確認:

```powershell
Get-Content "C:\Users\<USER>\AppData\Local\hermes\logs\agent.log" -Tail 100
```

`claude-opus-4.8` や `copilot` が出る場合は、Desktop側configを見直してください。

### `unknown model architecture: gemma4` が出る

llama.cppが古いです。
Gemma 4対応版に更新してください。

### コンテキスト長が短くて失敗する

Hermes Agentは最低64K程度を要求する場合があります。
現在のGemma 4 QAT Q4_0構成では256Kで起動できています。

`llama-server`:

```powershell
--ctx-size 262144
--cache-type-k q8_0
--cache-type-v q8_0
```

Hermes:

```yaml
model:
  context_length: 262144
```

### 返答が遅い

見るポイント:

- LM Studioが起動していないか
- 他のTTSやローカルLLMがGPUを使っていないか
- 公式QAT Q4_0モデルを使っているか
- 初回応答でプロンプトキャッシュが効いていないだけではないか

GPU確認:

```powershell
nvidia-smi
```

## 16. 今回の学び

今回、一番時間がかかったのはモデルそのものではありません。
設定ファイル、セッションDB、既存プロセス、GPU使用状況の切り分けでした。

学びをまとめます。

- Hermes CLIとHermes Desktopは、別の `config.yaml` を読むことがある
- Desktopの実設定は `/api/status` の `config_path` で確認する
- `/v1/models` が返っても、Hermes側の設定が合っているとは限らない
- 既存チャットは古いモデル名をセッションDBに持つことがある
- Hermes Agentでは64K以上のコンテキストを満たす必要がある
- Gemma 4 QAT Q4_0は256Kコンテキストで起動できた
- Gemma 4は古いllama.cppでは読めない
- Q8とQ6_Kも動くが、現在は公式Google QAT Q4_0を標準にする
- LM StudioやTTSなど、GPUを握る常駐プロセスは速度に大きく影響する
- 自動起動では、モデル読み込み完了を待つより先にDesktop画面を出すほうが親切
- ショートカットは複数回押される前提で、二重起動防止が必要

## 17. 最終構成

最終的には、次の構成で安定しました。

```text
Hermes Agent Desktop
  -> provider: custom
  -> base_url: http://127.0.0.1:8080/v1
  -> model: gemma-4-12b-it
  -> context_length: 262144

llama-server
  -> model file: gemma-4-12b-it-qat-q4_0.gguf
  -> alias: gemma-4-12b-it
  -> port: 8080
  -> ctx-size: 262144
  -> cache-type-k/v: q8_0
  -> reasoning: on
  -> reasoning-budget: -1

launcher shortcut
  -> starts llama-server
  -> starts Hermes Desktop
  -> stops llama-server when Hermes exits
```

## 注意

この手順は、個人のWindowsローカル環境での検証結果です。
Hermes Agent Desktopやllama.cppは更新が早いため、将来のバージョンでは挙動が変わる可能性があります。

また、`approvals.mode: off` は便利ですが危険です。
AIにローカル操作権限を広く渡す設定なので、作業内容とリスクを理解したうえで使ってください。
