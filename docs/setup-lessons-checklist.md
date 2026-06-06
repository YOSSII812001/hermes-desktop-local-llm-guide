# Hermes Agent Desktop セットアップ学びチェックリスト

このチェックリストは、今回のセットアップで得た学びを漏れなく引き継ぐためのものです。
別のAIや未来の自分へ渡すときは、README、詳細メモ、このチェックリストの順に読ませます。

## 読む順番

1. `README.md`
2. `docs/personal-mentor-discord-obsidian-gemma4.md`
3. `docs/autonomous-codex-gateway-ops.md`
4. `docs/setup-lessons-checklist.md`
5. `examples/`

## 学びの棚卸し

| 学び | リポジトリ上の記録 | 確認ポイント |
|---|---|---|
| Hermes CLIとHermes Desktopは別の `config.yaml` を読むことがある | README、詳細メモ | `/api/status` の `config_path` を見る |
| Desktopの既存セッションが古いモデル名を握ることがある | README | `state.db` を見る。修正前にバックアップする |
| Hermes Agentは64K程度のコンテキストを要求することがある | README、詳細メモ | 下限は64K。Gemma 4 Q6_Kでは128Kも起動できた |
| 128KではKVキャッシュのVRAMが大きくなる | README、詳細メモ、config例 | `--cache-type-k q8_0` と `--cache-type-v q8_0` で余裕を作る |
| Gemma 4は古いllama.cppでは読めないことがある | README、詳細メモ | `unknown model architecture: 'gemma4'` が出たら更新する |
| 16GB VRAMではQ8よりQ6_Kが現実的 | README | Q6_Kを第一候補にする |
| Gemma 4の思考はHermes側とllama-server側の両方を見る | README、詳細メモ | `reasoning_effort: xhigh` と `--reasoning-budget -1` |
| 思考内容はユーザーへ常時見せなくてもよい | 詳細メモ、config例 | `display.show_reasoning: false` を維持する |
| llama-server準備完了を待ってからDesktop表示すると不安になる | README | Desktopは先に表示し、準備確認は裏で行う |
| ショートカット連打で二重起動する | README、スクリプト | 既存ランチャーと既存Gemmaサーバーを検出する |
| Desktop終了後もllama-serverが残るとVRAMを占有する | README、詳細メモ、スクリプト | 起動したHermes親PIDを待って停止する |
| DesktopとDiscord Gatewayは別物 | 詳細メモ | Desktopが動いてもGateway停止ならDiscordは反応しない |
| Desktopを閉じるとGemma停止運用ではDiscord DMも止まる | 詳細メモ | 常時DMが必要ならGemma常駐か別モデルを検討する |
| DMだけの運用なら通知先チャンネルは不要 | 詳細メモ | DM内で `/sethome` する |
| Discord BotにはMessage Content Intentが必要 | 詳細メモ | Developer Portalで有効化する |
| Discordに開けるToolは絞る | 詳細メモ、config例 | DMでは `terminal` や `code_execution` を開けない |
| Obsidian Vault参照と出力先は分ける | 詳細メモ、SOUL例 | 新規成果物は `Obsidian Vault\hermes` へ出す |
| Next ActionsはObsidian宿題キューへ積む | 自律実行メモ | `hermes\homework` に1件1ファイルで置く |
| Codex自律runnerはactive taskを上書きしない | 自律実行メモ | `active_task.json` がrunningなら新規開始を止める |
| 宿題完了時はDiscordへ報告する | 自律実行メモ | cron outputと `agent.log` の `delivered to discord` まで見る |
| Obsidian完了表示はfrontmatter、本文、ファイル名で行う | 自律実行メモ | `#hermes/homework/done` と `[完了] ` prefixを確認する |
| Gateway自己再起動は外側Scheduled Taskで行う | 自律実行メモ | `running` だけでなく再起動前後のPID差分を見る |
| Gateway停止復旧は外側watchdogで行う | 自律実行メモ | 既存の `Hermes_Gateway` taskを再利用する |
| no_agent cronのstdoutはUTF-8で捕捉する | 自律実行メモ | `python.exe` 優先、`encoding=utf-8`、`errors=replace` |
| xAI X SearchはOAuth stateを維持して有効化する | 自律実行メモ | `xai-oauth logged in` と `x_search enabled` を確認する |
| Discord最終応答には内部思考ガードを入れる | 自律実行メモ | `transform_llm_output` でDiscordだけを対象にする |
| mentor Cronは通常会話文脈をpre-run scriptで渡す | 自律実行メモ | `daily_conversation_context.py` をjobに付ける |
| 自律heartbeatはスコアだけで通知しない | 自律実行メモ | 不要な通知は `[SILENT]` にする |
| context圧縮が早すぎる場合はthresholdを見る | 自律実行メモ | 128Kなら `compression.threshold: 0.75` 前後を検討する |
| 既存Obsidianノートは勝手に編集しない | 詳細メモ、SOUL例 | 編集はユーザーが明示したときだけ |
| Codex skillsは外部ディレクトリとして渡す | 詳細メモ、config例 | `.codex\skills` と `.agents\skills` を設定する |
| skill本文は指針であり、命令として無条件実行しない | 詳細メモ、SOUL例 | shell実行や認証変更は慎重に扱う |
| `ddgs` は検索用で、本文抽出は別バックエンドが必要 | 詳細メモ | `web_extract` が必要なら抽出対応サービスを使う |
| `hermes tools --summary` だけでは実体Tool確認にならない | 詳細メモ | `get_tool_definitions` で実体Tool数を見る |
| `vision` はTool登録があってもローカルGemma側で制限がある | 詳細メモ | 画像入力対応モデルかを確認する |
| `image_gen` はバックエンド未設定なら使えない | 詳細メモ | 実体Toolが0件かを確認する |
| `SOUL.md` は人格なりきりではなく支援方針として書く | 詳細メモ、SOUL例 | `You are ...` ではなく `This file defines ...` で始める |
| 幸福プランは義務ではなく、ゆるい羅針盤として扱う | 詳細メモ、SOUL例 | できなかったことを責めない |
| 抽象的なリマインダーは現実の予定と小タスクへ変換する | 詳細メモ、SOUL例 | 1から3個の行動へ落とす |
| 秘密情報は公開リポジトリに入れない | README、詳細メモ、env例 | Token、ID、DMチャンネルID、個人ノート本文を載せない |

