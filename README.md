# carfree-map（島根県 松江市・出雲市）

> このブランチは島根県松江市・出雲市向けの設定と計算結果を管理する。汎用部分は `main` ブランチを参照。

主要な駅・バス停を起点に、公共交通と徒歩だけで行ける範囲、その中にある店や施設の数、最終便で帰れる範囲を地図で示すアプリ（PWA）です。

GTFS（GTFS-JP を含む）と地図データがあれば、どの地域にも対応できます。地域ごとの設定は `regions/` に置きます。

## 構成

計算は事前に Python で済ませ、アプリは計算結果を表示するだけにする。サーバーが不要で、静的ファイルとして公開できる。

| 層 | 内容 | 場所 |
|---|---|---|
| 地域設定 | 対象地域の名前、GTFS フィードの入手先 | `regions/<地域id>.toml` |
| データ | 時刻表（GTFS）、道路網（OpenStreetMap）、標高、施設の位置 | `data/`（リポジトリには含めない） |
| 計算 | 道路網での徒歩時間（坂の補正つき）、時刻表に沿った乗り継ぎ、最終便からの逆算、施設の集計 | `pipeline/` |
| 計算結果 | 地域ごとの集計結果（元データは含めない） | `results/<地域id>/` |
| アプリ | 地図表示、起点・時刻の選択、現在地から最寄り停留所の自動選択、ホーム画面への追加 | `app/` |

## 計算方法

- **徒歩時間**: 直線距離ではなく、道路網上の最短経路で求める。標高から勾配を出し、Tobler の式で歩く速さを補正する。天候による係数の切り替えも予定。
- **公共交通**: 時刻表どおりに乗り継ぎ、指定時刻に出発して一定時間内に着ける範囲を求める。最終便から逆算し、起点に戻れる最終時刻も求める。
- **施設の集計**: 範囲内の施設を種類ごとに数え、重みを付けて点数化する。重みはアプリ上で変更できる。

## 計算の手順と出力

| 手順 | スクリプト | Actions | 出力（`results/<地域id>/`） |
|---|---|---|---|
| 1. 時刻表の取得と起点候補の順位付け | `fetch_data.py`, `gtfs_hubs.py` | data pipeline | `hub_ranking_<日付>.csv` |
| 2. 道路網・標高・施設の取得と徒歩圏の集計 | `hub_walk.py` | walk analysis | `walk_summary.md`, `hub_walk.csv`, `poi_list.csv` |

手順2では、起点から徒歩5・10・15分で届く施設の数を、直線距離・道路網（坂なし）・道路網（坂あり）の3通りで比べる。施設の分類と対応する OpenStreetMap のタグは `pipeline/poi_categories.toml` で定義する。

## 地域の追加

1. `regions/example.toml` を参考に `regions/<地域id>.toml` を作る。
2. 地域ごとの調整や計算結果は、`region/<地域id>` ブランチで管理する。

## 使い方

### GitHub 上で実行

Actions タブ → **data pipeline** → **Run workflow** で、ブランチ・地域id・運行日を指定して実行する。結果はジョブの概要に表示され、そのブランチの `results/<地域id>/` にコミットされる。

### 手元で実行

```bash
pip install -r pipeline/requirements.txt
python pipeline/fetch_data.py --region <地域id>                    # 時刻表データを data/raw/ に保存
python pipeline/gtfs_hubs.py --region <地域id> --date 2026-12-01   # 停留所ごとの発車本数ランキング
python pipeline/hub_walk.py --region <地域id>                      # 徒歩圏の集計（bbox と hubs が必要）
```

テスト（ネットワーク接続なし）:

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

## この地域の設定

- 地域id: `shimane-matsue`（`regions/shimane-matsue.toml`）
- 起点候補: 松江駅、県民会館前、松江しんじ湖温泉駅、ＪＲ出雲市駅（発車本数ランキングをもとに選定）
- 未対応: 出雲市のコミュニティバス、一畑電車

## ライセンスと出典

<<<<<<< HEAD
時刻表などの元データはリポジトリに含めない。各データの利用条件は配布元に従う。

- 松江市交通局・一畑バス GTFS-JP: https://matsue-bus.jp/opendata
=======
時刻表などの元データはリポジトリに含めない。各データの利用条件は配布元に従う。地域ごとの出典は、各地域ブランチの README に記載する。

- 地図データ・施設データ: © OpenStreetMap contributors（ODbL）
- 標高: 国土地理院 標高タイル（https://maps.gsi.go.jp/development/demtile.html）
>>>>>>> main
