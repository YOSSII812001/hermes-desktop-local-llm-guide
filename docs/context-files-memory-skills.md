# Hermesのコンテキストを役割別に整理する

結論から言うと、`SOUL.md` は人格と話し方だけに使います。
利用者情報、環境情報、作業手順を全部入れるファイルではありません。

Hermesには、情報の性質に合った保存先があります。
保存先を分けると、起動時の指示が短くなり、ローカルLLMも迷いにくくなります。

この文書は、次の警告を根本から解消するための設計ガイドです。

```text
Context file SOUL.md TRUNCATED: 20157 chars exceeds limit of 20000
```

## 1. 情報の置き場所

まず、次の表で保存先を決めてください。

| 情報 | 保存先 | 読み込まれる時期 | 例 |
|---|---|---|---|
| Hermesの人格、口調、応答姿勢 | `SOUL.md` | セッション開始時 | 結論を先に述べる、過度に砕けない |
| 利用者の好み、期待、仕事の進め方 | `USER.md` | セッション開始時 | 日本語を使う、短い報告を好む |
| 環境の事実、慣例、学んだ注意点 | `MEMORY.md` | セッション開始時 | Windowsを使う、設定の正本パス |
| プロジェクト固有の規則 | `.hermes.md` または `AGENTS.md` | 作業場所に応じて読込 | テストコマンド、編集禁止ファイル |
| 特定作業の詳しい手順 | `skills/<name>/SKILL.md` | 必要になったとき | Codex委譲、Obsidian保存、再起動 |
| 接続先、モデル、機能の有効化 | `config.yaml` | Hermes起動時 | モデル、Discord、skill binding |
| APIキーやBot Token | `.env`、OSの資格情報管理 | 必要な処理の実行時 | Discord Token、外部APIキー |
| 長い資料や履歴 | 外部文書、Obsidian、リポジトリ | 必要になったとき | 設計書、日報、調査資料 |

同じ内容を複数の場所へ書かないでください。
重複した指示は更新漏れと矛盾を生みます。

### 判断に迷ったとき

次の順に考えると、保存先を決めやすくなります。

1. 秘密情報なら、Markdownへ書かず資格情報として保存します。
2. すべての会話へ必要な人格情報なら、`SOUL.md`へ置きます。
3. 利用者自身の情報なら、`USER.md`へ置きます。
4. 環境や運用上の事実なら、`MEMORY.md`へ置きます。
5. 特定プロジェクトだけの規則なら、プロジェクト文書へ置きます。
6. 特定作業だけの手順なら、skillへ置きます。
7. 長い参考情報なら、外部文書へ置き、skillから参照します。

## 2. 各ファイルの役割

### SOUL.mdは人格と話し方だけにする

`SOUL.md` は、Hermesインスタンスの基本人格です。
公式Docsでは、システムプロンプトの先頭に入る識別情報とされています。

適している内容は次のとおりです。

- 口調と温かさ
- 回答の詳しさ
- 不確実な情報の伝え方
- 反対意見の示し方
- 避けたい言い回し
- すべての会話に共通する応答姿勢

次の内容は入れません。

- ファイルパス
- コマンドやポート番号
- プロジェクトの構成
- Codexへ委譲する詳しい条件
- Obsidianへ保存する詳しい手順
- Discord専用の運用手順
- 一時的なタスクや進捗
- APIキーや識別子

短い例は [SOUL.private-mentor-secretary.md](../examples/SOUL.private-mentor-secretary.md) を参照してください。

### USER.mdは利用者のプロフィールにする

`USER.md` は、Hermesが利用者について知っておく情報です。
公式上限は1,375文字です。

次のような情報を保存します。

- 使用言語
- 説明の好み
- 報告の受け取り方
- 意思決定の傾向
- 支援時に配慮すること
- 継続的な仕事の進め方

プロジェクトの状態や長い経歴は保存しません。
短く、現在も有効な情報だけを残してください。

例は [USER.private-mentor-secretary.md](../examples/USER.private-mentor-secretary.md) にあります。

### MEMORY.mdは環境の事実と学びにする

