# Hermes Agent Desktop を人間らしくする設定メモ（記憶・ゆらぎ・調子・文体）

このメモは、ローカルLLM（12B）の個人メンター秘書を「もう一段だけ人間らしく」するための設定集です。
README.mdの第18章（cronの黙る判断）を前提に、その上へ4本柱を足しています。

別のAIや未来の自分へ渡すときは、README → 各詳細メモ → このメモ、の順で読ませてください。

## 全体像：4本柱と設計思想

足したのは次の4本柱と、1つの付随修復です。

- 柱1: 記憶とフォローアップ（日次ダイジェスト＋未解決トピック）
- 柱2: 時間のゆらぎと生活リズム（配送時刻のゆらぎ＋曜日・書き出しヒント）
- 柱3: 感情・調子への寄り添い（疲労傾向のトラッキングとトーン調整）
- 柱4: 会話の自然さ（SOUL.md / SKILL.md への指針追記）
- 付随修復: `no_agent: false` cron はLLM可用性が前提という罠の解消

実装の判断軸は3つでした。

**なぜルールベースで、LLM呼び出しを増やさないのか。**
理由は2つあります。1つは壊れにくさ。llama-serverが停止していても、要約や文脈組み立てが動き続けます。
もう1つはコスト。要約のためにわざわざ推論を1回足す必要がありません。
12Bローカルモデルは、材料さえ整えればそれを文章化するのは得意なので、材料作りはルールベースに寄せました。

**なぜ1日1フォローなのか。**
しつこさは人間らしさの敵だからです。
「あの件どうなりました？」を毎チェックインで言う秘書は、人間味どころか機械じみて重い。
だから「1日に触れる未解決トピックは最大1件」を、LLMの自制ではなく構造で保証しました。

**なぜ減点方式なのか。**
「遠慮」を点数で表すためです。
加点で割り込みたい気持ちを作り、減点で「でも今は控えよう」を作る。
疲労トレンドも、新しい割り込み理由を増やすのではなく、既存スコアから引くだけにしました。

新スクリプトの共通基盤は `scripts\checkin_common.py` です。
秘密マスクの正規表現・語彙辞書・原子的な書き込み・`state.db` の読み取りをここに集約しています。
個々のスクリプトはこの基盤を呼ぶだけにして、マスク漏れや書き込み競合を1箇所で防いでいます。

> パス表記はすべて `%LOCALAPPDATA%`（= `C:\Users\<USER>\AppData\Local`）基準です。
> 実ユーザー名・Token・ID・実会話内容はこのメモには載せません。

## 柱1: 記憶とフォローアップ

### 仕組み

夜に1回、当日の会話を要約して翌日へ橋渡しします。

- `scripts\daily_digest.py`（`no_agent` cron `35 21 * * *`）が `state.db` の当日会話（user と assistant、cron発話は除外）をルールベース要約
- 出力1: `memories\diary\YYYY-MM-DD.md`（秘密マスク済みの日記）
- 出力2: `cron\open_loops.json`（未解決トピック一覧）

open_loops のライフサイクルは次のとおりです。

- 起こす: `OPEN_LOOP_TERMS`（「確認して」「あとで」「続き」等）を含むユーザー発話から、トピック単位で `open` を立てる
- 閉じる: `PROGRESS_TERMS`（「完了」「成功」等）を検出したら `closed`
- しつこさ防止: フォローを3回しても反応が無ければ `closed`。14日経過で剪定

レコード構造は次の形です。

```json
{
  "id": "loop-0001",
  "topic": "請求書まわりの確認",
  "summary": "請求書テンプレの件、あとで確認したいと言っていた",
  "first_seen": "2026-06-08",
  "last_mentioned": "2026-06-08",
  "status": "open",
  "follow_count": 0,
  "last_followed_on": null
}
```

翌日のチェックインでは、checkinのpre-run script `daily_conversation_context.py` が、
日記の直近1〜2日の抜粋と open_loops から **1件だけ** 候補を選び、`## 先日からの続き` セクションとして注入します。
選択した瞬間に `follow_count` を +1 し `last_followed_on` を当日へ原子的に更新するため、
**同じ日の2回目以降のチェックインには出ません**。1日1フォロー制限が構造で保証されます。

候補条件は4つすべてを満たすことです。

- `status` が `open`
- 今日まだフォローしていない
- `follow_count` が 3 未満
- `last_mentioned` が 1〜7日前

### セットアップ手順

スクリプトを `%LOCALAPPDATA%\hermes\scripts` に置き、cronジョブを2つ登録します。

