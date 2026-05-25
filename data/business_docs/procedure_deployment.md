# 手順書：本番環境デプロイ手順

## 概要
- 対象: Webアプリケーション本番デプロイ
- 所要時間: 約30分
- 実施タイミング: 毎週水曜日 22:00〜（メンテナンス時間帯）
- 担当: インフラチーム + 開発チームリーダー

## 事前確認チェックリスト
- [ ] ステージング環境でのテスト完了
- [ ] QAチームによるリリース承認取得
- [ ] 上長への実施連絡済み
- [ ] ロールバック手順の確認完了
- [ ] 監視ツールのアラート設定確認

## デプロイ手順

### 1. メンテナンスモード切替（22:00）
```bash
# ロードバランサーのメンテナンスページを有効化
aws elbv2 modify-listener --listener-arn $LISTENER_ARN \
  --default-actions Type=fixed-response,...
```
ユーザー向けメンテナンス通知がサイトに表示されることを確認する。

### 2. データベースバックアップ（22:05）
```bash
# RDSスナップショット作成
aws rds create-db-snapshot \
  --db-instance-identifier prod-db \
  --db-snapshot-identifier deploy-$(date +%Y%m%d)-pre
```
スナップショット完了まで約10分待機する。

### 3. アプリケーションデプロイ（22:15）
```bash
# ECRからイメージをプル
docker pull $ECR_REPO:$RELEASE_TAG

# ECSサービスを更新
aws ecs update-service \
  --cluster prod-cluster \
  --service app-service \
  --task-definition app-task:$NEW_REVISION \
  --force-new-deployment
```

### 4. ヘルスチェック（22:25）
- [ ] ECSタスクがRunning状態であることを確認
- [ ] ヘルスチェックエンドポイント（/health）が200を返すことを確認
- [ ] 主要機能の動作確認（ログイン・検索・決済）
- [ ] エラーログに異常がないことを確認

### 5. メンテナンスモード解除（22:30）
```bash
# ロードバランサーを通常モードに戻す
aws elbv2 modify-listener --listener-arn $LISTENER_ARN \
  --default-actions Type=forward,...
```

## ロールバック手順
問題が発生した場合、以下の手順で即時ロールバックする。

```bash
# 前バージョンのタスク定義に戻す
aws ecs update-service \
  --cluster prod-cluster \
  --service app-service \
  --task-definition app-task:$PREVIOUS_REVISION \
  --force-new-deployment
```

## 完了後の作業
1. デプロイ結果をSlackの #releases チャンネルに投稿
2. 本番環境の監視ダッシュボードを30分確認
3. 翌日朝のエラーレートを確認