`MEMORY.md` は、Hermes自身が覚えておく運用上の事実です。
公式上限は2,200文字です。

適している内容は次のとおりです。

- OSや利用環境
- 設定ファイルの正本
- よく使うプロジェクトの場所
- 繰り返し役立つ慣例
- 過去に判明したツールの癖
- 次回も必要な短い判断材料

ログ全文、会話全文、設計書、秘密情報は保存しません。
すぐ再取得できる一般知識も保存対象ではありません。

例は [MEMORY.local-environment.md](../examples/MEMORY.local-environment.md) にあります。

### プロジェクト文書は作業場所の規則にする

Hermesは、作業ディレクトリからプロジェクト文書を探します。
セッション開始時は、最初に見つかった1種類だけを使います。

優先順位は次のとおりです。

1. `.hermes.md` または `HERMES.md`
2. `AGENTS.md`
3. `CLAUDE.md`
4. `.cursorrules` または `.cursor/rules/*.mdc`

`SOUL.md` はこの競合には含まれません。
Hermesホームにあるグローバルな `SOUL.md` が独立して読み込まれます。

`AGENTS.md`には、次の内容が適しています。

- プロジェクトの目的と構成
- 実行するテストコマンド
- 編集してはいけないファイル
- ブランチやレビューの規則
- その作業場所だけで有効なパス
- ツールの利用方針

サブディレクトリの文書は、関連ファイルへ移動したときに段階的に読み込まれます。
起動時に全プロジェクトの規則を詰め込む必要はありません。

Hermesホーム向けの例は [AGENTS.hermes-home.md](../examples/AGENTS.hermes-home.md) にあります。

### skillsは必要な作業手順だけを持つ

skillは、必要なときだけ開く手順書です。
Hermesは起動時にskillの一覧だけを読み、本文は必要になってから読みます。

この仕組みを段階的開示と呼びます。
長い手順を常時読み込まないため、プロンプトを節約できます。

skillに適している内容は次のとおりです。

- 作業を始める条件
- 実行手順
- 読むべき補助文書
- 検証方法
- 失敗時の復旧手順
- その作業に固有の安全上の注意

1つの巨大skillにすべてを集めないでください。
入口skillを短くし、詳細は目的別skillや参照文書へ分けます。

## 3. SOUL.mdが肥大化する理由

SOULが大きくなる主な原因は、役割の異なる情報を追記し続けることです。

典型的には、次の順で肥大化します。

1. 最初に人格と口調を書く。
2. Discordの使い方を追記する。
3. Obsidianの保存先と操作手順を追記する。
4. Codex委譲や再起動手順を追記する。
5. 過去の失敗と一時的な対応を追記する。
6. 同じ注意を別の表現で重ねる。

結果として、毎回不要な手順までシステムプロンプトへ入ります。
小さいローカルモデルほど、重要な人格指示を見失いやすくなります。

### 文字数上限と切り詰め

公式のContext Filesガイドは、既定上限を20,000文字と説明しています。
上限を超えると、Hermesは先頭70%と末尾20%を残して中央を省略します。

Hermes v0.18.2のコードには、モデルのコンテキスト長から上限を計算する処理もあります。
この処理は20,000文字を下限、500,000文字を上限にします。
`config.yaml`に明示値があれば、その値が優先されます。

バージョンやモデル情報の渡り方により、実際の上限は変わります。
警告に表示された数値を、その実行環境の上限として扱ってください。

```yaml
# 必要な場合だけ明示します。
# 肥大化したSOULを残すための設定にはしません。
# context_file_max_chars: 20000
```

通常は未設定のままにし、Hermesの既定計算へ任せます。
上限を引き上げても、不要な指示が毎回入る問題は残ります。
先にファイルを役割別に分けてください。

### 実際の整理例

Windows DesktopとローカルGemmaを使う環境では、次の結果になりました。
数値は、2026年7月に確認した1環境の実測値です。