```powershell
# 日次ダイジェスト（夜21:35、LLMを使わない no_agent ジョブ）
# scheduleは位置引数、--scriptはファイル名のみ（HERMES_HOME\scripts から解決される）
hermes cron create "35 21 * * *" `
  --name "daily-digest-2135" `
  --script "daily_digest.py" `
  --no-agent `
  --deliver discord
```

`daily_conversation_context.py` は単体のcronではなく、既存の `mentor-checkin` ジョブの pre-run script として紐付けます。
紐付け方はホスト側のジョブ定義（`jobs.json`）に依存しますが、考え方は「チェックイン本体が走る直前にこのスクリプトを実行し、その stdout を Script Output としてLLMへ渡す」です。

### jobs.json の prompt 追記例

`mentor-checkin` ジョブの prompt 末尾に、次の英語指示を足します（実運用で使っている全文）。

```text
Follow the opening style hint in the Script Output and never reuse yesterday's
opening line. If the Script Output contains a 先日からの続き section, you may weave
in exactly one gentle follow-up about that topic when it fits naturally; skip it
otherwise. If the 最近の調子 section indicates fatigue, reduce suggestions to one
tiny action and soften the tone. Do not mention section names or that a script
output exists.
```

21:00 ジョブ全体の prompt 例は [examples/mentor-checkin-prompt.example.txt](../examples/mentor-checkin-prompt.example.txt) にあります。
適用は `hermes cron edit <job_id> --prompt "<既存prompt + 上記>"` で行います（jobs.json の直接編集は避ける）。

## 柱2: 時間のゆらぎと生活リズム

### 仕組み

- 配送時刻のゆらぎ: pre-run scriptの冒頭で `time.sleep(random.uniform(0, 420))`（0〜7分）
- `## いまの時間と曜日`: 曜日別ヒント（月＝週の立ち上がり／金＝週末前／土日＝休日トーン、計7種）＋時間帯（朝／夕方前／夜）
- `## 書き出しスタイルのヒント`: 6種から `random.choice` で1つだけ注入

cron expr は触りません。
exprは分単位の指定が中心で、「定時から数分のランダムなずれ」を表現しにくいからです。
exprは固定したまま、スクリプト内のsleepで配送時刻だけを揺らします。

書き出しヒントの6種は次のとおりです。

- 観察から
- ねぎらいから
- 前回の続きから
- 時候から
- 結論先出し
- 報告調

このうち1つだけを乱数で選び、「前回と同じ書き出しは禁止」と添えます。
12Bのテンプレ感を崩すのに一番効いたのがこれでした。モデルの自制ではなく、乱数が書き出しを強制的に変えるからです。

### 検証時の無効化

手動検証で0〜7分待つのは無駄なので、ゆらぎを切れるようにしてあります。

- フラグ: `--no-jitter`
- env: `HERMES_CHECKIN_JITTER=0`

cronはスクリプトへ引数を渡せないので、cron経由でゆらぎを止めるならenvが唯一のノブです。

## 柱3: 感情・調子への寄り添い

### 仕組み

疲労の傾向を数日分ためて、提案の量とトーンに反映します。

- `autonomous_trigger_evaluator.py`（15分heartbeat）に `update_mood_state()` を追加。評価のたびに `cron\mood_state.json` へ、日別の tired / stuck / progress / user_messages / max_score の当日maxを蓄積（14日保持、原子的書き込み）
- `load_fatigue_trend()`: 直近3日のうち2日以上で tired>0 なら `fatigue_trend=true` → evaluate() に**減点のみ**追加（fatigue_penalty=8）

ここが設計の肝です。
fatigue_penalty=8 は、README 18.4 の既存減点群（集中中 -12／クールダウン -20／反復 -12／深夜 -25）と同列に並ぶ、ただの仲間です。
スコアの加点式も、各しきい値も、`should_notify` の7条件ANDも一切変えていません。
「疲れていそうな時期は少し遠慮する」を、既存の枠組みの中で表現しただけです。

チェックイン側は `## 最近の調子` セクションで、ルールベースに1〜2行だけ渡します。

- ここ数日に疲労サインが続く → 提案は1つに絞り、低エネルギー寄りのトーン
- 昨日は前進が多い → 軽い確認で十分

### セットアップ手順

`update_mood_state()` と `load_fatigue_trend()` は `autonomous_trigger_evaluator.py` の中に組み込みます（新規cronは不要、既存の15分heartbeatに同居）。
`mood_state.json` は初回評価時に自動生成されます。手動で空ファイルを用意する必要はありません。

## 柱4: 会話の自然さ

