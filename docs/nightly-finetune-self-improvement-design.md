# 将来案: 夜間LoRAファインチューニングによる再帰的自己改善（設計書）

> **本書は未実装の将来案です。** 環境裏どり（実機・公式ドキュメント・Web調査）は完了しており、
> 実装に着手できる粒度まで設計を落としていますが、コードはまだ1行も書いていません。
> 実装に着手する場合は、必ず「Phase 0 スモークテスト」から始めてください。
>
> パス表記はすべて `%LOCALAPPDATA%`（= `C:\Users\<USER>\AppData\Local`）と `%USERPROFILE%` 基準です。
> 実ユーザー名・Token・ID・実会話内容はこのメモには載せません。

## 構想の1行要約

**人間が寝ている間に、その日の対話データでローカルGemmaをLoRA学習し、朝には少しだけ「うちの秘書」に近づいたモデルで起動する。**

## 1. 目的と背景

### なぜファインチューニングなのか

このガイドの本編（README §11〜13、§18〜19）で構築したローカルGemma秘書には、既知の弱点があります。
**SOUL.md・system_prompt・prefill見本会話を総動員しても、ローカル12Bモデルの口調・人格が完全には定着しない**ことです。
プロンプトで矯正する方式は、コンテキストを恒常的に消費し、長い対話の後半で素のGemmaに戻る現象も避けられません。

LoRAファインチューニングは、この弱点への根本対策です。口調・応答パターンを重みに焼き込めば、
プロンプト側の矯正コストを段階的に減らせます。タイトルの「再帰的自己改善」とは、
**エージェント自身の日々の対話が、翌日のエージェントの教師データになる**ループのことです。

### 学習する/しないの境界（重要な設計判断）

| 対象 | LoRAに焼くか | 理由 |
|---|---|---|
| 口調・人格・応答の型 | **焼く** | プロンプトで定着しきらない部分。これが主目的 |
| 対話パターン（指示への向き合い方） | **焼く** | 日々の良い応答が教師データになる |
| 事実知識（ユーザー情報・プロジェクト状況） | **焼かない** | 事実は更新され続ける。memories/MEMORY.md のコンテキスト注入が適所。LoRAに焼くと「更新不能な誤情報源」になる |

## 2. 裏どり結果（実現可能性: high）

2026年6月時点の調査結果です。検証環境は README「検証環境」と同じ
（RTX 4070 16GB / RAM 64GB級 / Windows 11 / llama.cpp b9498 CUDA版 / Gemma 4 12B IT QAT Q4_0 GGUF）。

### 成立の決め手5点