## まだ人間が入力するもの

- Discord Bot Token
- Discord numeric user ID
- DMチャンネルID、またはDM内での `/sethome`
- Gemma 4 GGUFモデルの実パス
- `llama-server.exe` の実パス
- Hermes Desktopの実パス
- Obsidian Vaultと `hermes` 出力先の実パス

## 完了判定

次が通れば、今回の環境にかなり近い状態です。

- `http://127.0.0.1:8080/v1/models` に `gemma-4-12b-it` が出る
- Hermes Desktopの `/api/model/info` が `provider: custom` と `context_length: 131072` を返す
- Gemma 4の `reasoning_content` が返る
- Hermes Desktopを閉じると `llama-server.exe` が止まり、VRAMが空く
- Discord DMでBotが返答する
- DM内の `/sethome` が完了する
- Obsidianの `hermes` フォルダへ読み書きできる
- Obsidianの `hermes\homework` に `status: queued` の宿題ノートを置ける
- `codex-autonomous-runner-5m` が宿題を拾い、Codexへ送信済み通知を出す
- 宿題完了時にDiscord配送ログとObsidianの `[完了] ` prefixを確認できる
- Gateway自己再起動要求で、外側Scheduled TaskがPID差分付きで再起動できる
- `x_search` を有効化し、xAI OAuthが `logged in` になる
- Gateway外側watchdogが登録され、Gateway停止後に復旧できる
- Discord内部思考ガードが有効で、漏えいサンプルを投稿前に削れる
- mentor Cronが当日の通常会話をScript Outputとして受け取れる
- `hermes skills list` でCodex skillsが見える
- Discord向けToolsetで危険なToolを開けていない