人格設定（SOUL.md）と秘書スキル（SKILL.md）に、文体の指針を足します。
ここはローカルモデルへの英語指示の方が安定したので、英語のまま載せます。

### SOUL.md への追記（全文）

```markdown
## Conversational Naturalness

- Vary your opening every time. Do not reuse the same first sentence pattern.
- Treat small talk as small talk: answer it briefly and warmly. Do not turn
  everything into a task.
- When something fails, apologize in one honest sentence, state the cause in
  one line, then move to the fix. No long excuses.
- When you are guessing, use a checking tone: "it might be ...",
  "if I'm wrong, please let me know."
- For follow-ups, raise only one topic per message, and leave room: add
  "it's perfectly fine if you don't answer."
- If there is no reply on a topic, drop it. Do not keep chasing it.
```

### SKILL.md（personal-mentor-secretary）への追記（全文）

```markdown
### Opening Variation

The Script Output may include a "## 書き出しスタイルのヒント" section with one
suggested opening style (observation / appreciation / continuation / season /
conclusion-first / report). Follow it loosely and never repeat the previous
opening. Do not mention the section name.

### Follow-up Etiquette

The Script Output may include a "## 先日からの続き" section with at most one
open topic. Touch it only when it fits naturally, exactly once, and never
mention that a section or Script Output exists. Keep one topic per message and
leave the user free not to answer.
```

書き出しヒントと先日の続きは、柱2・柱1のセクション名と対応づけています。
SKILL.md側で「セクション名には言及しない」と明示しておくのが、復唱事故を防ぐ近道です。

## 付随修復: no_agent=false cron はLLM可用性が前提という罠

### 症状と原因

`mentor-checkin` の3ジョブが毎回 `RuntimeError: Connection error.` で失敗し、⚠️ がDiscordへ流れました。

原因は、llama-server が Hermes Desktop 終了時にVRAM配慮で自動停止する一方、バックグラウンドのGateway cronは動き続けることでした。
**LLMを起こすジョブ（`no_agent: false`）だけが、相手不在で静かに死ぬ**わけです。
`no_agent: true` のジョブはLLM不要なので無事に動き、かえって異常に気づきにくいのが厄介でした。

### 解法：ensure_llm.py

チェックイン直前にllama-serverを起こす `scripts\ensure_llm.py` を pre-run に挟みます。

- `/health` をプローブ（llama.cppは 200=ready ／ 503=ロード中）
- 落ちていれば既存の起動用PS1を呼ぶ
- ready まで2秒間隔でポーリング（最大240秒）
- **自分が起動したときだけ** `cron\llama_started_by_cron.json` にマーカーを書く

起動に失敗したとき（GPU逼迫等）は、stdoutに `{"wakeAgent": false}` を出して **exit 0** で終わります。
そのチェックインは1回だけ静かに見送り、`cron\checkin_skips.jsonl` に記録します。

> 重要: 失敗時に非ゼロで落としてはいけません。
> 非ゼロ終了すると scheduler が「Script Error」をLLMへ知らせようとして、結局LLMを起こしにいき二重で失敗します。
> 「LLMが居ないから諦める」スクリプトが、諦め方を誤ってLLMを呼ぶ自爆です。失敗は必ず exit 0 ＋ `wakeAgent:false` で黙らせます。

### 後片付け：gemma_cron_reaper.py

起こしっぱなしを防ぐ回収役です。

- `scripts\gemma_cron_reaper.py`（`no_agent` cron `*/10 * * * *`）がマーカーを見る
- 起動から30分超 かつ Hermes Desktop 非実行なら、停止用PS1で回収
- Desktopが実行中なら、マーカーを消して所有権をDesktop側のwatcherへ移譲
- しきい値は env `HERMES_REAPER_IDLE_MINUTES`

回収役には2つの保険を入れています。

- **停止検証**: 停止用PS1を呼んだあと、プロセスが本当に消えたか最大15秒確認します。
  消えていなければマーカーを残したまま終わり、次の10分後の実行で再試行します。
  「停止が空振りしたのにマーカーだけ消え、サーバーが永遠に残る」事故を防ぐためです。
- **判断ログ**: 毎回の判断を `cron\reaper_log.jsonl` に1行ずつ残します
  （`reaped` / `too_young` / `handoff_desktop` / `stale_marker` / `stop_failed`）。
  reaperはDiscordへは沈黙する設計なので、ログが無いと「動いたのか何もしなかったのか」が
  後から分からなくなります。沈黙する家事こそ、足あとが要ります。

