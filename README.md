# Paper Collector

Claude for Desktopと連携して、論文の検索・収集・管理を行うシンプルなツールです。

## 概要

Paper Collectorは、研究者や学生が学術論文を効率的に検索し、管理するためのツールです。

主な機能:
- arXivとSemantic Scholarから論文を検索
- 論文のメタデータとPDF（利用可能な場合）を自動保存
- キーワード検索、引用数による検索、日付範囲検索
- 保存された論文のフィルタリングと詳細表示
- PDFから全文テキスト抽出と全文検索
- 引用数に基づくランキングと分析
- 論文データのCSV/JSON形式でのエクスポート

## 必要環境

- Python 3.12+
- uv (Pythonパッケージマネージャー) **必須**
- Claude for Desktop

## インストール

### uvを使ったセットアップ

Paper Collectorはuvパッケージマネージャーで管理することを前提としています。

### Paper Collectorのインストール

```bash
# 開発モードでのインストール
uv pip install -e .

# 依存関係の確認
uv pip list
```

## 使い方

以下の方法でPaper Collectorを起動できます：

```bash
# インストール済みの場合
paper-collector

# または開発環境で
python -m paper_collector
```

### Claude for Desktopとの連携設定

連携方法は以下の2つがあります。いずれの場合も連携前に、このプロジェクトをuv環境下でインストールしておく必要があります：`uv pip install -e .`

#### 1. 設定ファイルを使った簡単セットアップ（推奨）

このリポジトリに同梱されている `config/claude_desktop_config.json` を利用して連携を設定できます。

#### 2. 手動設定

Claude for Desktopの拡張機能設定から手動で接続することも可能です。

### 主要な機能とコマンド例

- 論文検索: `論文を検索して: 量子コンピューティング`
- 引用数で検索: `引用数100以上の機械学習論文を検索して`
- 日付範囲で検索: `2023年から2024年までの自然言語処理の論文を検索して`
- 保存済みの論文一覧: `保存した論文の一覧を表示して`
- 論文の詳細情報: `"Attention is All You Need" の論文詳細を表示して`
- 論文の全文取得: `"BERT: Pre-training of Deep Bidirectional Transformers" の全文を表示して`
- 全文検索: `保存された論文から "transformer architecture" について検索して`

## 設定

設定ファイルは `~/.paper_collector/config.json` に保存されます。