1. **学習ベース重みの存在**: [`unsloth/gemma-4-12B-it-qat-q4_0-unquantized`](https://huggingface.co/unsloth/gemma-4-12B-it-qat-q4_0-unquantized)
   — 配信中のQAT Q4_0 GGUFと**同一の重み分布をbf16展開したHF版**（約24GB）。
   ここでLoRAを学習すれば、量子化ベースへの実行時適用との整合性が最良になります。
   Gemma 4は**Apache 2.0・非ゲート**で、HFライセンス同意の壁すらありません（Gemma 3時代から大幅緩和）。
2. **unslothのGemma 4対応**: [unsloth](https://unsloth.ai/docs/models/gemma-4/train)がGemma 4をday-0サポート
   （約1.5x高速・約60%省VRAM公称）。**Windows nativeも公式対応**
   （[triton-windows](https://pypi.org/project/triton-windows/)がTriton公式に引き継がれPyPI継続公開）。
3. **LoRAの実行時適用**: llama-serverは `--lora <gguf>` / `--lora-scaled` に加え、
   **`GET/POST /lora-adapters` でのスケール切替**と**リクエスト単位の `"lora":[{"id":0,"scale":...}]` 指定**に対応
   （[server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)）。
   つまり**同一サーバーでLoRAあり/なしのbefore/after比較が1リクエスト単位でできる**。
   毎晩12B全体を再量子化する必要はなく、数百MBのアダプタGGUFを差し替えるだけで済みます。
4. **VRAM見積もり**: 12Bの4-bitロードは約8GB。QLoRA学習一式（LoRA勾配＋8bit optimizer＋活性化、
   gradient checkpointing有効・seq 2048・batch 1）で**ピーク11〜13GB**と見積もられ、16GBに収まります
   （unsloth実績: 26B-A4B QLoRAが約16GB）。
5. **変換経路**: llama.cppの `convert_lora_to_gguf.py` はPEFTアダプタ→GGUF変換に対応し、
   gemma4アーキテクチャの変換クラスも実装済み（[GGUF-my-LoRA](https://huggingface.co/blog/ngxson/gguf-my-lora)）。

### 制約・注意点

- **transformers 5.5以上が必須**（gemma4対応は2026年4月のv5.5から）。v5系は破壊的変更が多く、
  既存環境を壊さないために**学習専用venvの分離が必須**。
- llama.cppのWindowsバイナリzipにはPythonスクリプトが含まれないため、変換用に**ソースのclone**が必要。
- GGUFは直接学習できません。「HF bf16重みで学習 → アダプタだけGGUF化 → 配信側に `--lora` で適用」が唯一の現実的経路です。

## 3. アーキテクチャ全体像

```
21:35 daily-digest（既存・README §19.1）
22:10 [新] finetune-distill ……… 当日対話 → SFT JSONL蒸留
      ルールベース抽出 ＋ redaction ＋ Gemma自身による選別
      （llama-serverは既存のcronマーカー方式で起動 → reaperが30分後に自動停止）
00:30〜05:50 [新] finetune-orchestrator（10分tickの状態機械）
      ゲート判定 → llama-server明示停止（VRAM排他）
      → QLoRA学習をdetached起動 → tickで監視（heartbeat / deadline）
      → アダプタGGUF変換 → 品質ゲート（固定20問 before/after）
      → 採用なら current.json ポインタをアトミック更新
07:30 [新] finetune-morning-report …… Discordに5行要約＋Obsidianに詳細レポート
```

### なぜ「tick型の状態機械」なのか

数時間かかる学習ジョブを、cronジョブ1回で抱え込まないためです。
Hermesのcron基盤には「argvを渡せない」「長時間ジョブを前提にしていない」という制約があります。
そこで既存の自律runner（README §18の判断レイヤーと同系統の実装）が実証済みのパターンを踏襲します。
すなわち**学習プロセスはdetachedで起動し、10分ごとのtickがpid生存・heartbeat・deadlineを確認して状態を1歩ずつ進める**。
この形にすると、電源断・GPUハング・タイムアウトの検出と復旧が「再起動後の最初のtick」に自然に集約され、
専用のリカバリ処理が不要になります。

### なぜ蒸留は「書かせる」のではなく「選ばせる」のか

口調が弱いGemmaに口調の教師データを「生成させる」のは循環依存です。
一方、当日の実対話は既にinstruction-response形をしています。
そこで蒸留は**ルールベース抽出が主役**、LLMの役割は**5段階採点による選別**に限定します。
これは本編の設計思想（README §19「材料作りはルールベースに寄せる」）の延長線であり、
既存の `daily_digest.py` が持つ秘密マスク・原子的書き込みの共通基盤（`scripts\checkin_common.py`）をそのまま再利用できます。
外部API（クラウドLLM）には一切依存しません。コストゼロ・完全ローカルで回ります。

### データ蒸留の処理段

```
1. 収集    当日の対話ソースを重複防止台帳（seen_sources.json）と突合し、新規分のみ列挙
2. 抽出    ルールベースで instruction / output ペア化
3. redaction  正規表現denylist（鍵形式・token・メール・絶対パス・ID等）に1つでもヒット
              → マスクではなく「ペアごと破棄」（総量が小さいうちは安全側に倒す）
4. 選別    ローカルGemmaが各ペアを「口調らしさ／有害性／具体性」で採点、閾値未満は rejected へ
5. 重複排除  instruction+output のハッシュで既存データセットと突合
6. 追記    dataset\sft\train.jsonl へ追記（messages形式。chat template適用は学習側の責務）
7. 記録    判断JSONLログへ {distilled: N, rejected: M, redacted: K} を1行
```

## 4. 学習設計

### 学習戦略: 毎回ベースから全量再学習

| 戦略 | 採否 | 理由 |
|---|---|---|
| **全履歴データで毎回ベースから学習し直し** | **採用** | データが数千例以下のうちは数十分で終わる。忘却が構造的に起きない。アダプタ1個の管理で済みロールバックが単純 |
| 前回アダプタから継続学習 | 不採用 | 古いデータへの忘却が累積し、数十世代後の品質が予測不能 |
| アダプタを毎晩積層（--lora複数） | 不採用 | スケール調整と干渉が未検証のまま複雑化する |

学習が深夜枠（約2時間）に収まらなくなったら「直近N日全量＋古いデータのサンプリング」へ移行します。

### 推奨ハイパーパラメータ（日々数十〜数百例の小データ継続学習向け）

| 項目 | 推奨値 | 根拠 |
|---|---|---|
| rank / alpha | 16 / 16 | 小データでr=32以上は過学習リスク |
| target_modules | 言語層の attention＋MLP のみ（vision/audioタワー凍結） | テキスト用途・GGUF変換の確実性・VRAM節約 |
| learning rate | 5e-5〜1e-4（通常の2e-4より低め） | 破滅的忘却対策 |
| epochs | 2〜3（数十例時）、1〜2（数百例超） | 3超は丸暗記化のサイン |
| max_seq_len | 2048 | VRAMとのバランス |
| batch | per_device 1〜2 × grad_accum 8 | 16GB制約 |
| optimizer | paged_adamw_8bit | VRAMスパイク回避 |
| その他 | gradient checkpointing、train_on_responses_only（`<start_of_turn>model` 以降のみ損失） | 標準的安定化 |

**リプレイバッファ**: 学習データの20〜30%相当を固定の汎用日本語データから混合します。
新規データだけで回すと、口調は付いても汎用能力が削れていくためです。

### 学習環境の分離

```
%USERPROFILE%\hermes-finetune\
├── .venv\                  # uv venv --python 3.12（unsloth推奨。既存環境とは完全分離）
│                           # torch(cu12x) + triton-windows + unsloth + transformers>=5.5 + trl/peft/bitsandbytes
├── llama.cpp\              # ソースclone（convert_lora_to_gguf.py 用）
├── scripts\train_qlora.py  # 学習本体
├── scripts\eval_before_after.py
├── data\replay\            # リプレイバッファ
└── adapters\               # 学習出力（HF形式）
```

## 5. 安全装置

### なぜここまで守るのか

「寝ている間に重みが変わる」仕組みは、壊れ方も静かです。
朝起きたら秘書の口調が崩壊していた、では本末転倒なので、README §18.7（暴走と沈黙の両方を守る）と同じ思想で多層防御にします。

1. **イミュータブルなアダプタ版管理**: `adapters\versions\vNNN-YYYYMMDD\`（adapter.gguf＋manifest.json）は作成後変更しない。
   manifestにはベースモデルhash・データセットsnapshot hash・評価結果を記録。直近5版保持
2. **ポインタのアトミック更新**: 配信側が読むのは `adapters\current.json`（採用版へのポインタ＋`previous_version`）だけ。
   一時ファイル書き込み→renameで更新し、書きかけを読まれる事故を防ぐ。
   **ロールバック＝ポインタをprevious_versionへ書き戻すだけ**
3. **品質ゲート（before/after比較）**: 固定20問（口調・人格10＋指示追従5＋リグレッション5）を、
   リクエスト単位LoRAスケール指定（scale 0=ベース、1=候補）で同一サーバーに投げて比較。
   採点はヒューリスティック主体（空応答・n-gram反復・日本語比率・口調キーワード一致率）。
   **Gemma自身をjudgeにしない**（自己バイアス）。劣化検知なら候補を棄却し、currentは触らない
4. **フェイルオープン**: ポインタやアダプタが無ければ `--lora` を付けずに従来どおり起動。
   **学習基盤の故障がチャット機能を殺さない**
5. **VRAM排他**: 学習開始前にllama-serverを明示停止し、`training_lock` マーカーを置く。
   既存のオンデマンド起動ヘルパーに「lock存在時は起動拒否」のガードを足し、深夜cronとの競合を閉じる。
   デスクトップ本体が稼働中（ユーザーが夜更かし中）なら今夜の学習はスキップ
6. **電源断・ハング対策**: 学習側はheartbeatファイルを5分毎更新。tickが「pid消失かつexit記録なし」を電源断と判定、
   heartbeat 20分停滞をハングと判定してkill。05:50のハードデッドラインで強制終了（朝の利用とVRAM競合させない）
7. **連続失敗クールダウン**: 連続2回失敗で72時間停止＋Discord警告1回（既存watchdogと同パターン）
8. **判断JSONLログ**: 全tickが最低1行 `{at, decision, ...}` を書く。
   「沈黙＝正常スキップ」と「沈黙＝故障」をログで区別可能にする（README §18の黙る設計と同じ原則）

## 6. 既存基盤への変更点（最小限）

| 対象 | 変更 | 規模 |
|---|---|---|
| `scripts\start-gemma-llama-server.ps1` | `$LoraPointer` パラメータ追加＋current.json存在時のみ `$Arguments` へ `--lora` を追記 | 約10行。**ガイドrepo版と配備先（`%USERPROFILE%\.hermes\scripts\`）の2か所を同時更新** |
| LLMオンデマンド起動ヘルパー | training_lock 尊重ガード | 約3行 |
| cron jobs.json | 3ジョブ追加（distill 22:10 / orchestrator 深夜10分tick / morning-report 07:30、いずれも `no_agent: true`） | Gateway停止中に編集 |
| config.yaml / Gateway | **変更不要**（endpoint・alias・API不変。LoRAはサーバー起動引数のみ） | — |
| SOUL.md / prefill | **当面そのまま**（アダプタとの二重防御。口調定着を確認してから段階的に削減） | — |

新規スクリプト（distill / orchestrator / eval / morning-report）は `%LOCALAPPDATA%\hermes\scripts\` に、
状態・データセット・アダプタは `%LOCALAPPDATA%\hermes\finetune\` 配下に置きます。

## 7. 段階導入計画

| Phase | 内容 | 完了条件 |
|---|---|---|
| **0. スモークテスト** | venv構築→ベース重みDL（約24GB）→ダミー10例で train→convert→`--lora` 起動 | 最重要3点の実地確認: ①unslothがWindowsで動く ②gemma4アダプタのGGUF変換が通る ③配信中のllama.cppビルドでLoRAがロードできる。VRAMピーク実測 |
| **1. データパイプラインのみ** | distillジョブだけ稼働 | 3日分の蒸留結果を人間が目視し、redaction漏れゼロ＋品質が学習に値すると確認 |
| **2. 手動1サイクル** | 日中に手動で 学習→評価→適用 | 口調変化を体感確認＋**ロールバック演習を必ず実施** |
| **3. 半自動** | 夜間に学習・評価まで自動。**採用だけ人間承認**（朝レポートのfrontmatter書き換え） | 連続2サイクル成功＋電源断シミュレーション1回成功 |
| **4. 完全自動** | 品質ゲート通過で自動採用 | 4週間無事故で継続。劣化1回でPhase 3へ差し戻し |

### スキップ条件の初期値

現状の日次データ量は小さいため、`新規24例未満なら学習しない`＋`前回学習から3日未満なら学習しない` で始めます。
実効的には週1〜2回の学習となり、**「学習が走らない夜」が大半なのが正常動作**です（判断ログに skip 理由が残ります）。

## 8. リスクと未確定事項

1. **`convert_lora_to_gguf.py` × gemma4（unified形式）の実地未検証** — 最大の未知数。
   クラス対応は確認済みだが、マルチモーダル統合チェックポイントのテンソル名マッピングはPhase 0で必ず確認。
   NGならllama.cpp更新、それでもダメなら「PEFTマージ→GGUF再変換→再量子化」の重量級パスへ
2. **QAT Q4_0ベース＋実行時LoRAの品質** — QAT（量子化を前提に学習された重み）への実行時LoRA加算は理論上の劣化要因あり。
   カナリアテスト（学習データにしか無い応答パターンのQA）で実測し、問題があればマージ＋再量子化パス
   （毎晩+20分程度）またはベースGGUFの変更で対処
3. **unsloth Windows nativeの安定性** — triton↔torchのバージョン対応を厳守。
   NGなら transformers+peft素組み（triton非依存・低速だが12B小データなら許容）またはWSL2
4. **PCの夜間スリープ設定** — cronはプロセスが生きていることが前提。スリープするなら
   「PCを起こすだけのScheduled Task（wake timer）」を併設（ジョブ本体はcronのまま）
5. **データ量の絶対的不足期** — 最初の数週間は学習材料が足りない。閾値ゲートで「無理に学習しない」を保証し、
   蒸留の採用/棄却率を判断ログで定点観測する

## 関連資料

- README §11（QAT Q4_0へ確定した理由）、§18〜19（cron判断レイヤー・人間らしさ4本柱）
- `docs/human-like-behavior.md` — 共通基盤 `checkin_common.py`（秘密マスク・原子的書き込み）の説明
- unsloth Gemma 4ガイド: https://unsloth.ai/docs/models/gemma-4/train
- llama.cpp server README（--lora / /lora-adapters）: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- GGUF-my-LoRA（PEFT→GGUF変換の解説）: https://huggingface.co/blog/ngxson/gguf-my-lora
