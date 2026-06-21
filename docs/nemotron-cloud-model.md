# クラウドNemotronを手動切替で使う（Codex不在時の代役）

普段はローカルGemmaで動かしつつ、Codexがレートリミット等で使えないときに、
NVIDIAの大型モデル **Nemotron 3 Ultra (550B)** を手動で呼び出して高度な調査・自己改善を任せる手順です。

## なぜ使うのか

- ローカルGemmaは無料・高速・プライバシー◎だが、難しい調査や長い自己改善には力不足なことがある
- Codex（OpenAI）がレートリミットで使えないときの「賢い代役」がほしい
- Nemotron 3 Ultra は [build.nvidia.com](https://build.nvidia.com) で **無料（レート制限のみ・課金なし）**、OpenAI互換、コンテキスト 1M、長時間エージェント向け設計

## 設計方針

- メインモデル（Gemma）は**変更しない**。普段はローカルGemmaのまま
- `/model` の**手動切替**で、必要なときだけNemotronに乗り換える（常時クラウドにしない）
- Codex（外部CLI）を経由しないので、Codexのレートリミットとは無縁

## 前提

- NVIDIA APIキー（無料）。`build.nvidia.com` で取得
- Hermesは NVIDIA を**組み込みプロバイダ**（`provider: nvidia`）としてサポート（`hermes model` の一覧に "NVIDIA Build" あり）

## 手順

### 1. APIキーを取得

`build.nvidia.com` → 「Try NVIDIA NIM APIs」→ NVIDIA Developer Program に無料登録（クレジットカード不要）→ メール認証 → API Keys → 「Generate Key」→ `nvapi-...` をコピー。

### 2. `.env` にキーを設定

`%LOCALAPPDATA%\hermes\.env` に追記します（秘密情報。`config.yaml` には書かない。`.env` は `.gitignore` 済み）。

```
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxx
```

### 3. `config.yaml` にエイリアスを追加

`%LOCALAPPDATA%\hermes\config.yaml` のトップレベルに追記します。**既存の `model:`（Gemma）ブロックは変更しません**。

```yaml
model_aliases:
  nemotron:                                  # /model nemotron → Nemotron 550B
    model: nvidia/nemotron-3-ultra-550b-a55b
    provider: nvidia
  gemma:                                     # /model gemma → ローカルGemmaに戻す
    model: gemma-4-12b-it
    provider: custom
    base_url: http://127.0.0.1:8080/v1
```

`provider: nvidia` は組み込みのため `base_url` は不要（クラウドの `build.nvidia.com` を自動で向き、課金ダッシュボード用ヘッダも自動付与）。キーは `.env` の `NVIDIA_API_KEY` が自動で読まれます。

### 4. 反映と確認

```powershell
$hermes = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe"
& $hermes config check          # NVIDIA_API_KEY が OK、YAMLがパスOKか
```

利用可能なモデルIDを実APIで確認（任意。TLS1.2を明示）:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$h = @{ Authorization = "Bearer $env:NVIDIA_API_KEY" }
(Invoke-RestMethod 'https://integrate.api.nvidia.com/v1/models' -Headers $h).data.id |
  Where-Object { $_ -match 'nemotron' } | Sort-Object
```

### 5. 使い方

Hermesのチャットセッション内で切り替えます（エイリアス名は補完候補に出ないので手入力）。

```
/model nemotron     # Nemotron(550B)に切替（このセッションだけ）
/model gemma        # ローカルGemmaに戻す
```

`--global` を付けない限り、切替は現在のセッション限りで、新しいセッションは自動でGemmaに戻ります（＝普段はGemmaを維持）。

## Tool callingの注意

Nemotron 3 / NVIDIA NIMはOpenAI互換APIとして使います。Gemma 4ローカル運用と同じ履歴変換を流用しないでください。

NVIDIA NIM側:

- リクエストにはOpenAI互換の `tools` を渡す
- Tool付きリクエストでは top-level に `tool_choice: auto` を付ける
- Toolがない通常会話では `tool_choice` を付けない
- モデルが返した `assistant.tool_calls` をHermes側で実行し、結果を `role: tool` として次ターンへ戻す

Gemma 4側との違い:

- Gemma 4はTool実行後の履歴を `assistant.tool_calls` / `assistant.tool_responses` へ畳み込む必要がある
- Nemotron 3は標準のOpenAI互換 `assistant.tool_calls` -> `role: tool` ループを維持する
- NIMはMCPサーバーへ直接接続しない。MCP Toolの列挙・実行・結果返却はHermes側の責務

確認用の軽いプロンプト:

```text
/model nemotron
web_search tool を使って NVIDIA NIM tool calling の公式情報を1件確認し、出典付きで要約してください。
```

確認ポイント:

- `tools` ありの呼び出しで `tool_choice: auto` が入る
- Tool結果が `role: tool` として戻る
- Tool結果の次ターンでNemotronが自然文の最終回答を返す
- `/model gemma` に戻した後、Gemma用のTool履歴形式と混ざらない

公式参照:

- NVIDIA NIM Tool Calling and MCP: https://docs.nvidia.com/nim/large-language-models/latest/advanced-use-cases/tool-calling-and-mcp.html
- NVIDIA NIM Nemotron 3 Ultra quickstart: https://docs.nvidia.com/nim/large-language-models/latest/day-0/get-started-nemotron-3-ultra.html

## 注意点

- 無料枠はレート制限あり（超過は HTTP 429 が返るだけで**課金は発生しない**）
- 出力 `max_tokens` の既定値が小さいことがある。長い生成が途中で切れる場合は設定で引き上げる
- 別途、期間限定で Nous Portal 経由の無料提供がある場合もあるが、`build.nvidia.com` 版は**恒久無料**なので恒久利用にはこちらが安心

## 確認チェックリスト

- [ ] `hermes config check` で `NVIDIA_API_KEY` が OK 表示
- [ ] `/model nemotron` で `Provider: Nvidia` に切替表示される
- [ ] 切替後にツール実行（Web検索・ファイル操作など）が動く
- [ ] `/model gemma` で元のローカルGemmaに復帰できる
