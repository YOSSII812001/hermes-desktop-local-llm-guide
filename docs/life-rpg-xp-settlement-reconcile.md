# Life RPG の精算は「発表」と「再計算」が別物 — XP取りこぼしと reconcile

Hermes Agent Desktop 上で Life RPG（`%LOCALAPPDATA%\hermes\rpg_system`）を回していると、
「行動を報告したのに XP が増えない」という事象が起きることがある。原因は演出の名前と
実装のズレにあり、cron の「定期的に動くが通知するとは限らない」（README §18）と同じ構図の
「定期的に動くが再計算するとは限らない」問題である。

## 何が起きるか

夜のスケジュールタスクは2本に分かれている。

- `LifeRPG_NightlySettlement`（22:00）= `quest_settlement.py`（`settle_day`）。レポートを読んで XP/SP を**計算**する。
- `LifeRPG_DailyRewardReveal`（22:10）= reward phase。確定済みの結果を**発表(reveal)するだけ**で、XP は計算しない。

つまり「夜の精算で XP に変わる」という案内に対して、実際に計算するのは settlement の側だけ。
ここまでは設計通りだが、`settle_day` には落とし穴がある。

## 落とし穴：初回精算で日がロックされる

`settle_day` は、その日を一度精算すると `daily_logs` に保存して**ロック**する。
以降、`--force` を付けずに再精算しても `already_settled` で素通りし、**何も再計算しない**。

そのため次の順序で取りこぼしが起きる。

1. 日中に一度精算する（手動保存など）。その時点のレポートで XP が確定・ロックされる。
2. 夕方以降にレポートへ成果を追記する。
3. 夜の settlement が走るが、`--force` が無いと `already_settled` で素通り。追記分は反映されない。

レポートが唯一の正であり、XP は `daily_logs` から再計算される（`recalc_progression` は全 settled
ログをゼロから集計し直す**冪等**処理）。にもかかわらず、ロックのせいで最終レポートが再計算されない。

## 対策1：夜の settlement を `--force` にする

`register_tasks.ps1` の `LifeRPG_NightlySettlement` を `quest_settlement.py --force` で登録する。
これで夜の精算が必ず最終レポートを再計算し、日中の追記を取りこぼさない。

`--force` でも空レポートは `no_report` 扱いで既存ログを温存する（消さない）。`recalc_progression`
が冪等なので、毎晩 force で走らせても二重加算は起きない。

ルートのスケジュールタスクを書き換えるには管理者権限が要る（`Set-ScheduledTask` が
`HRESULT 0x80070005`＝アクセス拒否で失敗する場合は UAC 昇格して再実行する）。

## 対策2：reconcile ツールで過去日を点検・修復する

`reconcile_xp.py` は、各日のレポートから `daily_log` を再計算し、保存済みの値とのドリフトや
未精算を検出して `--force` 再精算で直す点検ツール。スコアリングは再実装せずエンジンの正規関数
（`report_to_day_log` / `settle_day`）を再利用する。

```powershell
$Root = "$env:LOCALAPPDATA\hermes\rpg_system"
# 確認だけ（書き込みなし・既定）
py -3 "$Root\reconcile_xp.py" --all
# 適用（実際に直す）
py -3 "$Root\reconcile_xp.py" --date 2026-06-26 --apply
py -3 "$Root\reconcile_xp.py" --all --apply
```

既定は dry-run で、ドリフトのある日だけを表示する。`--apply` を付けたときだけ書き込む。
冪等なので、同じ状態に対して何度実行しても結果は変わらない。

## 教訓

- 「精算」と名のつくジョブが、実際に値を**計算**しているのか、確定済みを**表示**しているだけなのかを区別する。
- 一度きりでロックする集計は、入力が後から増える運用では取りこぼす。再計算は冪等にし、最終入力で再実行する。
- 自動修復（夜の `--force`）と手動点検（reconcile ツール）の二段で守ると、原因調査をしなくても数値が正に収束する。
