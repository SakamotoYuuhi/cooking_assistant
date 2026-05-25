# 社内FAQ：エンジニアリング

## 開発環境

### Q: ローカル開発環境のセットアップ手順は？
A: 以下の手順でセットアップできます：
1. Homebrewをインストール
2. `brew install git python3 node docker`
3. GitHubのSSHキーを設定（wiki/ssh-setup 参照）
4. リポジトリをクローン: `git clone git@github.com:company/app.git`
5. `.env.example` をコピーして `.env` を作成
6. `docker-compose up -d` でローカルDBを起動
7. `pip install -r requirements.txt` で依存ライブラリをインストール
8. `python manage.py migrate` でDBマイグレーション実行

詳細はREADME.mdを参照してください。

### Q: コードレビューのガイドラインは？
A: 以下のルールに従ってください：
- PRのサイズは300行以内を目標にする
- レビュアーは最低2名必要（うち1名はシニアエンジニア）
- レビューは依頼から2営業日以内に完了
- 承認なしにmainブランチへのマージ禁止
- テストカバレッジ80%以上を維持

### Q: ブランチ命名規則は？
A: 以下の命名規則に従ってください：
- 機能追加: `feature/[チケット番号]-[機能名]` （例: feature/JIRA-123-user-auth）
- バグ修正: `fix/[チケット番号]-[内容]` （例: fix/JIRA-456-login-error）
- 緊急修正: `hotfix/[内容]` （例: hotfix/payment-timeout）
- リリース: `release/[バージョン]` （例: release/v2.3.0）

## CI/CD

### Q: CIが失敗した場合の対処法は？
A: 以下の順で確認してください：
1. GitHub ActionsのログでエラーメッセージをCHECK
2. ローカルで同じコマンドを実行して再現確認
3. テスト失敗の場合: テストコードの修正
4. Lintエラーの場合: `pre-commit run --all-files` で自動修正
5. 解決できない場合はインフラチームへSlackで相談

### Q: Staging環境へのデプロイ方法は？
A: `develop` ブランチへのマージで自動デプロイされます。
手動デプロイが必要な場合：
```bash
# GitHub ActionsのWorkflowを手動トリガー
gh workflow run deploy-staging.yml --ref [ブランチ名]
```
デプロイ状況は #deployments チャンネルで確認できます。

## セキュリティ

### Q: 機密情報をコードに含めてしまった場合は？
A: 以下の手順で即座に対応してください：
1. 該当のシークレットを即座に無効化（AWSキーならIAMコンソールで削除）
2. git historyから削除: `git filter-branch` または `BFG Repo Cleaner`
3. force pushを実施（シニアエンジニアの確認必須）
4. セキュリティチームへ報告
5. 影響範囲の調査

### Q: 依存ライブラリの脆弱性が検出された場合は？
A: Dependabotのアラートを確認し、以下の基準で対応してください：
- Critical/High: 即日対応（当日中にPR作成）
- Medium: 1週間以内に対応
- Low: 次のスプリントで対応
対応方法はセキュリティWiki（wiki/vulnerability-response）を参照してください。
