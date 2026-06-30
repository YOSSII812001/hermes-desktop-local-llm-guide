# Life RPG イベント画像のマッピングと配送

このメモは、Life RPGのイベント画像をHermes Agent DesktopとSubstack下書き運用へつなぐための公開向け手順です。

## 結論

画像IDの正本は、Hermes Agent側ではなくLife RPG本体にあります。

Life RPG本体は、次の2つを正本として画像を選びます。

- `%LOCALAPPDATA%\hermes\rpg_system\assets\images\events\manifest.json`
- `%LOCALAPPDATA%\hermes\rpg_system\life_rpg_engine.py`

Hermes Agent Desktopは、`image_id` から画像を再検索しません。
Life RPGが通知payloadに載せた `event_image.path` または `image_path` を受け取り、本文末尾の `MEDIA:<local_path>` として配送します。

## 画像セット

標準構成は150枚です。

| 種類 | 枚数 | 用途 |
|---|---:|---|
| 既存カード画像 | 100 | 敵、クエスト、アイテム、称号、デッキ、ステータス、ボス |
| 自律イベント画像 | 40 | 報酬箱、支援者、回復拠点、選択分岐、Anti-Vision、ボス進捗、Cron監視 |
| Substack記事用UI画像 | 10 | HUD、クエストログ、報酬ポップアップ、スキルツリー、休息メニュー |

`manifest.json` の各assetは、主に次の値を持ちます。

| キー | 役割 |
|---|---|
| `id` | 通知payloadへ出る画像ID |
| `file` | PNGファイル名 |
| `category` | `enemy` / `quest` / `event` など |
| `variant` | `encounter` / `start` / `signal` / `ok` など |
| `linked_entity` | Life RPG上の意味。例: `event:cron_watchdog` |
| `sha256` | ファイル重複や破損の検証用 |

## Life RPG側の選択ロジック

Life RPG本体では、`life_rpg_engine.py` がイベント種別を `linked_entity` に寄せます。

代表例:

| イベント種別 | `linked_entity` |
|---|---|
| `loot_hint` | `event:loot_hint` |
| `reward_reveal` | `event:reward_reveal` |
| `companion_signal` | `event:companion_signal` |
| `sanctuary_signal` | `event:sanctuary_signal` |
| `choice` | `event:choice` |
| `anti_vision` | `event:anti_vision` |
| `boss_progress` | `event:boss_progress` |
| `cron_watchdog` | `event:cron_watchdog` |
| `ui_overlay` | `event:ui_overlay` |

流れは次の通りです。

1. `event_event_image(kind, variant)` がイベント種別を `linked_entity` に変換する。
2. `event_image_by_entity(linked_entity, variant, category)` が `manifest.json` からassetを探す。
3. PNGファイルが存在するときだけ、絶対パス付きの `event_image` を返す。
4. `attach_event_image()` が通知payloadへ `event_image`、`image_id`、`image_file`、`image_path` を載せる。

該当する専用イベント画像が無い場合は、既存の敵・クエスト・デッキ・ステータス画像へfallbackします。

## Hermes Agent側の配送ロジック

Hermes Agent側は、画像IDを解決しません。

Life RPGのDiscord配送helperは、通知payloadから画像パスを取り出します。

優先順:

1. `event_image.path`
2. `image_path`

画像ファイルが存在するとき、`hermes_desktop_send.py` は本文末尾に次の行を足します。
実際のpayloadでは、環境変数ではなく展開済みの絶対パスを使います。

```text
MEDIA:C:\Users\<USER>\AppData\Local\hermes\rpg_system\assets\images\events\event-cron-clocktower-ok.png
```

Hermes Agent Desktopの `send_message` は、`MEDIA:<local_path>` を添付ファイルとして扱います。
Gateway側では安全なパスだけが残り、Discordなどのplatform adapterへ画像として渡されます。

## 許可ディレクトリ

厳格モードで画像配送を安定させるには、Hermesの設定にイベント画像ディレクトリを登録します。
設定ファイルには、環境変数ではなく展開済みの絶対パスを書きます。

```yaml
gateway:
  media_delivery_allow_dirs:
    - "C:\\Users\\<USER>\\AppData\\Local\\hermes\\rpg_system\\assets\\images\\events"
```

実際の設定ファイルは環境によって異なります。
Desktopが読んでいる設定は、Gateway status APIの `config_path` を見て確認してください。

```powershell
Invoke-RestMethod http://127.0.0.1:9120/api/status |
  ConvertTo-Json -Depth 8
```

## Substack下書き用コピー

Substack下書き作成では、画像を記事本文へ貼るためにローカルコピーを使うことがあります。

標準例:

```text
%USERPROFILE%\liferpg-cards
```

このフォルダを使う場合は、Life RPG本体の画像フォルダと同じ150枚構成に同期します。

```powershell
$Source = "$env:LOCALAPPDATA\hermes\rpg_system\assets\images\events"
$Cards = "$env:USERPROFILE\liferpg-cards"

New-Item -ItemType Directory -Path $Cards -Force | Out-Null
Copy-Item -LiteralPath "$Source\manifest.json" -Destination "$Cards\manifest.json" -Force
Copy-Item -LiteralPath "$Source\prompts.jsonl" -Destination "$Cards\prompts.jsonl" -Force
Get-ChildItem -LiteralPath $Source -Filter "*.png" -File |
  Copy-Item -Destination $Cards -Force
Get-ChildItem -LiteralPath $Cards -Filter "*.png" -File |
  Sort-Object Name |
  ForEach-Object { "assets/images/events/$($_.Name)" } |
  Set-Content -LiteralPath "$Cards\_list.txt" -Encoding UTF8
```

Substack側の記事テーマに応じて、`manifest.json` の `category` / `linked_entity` を見て画像を選びます。
報酬箱、支援者、回復拠点、選択分岐、Anti-Vision、ボス進捗、Cron監視、UI解説の記事では、`category: event` の画像を優先できます。

## 検証

画像セットの件数と分類を確認します。

```powershell
@'
import json
import os
from pathlib import Path

base = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "rpg_system" / "assets" / "images" / "events"
data = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
assets = data.get("assets", [])

print({
    "manifest_assets": len(assets),
    "manifest_events": sum(1 for asset in assets if asset.get("category") == "event"),
    "png": len(list(base.glob("*.png"))),
    "event_png": len(list(base.glob("event-*.png"))),
})
'@ | py -3 -
```

期待値:

```text
manifest_assets = 150
manifest_events = 50
png = 150
event_png = 50
```

代表的なdry-runです。

```powershell
$Root = "$env:LOCALAPPDATA\hermes\rpg_system"

py -3 "$Root\life_rpg_engine.py" autonomy --phase watchdog --slot 22:40 --date 2026-06-28 --dry-run
py -3 "$Root\life_rpg_engine.py" autonomy --phase reward --slot 22:10 --date 2026-06-28 --dry-run
py -3 "$Root\life_rpg_engine.py" reminder --slot 17:00 --date 2026-06-28 --dry-run
```

確認する値:

- `event_image.category` が `event` になる。
- `image_id` が `event-*` 形式になる。
- `image_path` のPNGファイルが存在する。

## 事故を避けるポイント

- Hermes Agent側に、Life RPG画像IDの別マッピング表を増やさない。
- `image_id` は表示・ログ・重複判定用と考える。
- 実配送は `image_path` と `MEDIA:<local_path>` の流れで確認する。
- 公開repoには実token、Discord ID、OAuth callback、個人ノート本文を入れない。
- Windowsローカルの実パスを書くときは、公開手順では `%LOCALAPPDATA%` と `%USERPROFILE%` に置き換える。
