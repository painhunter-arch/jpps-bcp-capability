# データ項目の定義

## Report（申告）

| 項目 | 型 | 必須 | 内容 |
| --- | --- | --- | --- |
| facilityName | string（80字以内） | ○ | 施設名 |
| facilityType | `hospital` / `clinic` / `pharmacy` | ○ | 施設の種別（病院／診療所／保険薬局） |
| pref | string | ○ | 都道府県（47都道府県名のいずれか） |
| address | string（120字以内） | ○ | 所在地（住所）。都道府県から入力。都道府県・市区町村の読み取りと位置の取得に使う |
| city | string（40字以内） | ○ | 市区町村。所在地から自動で読み取る（修正可）。災害救助法の適用市町村との照合と「市域」表示に使う |
| lat / lng | number \| null |  | 位置（緯度・経度）。所在地から国土地理院の住所検索API（またはGoogle）で求める。求められない場合は null |
| geoSrc | string |  | 位置の出典（`gsi`＝国土地理院、`google`、`sample`） |
| opioid | `ok` / `ask` / `ng` | ○ | 医療用麻薬（内服・貼付）：対応可／要相談／不可 |
| injection | `ok` / `ask` / `ng` | ○ | 医療用麻薬注射剤・PCA |
| homecare | `ok` / `ask` / `ng` | ○ | 在宅訪問（緩和ケア） |
| contactName | string（40字以内） | ○ | 申告者氏名 |
| memberNo | string（`709` で始まる10桁） | ○ | 会員番号 |
| tel | string | ○ | 災害時に通じる電話番号 |
| email | string |  | メールアドレス |
| assocPref | string（40字以内） |  | 所属する都道府県薬剤師会 |
| assocLocal | string（40字以内） |  | 所属する地域（地区）薬剤師会 |
| assocHosp | string（40字以内） |  | 所属する都道府県病院薬剤師会 |
| note | string（200字以内） |  | 補足 |
| consent | boolean（`true`） | ○ | 利用目的・提供先・会員向けの表示への同意 |
| consentVer | number |  | 同意した様式の版。`2` = 会員向けの表示（施設名等）に同意。`1` または未設定の申告は、会員向けの表示で施設名を伏せる |
| updatedAt | string（ISO 8601） | ○ | 最終保存日時 |

在庫数量は項目として持ちません。

## Mode（運用モード）

| 項目 | 型 | 内容 |
| --- | --- | --- |
| state | `normal` / `drill` / `disaster` | 平時／訓練／災害対策 |
| name | string | 訓練名または災害名 |
| since | string（`YYYY-MM-DD`） | 災害対策の発動日（`disaster` のとき必須） |
| startedAt | string（ISO 8601） | 訓練開始日時（`drill` のとき必須） |
| prefs | string[] | 想定・被災都道府県（空なら全国）。cities の都道府県も自動で含める |
| cities | {pref, city}[] | 適用・想定市町村（災害救助法の適用市町村など）。指定があれば、市町村単位で絞り込み・訓練の集計対象・地図の強調・会員画面の表示に使う |
| drillId | string | 実施中の訓練のID |
| active | boolean | 旧形式との互換用（`disaster` のとき `true`） |
| updatedAt | string（ISO 8601） | 変更日時 |

市町村の照合：申告の `city` と記録した市町村名を、空白を除いたうえで、一致・前方一致・後方一致のいずれかで照合する（例：「上益城郡益城町」と「益城町」、「熊本市中央区」と「熊本市」は一致とみなす）。都道府県が異なるものは一致としない。

基準日時：訓練は `startedAt`、災害対策は `since` の0時。これより前に更新された申告に「訓練未回答」「発動後未更新」の印がつきます。平時は更新から365日を過ぎた申告に「更新が必要」の印がつきます。

## Summary（申請側の地図に使う匿名の集計）

| 項目 | 型 | 内容 |
| --- | --- | --- |
| updatedAt | string（ISO 8601） | 集計日時 |
| total | number | 申告件数 |
| prefs | {都道府県: {n, opioid:{ok,ask,ng}, injection:{…}, homecare:{…}}} | 都道府県別の件数 |
| cities | [{pref, city, n, opioid:{…}, injection:{…}, homecare:{…}}] | 市区町村別の件数 |
| facilities | [{fid, facilityName?, address?, facilityType, pref, city, lat, lng, assocPref?, assocLocal, assocHosp?, opioid, injection, homecare, updatedAt, hidden?}] | 会員向けの「地域の稼働状況」に使う施設一覧。`fid` は会員番号から作る仮名ID（SHA-256の先頭12桁）。consentVer が2未満の申告は `hidden: true` で施設名等を含めない。**氏名・会員番号・電話・メール・補足は含めない** |

