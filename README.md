# alternative-tsukuba-kdb

[![CSV scheduled update](https://github.com/Make-IT-TSUKUBA/alternative-tsukuba-kdb/actions/workflows/main.yml/badge.svg)](https://github.com/Make-IT-TSUKUBA/alternative-tsukuba-kdb/actions/workflows/main.yml)

筑波大学の教育課程編成支援システム「KdB」の非公式代替サイトです。  
An unofficial website of the alternative of KdB, a curriculum planning support system used in University of Tsukuba.

<https://make-it-tsukuba.github.io/alternative-tsukuba-kdb/>

## このフォークについて

このリポジトリは、[Make-IT-TSUKUBA/alternative-tsukuba-kdb](https://github.com/Make-IT-TSUKUBA/alternative-tsukuba-kdb) のフォークです。

2026 年度の開設授業科目一覧 PDF は公開された一方で、KdB の 2026 年度データ更新はまだ行われていません。

- 開設授業科目一覧 PDF
  <https://www.tsukuba.ac.jp/education/ug-courses-openclass/2026/pdf/full-version.pdf>

そのため、本家の KdB 代替サイトも 2026 年度の情報をまだ扱えず、新年度の科目検索・閲覧に使いにくい状態になっています。
このフォークでは、上記 PDF から科目情報を抽出して JSON を構築し、KdB が更新される前の時点でも 2026 年度の科目情報を早めに使えるようにしています。

これは、2026 年 4 月上旬ごろに KdB と本家リポジトリが新年度対応するまでの暫定運用を主目的としています。

### この孫フォークについて
- 上記リポジトリに掲載されていたパースデータの一部に不備があり(例えばFG16011の概要にFG16043の概要が吸い取られている)、最初は単にパース用のスクリプトにbug fixを加えてPRを送ろうかと思っていたが、細かく見ていくとそもそもpdftotextが吐き出すbboxだけですべてのセグメンテーションを完璧に行うのが技術的に難しそうな気がしてきたので、素直に外部ライブラリ(`pdfplumber`)を使って再実装してみよう　という考えで引かれた
- 自分用

## PDF からの再構築

2026 年度の JSON は、KdB の CSV ではなく、開設授業科目一覧 PDF から再構築できます。

1. `full-version.pdf` をリポジトリルートに配置します。
2. 次のコマンドを実行します。

```bash
python tools/python/pdf-json.py full-version.pdf frontend/src/kdb
```

これにより、以下のファイルが更新されます。

- `/frontend/src/kdb/kdb.json`
- `/frontend/src/kdb/kdb-grad.json`

## 開発

`/csv` 配下に過去の科目データの CSV ファイルが含まれるため、clone/pull に時間を要する場合があります。スパースチェックアウト等を活用することをおすすめします。

```bash
# /csv を除外
git clone --depth 1 --filter=blob:none --no-checkout git@github.com:Make-IT-TSUKUBA/alternative-tsukuba-kdb.git
cd alternative-tsukuba-kdb
git sparse-checkout init --no-cone
printf '/*\n!csv/\n' > .git/info/sparse-checkout
git checkout main
```

詳細な開発手順については、以下の README.md を参照してください。

- `/frontend`：フロントエンド
- `/tools`：科目データの取得、管理用スクリプト

## ライセンス

This application is released under the MIT License, see [LICENSE](https://github.com/Make-IT-TSUKUBA/alternative-tsukuba-kdb/blob/main/LICENSE).