| 対象 | 整理前 | 整理後 |
|---|---:|---:|
| `SOUL.md` | 20,178文字 | 1,214文字 |
| `USER.md` | 未分離 | 545文字 |
| `MEMORY.md` | 運用情報と秘密が混在 | 871文字 |
| `AGENTS.md` | 情報がSOULへ混在 | 1,346文字 |
| 主な運用skill | 13,554文字 | 3,527文字 |
| Discordの自動読込 | 6 skills、約26,700文字 | 入口skill 1つ、1,040文字 |

整理では、人格情報だけをSOULへ残しました。
利用者情報、環境情報、運用規則、作業手順は別の保存先へ移しました。

また、記憶ファイル内に平文の連携Tokenが見つかりました。
値を削除し、記憶ファイルを含まない安全なバックアップへ切り替えました。
実際の運用では、漏えいの可能性を確認してTokenも再発行してください。

整理後は、同じ20,000文字の上限を変えずに警告が止まりました。
この結果からも、上限変更より情報の再配置を先に行うべきだと分かります。

## 4. Discordでは小さい入口skillだけを自動読込する

専用のDiscord DMやチャンネルでは、`channel_skill_bindings`を使えます。
この設定は、新しいセッションの開始時にskill本文をユーザーメッセージとして注入します。

公式Docsの公開例はSlack向けです。
Hermes v0.18.2の実装では、DiscordとSlackの両方がこの設定を受け取ります。

skill選択を小さいローカルモデルへ任せたくない場合に有効です。
ただし、複数の大きなskillを束ねると、再びプロンプトが肥大化します。

次のように、小さい入口skillを1つだけ指定してください。

```yaml
discord:
  channel_skill_bindings:
    - id: "<DISCORD_DM_OR_CHANNEL_ID>"
      skills:
        - hermes-discord-core
```

入口skillは、依頼の種類と参照先だけを定義します。
実作業の手順は別のskillへ任せます。

例は [hermes-discord-core.SKILL.md](../examples/hermes-discord-core.SKILL.md) にあります。

### 設定が反映される時期

bindingは、新しいセッションか自動リセット時だけ読み込まれます。
設定やskillを変更した後は、対象チャンネルで `/new` を実行してください。

Gatewayの再起動だけでは、進行中のセッション履歴は更新されません。
変更後の検証は、必ず新しいセッションで行います。

### ローカルLLMでの注意

ローカルLLMは、skillの自動選択や長い指示への追従が弱い場合があります。
次の順で安定性を高めてください。

1. `SOUL.md`を短くする。
2. Discord用の入口skillを1つにする。
3. 入口skillから目的別skillへ分岐させる。
4. 同じ依頼を新しいセッションで複数回試す。
5. 実際に選んだコマンドやskillをログで確認する。

skillを登録しただけで、必ず正しく使われるとは限りません。
実際のモデルとGateway経路で確認してください。

## 5. 安全な移行手順

### 1. 実際のHermesホームを確認する

Windows Desktopでは、通常 `%LOCALAPPDATA%\hermes` を使います。
ただし、別プロファイルや環境変数で変わる場合があります。

Desktopの状態APIが使える場合は、次で正本を確認します。

```powershell
Invoke-RestMethod http://127.0.0.1:9120/api/status |
  ConvertTo-Json -Depth 8
```

`config_path`とプロファイル情報を確認してください。
推測した別フォルダへ同じ変更を重ねないでください。

### 2. 秘密情報を除外してバックアップする

バックアップには、認証ファイルやデータベースを含めません。
対象は、これから編集する設定文書とskillだけに絞ります。

```powershell
$hermesHome = Join-Path $env:LOCALAPPDATA 'hermes'
$backup = Join-Path $env:TEMP 'hermes-context-backup'
New-Item -ItemType Directory -Path $backup -Force | Out-Null

Copy-Item (Join-Path $hermesHome 'SOUL.md') $backup
Copy-Item (Join-Path $hermesHome 'config.yaml') $backup
```

`.env`、`auth.json`、`state.db`、lockファイルはコピーしません。
記憶ファイルに秘密情報がある場合も、そのまま公開用バックアップへ入れないでください。

### 3. SOUL.mdを分類する

既存の各段落へ、次の印を付けます。