管理側が申告の変更時に自動で作成して公開する。**氏名・会員番号・電話・メール・補足は含めない。** 施設名は、会員向けの表示に同意した申告に限って含める。 Git公開版では状態ファイル（公開）に、運用モードとともに書き込む。

## Post（掲示板の書き込み）

| 項目 | 型 | 内容 |
| --- | --- | --- |
| id | string | 書き込みID |
| cat | `info` / `shortage` / `support` / `tf` / `gov` / `society` / `other` | 区分（情報提供・不足・支援・TF指示・行政情報・学会指示・その他） |
| pref / city | string | 都道府県（空は全国）、市区町村（任意） |
| title / body | string（60字 / 500字以内） | 件名・内容。患者の個人を特定できる情報は書かない |
| byName / byRole / byFid | string | 書き込み者の表示名（施設名、都道府県連絡員、災害対策TF、日本緩和医療薬学会）、役割（member / liaison / admin）、照合ID |
| createdAt / resolved | string / boolean | 書き込み日時、解決済み |

書き込める区分：会員＝情報提供・不足・支援・その他。都道府県連絡員＝左記＋行政情報。学会・TF＝全区分。TF指示・学会指示は学会・TFの書き込みに限って表示し、行政情報は学会・TFまたは担当都道府県の連絡員の書き込みに限って表示する。

## PrefStatus（都道府県の状況。都道府県連絡員が入力）

| 項目 | 型 | 内容 |
| --- | --- | --- |
| pref | string | 都道府県 |
| level | `normal` / `partial` / `severe` / `unknown` | 全体の状況（平常・一部に支障・重大な支障・不明） |
| items | {medical, pharmacy, supply, lifeline, traffic, assoc: `ok` / `issue` / `unknown`} | 医療機関、薬局、医薬品流通（医療用麻薬を含む）、ライフライン、交通・物流、薬剤師会・病院薬剤師会の稼働 |
| comment | string（300字以内） | 補足 |
| byName / byRole / byFid / updatedAt | string | 入力者（都道府県連絡員・災害対策TF）、役割、照合ID、入力日時 |

## Liaison（都道府県連絡員）

`{ fid, pref, role: "正" | "副", name }`。`fid` は会員番号から作る照合ID（会員番号そのものは保存しない）。`name` は管理用の控えで、会員向けには表示しない。

## Drill（訓練記録）

| 項目 | 型 | 内容 |
| --- | --- | --- |
| id | string | 訓練ID |
| name | string | 訓練名 |
| startedAt / endedAt | string（ISO 8601） | 開始・終了日時 |
| prefs | string[] | 対象都道府県（空なら全国） |
| cities | {pref, city}[] | 対象市町村（指定した場合） |
| target | number | 対象の申告件数 |
| responded | number | 回答件数（開始以降に保存された申告） |
| within24 / within72 | number | 開始から24時間／72時間以内の回答件数 |
| medianHours | number \| null | 開始から回答までの時間の中央値（時間） |

## ファイル形式（スタンドアロン版）

- 申告ファイル：`{ "schema": "jpps-bcp-capability-report", "version": 1, "exportedAt": "...", "report": Report }`
- 集計バックアップ：`{ "schema": "jpps-bcp-capability-backup", "version": 1, "exportedAt": "...", "mode": Mode, "reports": Report[] }`

## Git公開版（Google ドライブ）のファイル

| ファイル | 置き場所 | 内容 |
| --- | --- | --- |
| `config.json` | 公開リポジトリ（index.html と同じ場所） | `{ storage:"gdrive", clientId, apiKey, adminEmail, statusFileId, mapsKey }`。管理画面で書き出す |
| `jpps-bcp-report-会員番号.json` | 会員本人のドライブ（管理用アカウントと共有） | Report。`appProperties`：`{ jpps:"report", memberNo }` |
| `jpps-bcp-status.json` | 管理用アカウントのドライブ（公開・閲覧のみ） | `{ mode: Mode, summary: Summary, updatedAt }`。個人情報は含めない（集計は件数のみ）。`appProperties`：`{ jpps:"status" }` |
| `jpps-bcp-config.json` | 管理用アカウントのドライブ（非公開） | `{ approved:[メール], rejected:[メール], drills: Drill[] }`。`appProperties`：`{ jpps:"config" }` |