なお `wakeAgent` ゲートは `no_agent: false` のジョブでも有効でした（scheduler実装で確認済み）。

### cron登録例

```powershell
# llama-server 回収（10分ごと、LLMを使わない no_agent ジョブ）
hermes cron create "*/10 * * * *" `
  --name "gemma-cron-reaper-10m" `
  --script "gemma_cron_reaper.py" `
  --no-agent `
  --deliver discord
```

`ensure_llm.py` は単体cronではなく、`mentor-checkin` 各ジョブの pre-run script として紐付けます。

## 状態ファイルのサンプル（架空データ）

### memories\diary\YYYY-MM-DD.md

```markdown
# 2026-06-08 の記録

## 今日の流れ
- 午前: 請求書テンプレの相談。あとで確認したいとのこと。
- 午後: デプロイ手順の見直し。ステージングは通った。

## 気になっていること
- 請求書テンプレの件は未決着（あとで確認したい、と発話）

## 調子メモ
- 夕方に「疲れた」の発話あり
```

### cron\open_loops.json

```json
{
  "loops": [
    {
      "id": "loop-0001",
      "topic": "請求書テンプレの確認",
      "summary": "請求書テンプレの件、あとで確認したいと言っていた",
      "first_seen": "2026-06-08",
      "last_mentioned": "2026-06-08",
      "status": "open",
      "follow_count": 0,
      "last_followed_on": null
    }
  ],
  "updated_at": "2026-06-08T21:35:00"
}
```

### cron\mood_state.json

```json
{
  "days": {
    "2026-06-06": { "tired": 1, "stuck": 0, "progress": 2, "user_messages": 9, "max_score": 41 },
    "2026-06-07": { "tired": 0, "stuck": 1, "progress": 1, "user_messages": 5, "max_score": 33 },
    "2026-06-08": { "tired": 1, "stuck": 0, "progress": 3, "user_messages": 12, "max_score": 48 }
  },
  "updated_at": "2026-06-08T21:30:00"
}
```

## デバッグ手順

```powershell
$python = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"
$scripts = "$env:LOCALAPPDATA\hermes\scripts"

# 翌日チェックイン用の文脈を、待ち時間なしで確認
& $python "$scripts\daily_conversation_context.py" --no-jitter

# 日次ダイジェストを、ファイルを書かずに試す
& $python "$scripts\daily_digest.py" --dry-run

# llama-server の起動状態だけ確認
& $python "$scripts\ensure_llm.py" --status

# reaper の回収をその場で試す（待ち時間0）
$env:HERMES_REAPER_IDLE_MINUTES = "0"
& $python "$scripts\gemma_cron_reaper.py"
```

cronジョブとして仕込んだものは `hermes cron run <job_id|name>` で叩けます。
次の毎分tickに合わせて1回だけ実行されます。

状態ファイルを直接見たいときは次のとおりです。

```powershell
Get-Content "$env:LOCALAPPDATA\hermes\cron\open_loops.json"
Get-Content "$env:LOCALAPPDATA\hermes\cron\mood_state.json"
Get-Content "$env:LOCALAPPDATA\hermes\cron\checkin_skips.jsonl" -Tail 20
Get-Content "$env:LOCALAPPDATA\hermes\cron\reaper_log.jsonl" -Tail 20
```

## よくある失敗

- **exit 0 を破る**: 失敗時に非ゼロで落とすと、scheduler が Script Error をLLMへ知らせようとして二重失敗する。失敗は必ず exit 0 ＋ `{"wakeAgent": false}` で黙らせる。
- **cronに引数で挙動を切り替えようとする**: cronはスクリプトへ引数を渡せない。切り替えは env（`HERMES_CHECKIN_JITTER` / `HERMES_REAPER_IDLE_MINUTES`）かファイルで行う。
- **LLMがセクション名を復唱する**: 「## 先日からの続き」などをそのまま読み上げてしまうのは、prompt側の "Do not mention section names" / "never mention that a section ... exists" で抑える。
- **フォローアップがしつこくなる**: LLMの自制に頼らず、1日1フォローを `follow_count` と `last_followed_on` の原子的更新で構造的に縛る。3回反応が無ければ `closed`。
- **記憶のためにLLMを毎回呼ぶ**: 要約はルールベースに寄せる。llama-server停止中でも壊れず、推論コストも増えない。
- **沈黙する家事スクリプトに足あとを残さない**: reaperのように成功しても黙る役は、後から「動いたのか・何もしなかったのか・失敗したのか」を区別できなくなる。判断ログ（`reaper_log.jsonl`）と停止検証を最初から入れておく。