- `S`: 人格と話し方
- `U`: 利用者情報
- `M`: 環境の事実や学び
- `A`: プロジェクトや運用の規則
- `K`: 特定作業の手順
- `D`: 長い資料や履歴
- `X`: 秘密情報または不要な内容

`S`だけを`SOUL.md`へ残します。
ほかの内容は対応する保存先へ移します。

### 4. 重複と古い情報を削る

移動後に、同じ意味の指示を検索してください。
正本を1つに決め、ほかの重複を削ります。

一時的な障害、完了済みタスク、古いパスは残しません。
必要な教訓だけを短い事実へ書き換えます。

### 5. 文字数を確認する

```powershell
$hermesHome = Join-Path $env:LOCALAPPDATA 'hermes'
$targets = @(
  (Join-Path $hermesHome 'SOUL.md'),
  (Join-Path $hermesHome 'memories\USER.md'),
  (Join-Path $hermesHome 'memories\MEMORY.md')
)

$targets | ForEach-Object {
  [pscustomobject]@{
    File = $_
    Chars = (Get-Content -LiteralPath $_ -Raw).Length
  }
}
```

`USER.md`は1,375文字以内、`MEMORY.md`は2,200文字以内にします。
`SOUL.md`は上限より十分に短く保つことを推奨します。

### 6. 設定とskillを確認する

Hermes CLIの場所はインストール方法で異なります。
PATHが通っている場合は、次を実行してください。

```powershell
hermes config check
hermes mcp list
hermes skills list
hermes prompt-size --platform discord --json
```

`prompt-size`が使えない旧版では、ファイルの文字数と起動ログを確認します。

### 7. 新しいセッションで動作を確認する

対象のDiscordチャンネルで `/new` を実行します。
次の観点を1つずつ確認してください。

- SOULの口調を維持している
- 利用者の好みを反映している
- 環境の事実を正しく参照する
- プロジェクト規則を作業場所に応じて読む
- Discordの入口skillから正しい手順へ分岐する
- 起動時に切り詰め警告が出ない

一度に複数の観点を試すと、原因を特定しにくくなります。

## 6. 秘密情報を見つけた場合

Markdown内にTokenやAPIキーを見つけたら、次の順で対処します。

1. ファイルから秘密情報を削除する。
2. `.env`または資格情報管理へ移す。
3. 漏えいの可能性があれば、発行元で無効化して再発行する。
4. Git履歴や共有バックアップへの混入を確認する。
5. 記憶には、秘密そのものではなく保存場所だけを残す。

秘密情報を削除しただけでは、漏えいリスクは消えません。
外部へ出た可能性がある場合は、必ずローテーションしてください。

## 7. よくある失敗

### 上限だけを引き上げる

警告は消えても、毎回不要な手順を読む問題は残ります。
まず役割ごとに分割してください。

### SOUL.mdへ安全規則を全部入れる

すべての会話へ必要な短い姿勢だけなら問題ありません。
具体的なコマンド、パス、復旧手順は`AGENTS.md`かskillへ置きます。

### Discordへ複数の巨大skillを自動読込する

bindingしたskillはセッション履歴へ入ります。
入口skillを1つにして、必要な手順だけ後から読みます。

### 設定変更後も同じセッションで試す

記憶とchannel skill bindingは、セッション開始時のスナップショットです。
`/new`を実行してから確認してください。

### 公開サンプルへ実値をコピーする

実Token、Discord ID、OAuth callback、利用者名を公開しないでください。
公開文書では、`<USER>`や`<DISCORD_CHANNEL_ID>`へ置き換えます。

## 8. 公式リファレンス

- [Use SOUL.md with Hermes](https://hermes-agent.nousresearch.com/docs/guides/use-soul-with-hermes/)
- [Context Files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files)
- [Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
- [Work with Skills](https://hermes-agent.nousresearch.com/docs/guides/work-with-skills/)
- [Configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)
- [Slack: Per-Channel Skill Bindings](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/slack/#per-channel-skill-bindings)
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

この文書の実装確認には、Hermes Agent v0.18.2も使用しました。
Hermesは更新が速いため、変更前に公式Docsと使用中のコードを再確認してください。
