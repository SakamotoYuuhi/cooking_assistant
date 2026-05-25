# 障害対応手順書

## 障害レベル定義

| レベル | 基準 | 対応時間 | 連絡先 |
|-------|------|---------|--------|
| P1（緊急） | 本番サービス全停止・決済不能 | 即時（24時間対応） | CTO・部長・全インフラ |
| P2（高） | 主要機能の一部停止・著しいパフォーマンス低下 | 30分以内 | インフラチームリーダー |
| P3（中） | 一部機能の不具合・特定ユーザーへの影響 | 2時間以内 | 担当チーム |
| P4（低） | 軽微な表示崩れ・使い勝手の問題 | 翌営業日 | 開発チーム |

## P1障害 対応フロー

### 第1フェーズ：検知と初動（0〜10分）

1. **アラート受信**
   - CloudWatchアラームまたはDatadogから通知
   - PagerDutyで担当者にエスカレーション

2. **状況確認**
   ```bash
   # サービス稼働確認
   curl -s https://api.company.com/health
   
   # ECSタスク状態確認
   aws ecs describe-services --cluster prod-cluster --services app-service
   
   # エラーログ確認（直近5分）
   aws logs tail /ecs/app --since 5m --follow
   ```

3. **インシデントチャンネル作成**
   - Slackに `#incident-YYYYMMDD-[内容]` チャンネルを作成
   - 関係者を招待
   - インシデント指揮者（IC）を決定

### 第2フェーズ：原因調査（10〜30分）

よくある原因と確認コマンド：

**データベース接続エラーの場合**
```bash
# RDS接続確認
aws rds describe-db-instances --db-instance-identifier prod-db
# 接続数確認
SELECT count(*) FROM pg_stat_activity;
```

**メモリ不足の場合**
```bash
# ECSタスクのメモリ使用率確認
aws cloudwatch get-metric-data \
  --metric-data-queries file://memory-query.json
```

**デプロイ起因の場合**
```bash
# デプロイ履歴確認
aws ecs describe-services --cluster prod-cluster \
  --services app-service \
  --query 'services[].deployments'
```

### 第3フェーズ：復旧（30〜60分）

**即時対応オプション**
1. 前バージョンへのロールバック（5分）
2. ECSタスクの再起動（3分）
3. RDSフェイルオーバー（15分）
4. スケールアウト（5分）

### 第4フェーズ：事後対応

- [ ] 障害報告書の作成（発生から48時間以内）
- [ ] 原因分析（RCA）の実施
- [ ] 再発防止策の策定と実施
- [ ] ポストモーテムの実施（1週間以内）

## よくある障害パターンと対処法

### タイムアウトエラーが多発している
→ データベースの接続プールを確認。必要に応じてECSタスク数を増加。

### 特定のAPIだけ500エラー
→ そのAPIのログを重点的に確認。デプロイ直後であればロールバックを検討。

### ディスク使用率が高い
→ 不要なログファイルを削除。S3へのアーカイブスクリプトを実行。

### レスポンスが遅い（タイムアウトなし）
→ APMツールでスロークエリを確認。インデックスの追加を検討。
