"""資料2の画面例を作成するスクリプト（架空データを使用）。

使い方:
    python tools/make_screenshots.py
出力:
    tests/output/ に画面例の PNG を保存する。

本番の見え方に合わせるため、スタンドアロン専用の表示（申告ファイルの書き出し・読み込み等）は隠して撮影する。
"""
import json
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "output"
K = "jpps-bcp-local-v1"

HIDE = "<style>.toast{display:none!important}#exportMine,#sendGuide,#backendNotice,#tfLink,footer,.sa-only{display:none!important}.wrap{max-width:1080px!important}</style>"

sample = json.loads((ROOT / "samples" / "sample-reports.json").read_text(encoding="utf-8"))
mine = json.loads((ROOT / "samples" / "sample-report-single.json").read_text(encoding="utf-8"))["report"]
tf = {r["memberNo"]: r for r in sample["reports"]}
disaster = {"state": "disaster", "active": True, "name": "令和8年熊本地震（訓練例）", "since": "2026-07-28", "prefs": ["熊本県"],
            "cities": [{"pref": "熊本県", "city": "熊本市"}, {"pref": "熊本県", "city": "上益城郡益城町"}, {"pref": "熊本県", "city": "八代市"}]}
drill = {"state": "drill", "active": False, "name": "2026年度 机上訓練（熊本地震想定）", "startedAt": "2026-07-29T00:00:00+09:00", "prefs": ["熊本県"], "drillId": "D1"}
history = [{"id": "D0", "name": "2025年度 机上訓練（首都直下地震想定・例）", "startedAt": "2026-03-02T10:00:00+09:00",
            "endedAt": "2026-03-09T17:00:00+09:00", "prefs": [], "target": 120, "responded": 78,
            "within24": 41, "within72": 66, "medianHours": 20.5}]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    html = html.replace("</head>", HIDE + "</head>").replace("backend && backend.fileMode ?", "false ?")
    page_file = OUT / "_page.html"
    page_file.write_text(html, encoding="utf-8")
    url = page_file.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1120, "height": 900}, device_scale_factor=1.5,
                                  timezone_id="Asia/Tokyo", locale="ja-JP")
        page = ctx.new_page()

        def open_with(store, suffix=""):
            page.goto(url)
            page.evaluate("(s)=>{localStorage.clear();for(const[k,v] of Object.entries(s))localStorage.setItem(k,JSON.stringify(v));}", store)
            page.evaluate("sessionStorage.clear()")
            if suffix == "#tf":
                page.evaluate("sessionStorage.setItem('jpps-bcp-local-v1:admin','f015aee490672c22a6696ba69afc76ca07be30830fbd4d1ac3edce04b97f1b05')")
            elif suffix == "#login":
                page.evaluate("sessionStorage.clear()"); suffix = "#tf"
            page.goto(url + suffix)
            page.wait_for_timeout(800)

        def clip_between(top_selector, bottom_selector, name):
            page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(100)
            y0 = page.locator(top_selector).first.bounding_box()["y"]
            b = page.locator(bottom_selector).first.bounding_box()
            page.screenshot(path=str(OUT / name), full_page=True,
                            clip={"x": 0, "y": y0 - 10, "width": 1120, "height": b["y"] + b["height"] - y0 + 24})

        open_with({K + ":mine": mine})
        page.click("#tab-form"); page.wait_for_timeout(100)
        page.screenshot(path=str(OUT / "01_申告画面_平時.png"), full_page=True)
        open_with({K + ":mine": mine, K + ":mode": disaster})
        page.screenshot(path=str(OUT / "02_申告画面_災害対策.png"), clip={"x": 0, "y": 0, "width": 1120, "height": 760})
        open_with({K + ":tf": tf, K + ":mode": disaster}, "#tf")
        page.screenshot(path=str(OUT / "03_集計画面.png"), full_page=True)
        page.evaluate("window.scrollTo(0,0)")
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "04_地域の稼働状況_全国.png")
        page.click("#tab-map"); page.wait_for_timeout(80)
        page.click('#vTiles .tile[data-pref="熊本県"]'); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "12_地域の稼働状況_都道府県_地区.png")
        page.click('#vDiv [data-div="city"]'); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "17_地域の稼働状況_都道府県_市域.png")
        page.click('#vDiv [data-div="district"]'); page.wait_for_timeout(200)
        page.click('#vBody .vcard[data-group="熊本市薬剤師会"]'); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "13_地域の稼働状況_地域薬剤師会.png")
        page.locator("#vBody .vcard").first.click(); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "14_施設の詳細_管理画面.png")
        open_with({K + ":mine": mine, K + ":mode": drill})
        page.screenshot(path=str(OUT / "05_申告画面_訓練中.png"), clip={"x": 0, "y": 0, "width": 1120, "height": 430})
        open_with({K + ":tf": tf, K + ":mode": drill, K + ":drills": history}, "#tf")
        clip_between('h2:has-text("運用モード（管理）")', "#drillCsv", "06_管理画面_訓練.png")
        clip_between('h2:has-text("市区町村別の集計")', "#citySumTable", "09_市区町村別集計.png")
        open_with({K + ":tf": tf, K + ":mode": disaster}, "#tf")
        clip_between('h2:has-text("運用モード（管理）")', "#modeSave", "10_運用モード_適用市町村.png")
        open_with({K + ":tf": tf, K + ":mode": disaster}, "#tf")
        page.wait_for_timeout(1600)
        page.evaluate("sessionStorage.clear()")
        page.goto(url); page.wait_for_timeout(300)
        page.evaluate("(m)=>localStorage.setItem('jpps-bcp-local-v1:mine', JSON.stringify(m))", {**tf["7091000002"], "consentVer": 2})
        page.reload(); page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "15_申請側_バナーと地図.png"), clip={"x": 0, "y": 0, "width": 1120, "height": 980})
        page.click("#tab-map"); page.wait_for_timeout(80)
        page.select_option("#vPref", "熊本県"); page.select_option("#vGroup", "熊本市薬剤師会"); page.select_option("#vFac", label="A病院"); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "16_施設の詳細_申請側.png")
        # 掲示板と都道府県の状況（連絡員）
        board = [
          {"id":"P1","cat":"tf","pref":"熊本県","title":"医療用麻薬の譲渡特例を確認してください","body":"厚労省事務連絡（7月29日付）を災害関連情報ページに掲載しました。","byName":"災害対策TF","byRole":"admin","createdAt":"2026-07-29T12:00:00+09:00"},
          {"id":"P2","cat":"shortage","pref":"熊本県","city":"益城町","title":"フェンタニル貼付剤の在庫が少ない","body":"近隣の薬局でも不足。融通できる施設があれば連絡を。","byName":"B薬局","byRole":"member","createdAt":"2026-07-29T15:30:00+09:00"},
          {"id":"P3","cat":"gov","pref":"熊本県","title":"県の保健医療福祉調整本部が設置","body":"災害薬事コーディネーターが活動を開始。","byName":"災害対策TF（行政情報）","byRole":"admin","createdAt":"2026-07-29T10:00:00+09:00"},
          {"id":"P4","cat":"support","pref":"福岡県","title":"PCAポンプ2台を貸し出せます","body":"久留米市内。必要な施設はTF経由で連絡を。","byName":"E病院","byRole":"member","createdAt":"2026-07-30T09:00:00+09:00"}]
        prefst = {"熊本県":{"pref":"熊本県","level":"severe","items":{"medical":"issue","pharmacy":"issue","supply":"issue","lifeline":"issue","traffic":"issue","assoc":"ok"},"comment":"益城町・熊本市東区で停電・断水。医療用麻薬の配送に遅延。","byName":"熊本県 都道府県連絡員","byRole":"admin","updatedAt":"2026-07-29T18:00:00+09:00"},
                  "福岡県":{"pref":"福岡県","level":"partial","items":{"medical":"ok","pharmacy":"ok","supply":"issue","lifeline":"ok","traffic":"issue","assoc":"ok"},"comment":"","byName":"福岡県 都道府県連絡員","byRole":"admin","updatedAt":"2026-07-29T17:00:00+09:00"}}
        open_with({K + ":tf": tf, K + ":mode": disaster, K + ":board": board, K + ":prefst": prefst}, "#tf")
        page.wait_for_timeout(1700); page.evaluate("sessionStorage.clear()")
        page.goto(url); page.wait_for_timeout(300)
        page.evaluate("(m)=>localStorage.setItem('jpps-bcp-local-v1:mine', JSON.stringify(m))", {**tf["7091000002"], "consentVer": 2}); page.reload(); page.wait_for_timeout(800)
        page.click("#tab-map"); page.wait_for_timeout(80)
        page.select_option("#vCap", "__pref"); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "18_都道府県の状況_全国.png")
        page.click("#tab-board"); page.wait_for_timeout(120)
        clip_between("#boardBox", "#boardList", "19_掲示板.png")
        page.click("#tab-map"); page.wait_for_timeout(80)
        page.click('#vTiles .tile[data-pref="熊本県"]'); page.wait_for_timeout(200)
        page.click("#tab-map"); page.wait_for_timeout(80)
        clip_between("#vmap", "#vmap .legend", "20_都道府県の状況_熊本県.png")
        page.screenshot(path=str(OUT / "21_表題とバナー.png"), clip={"x": 0, "y": 0, "width": 1120, "height": 260})
        open_with({}, "#login")
        page.screenshot(path=str(OUT / "07_管理画面ログイン.png"), clip={"x": 0, "y": 0, "width": 1120, "height": 560})
        gcfg = {"storage": "gdrive", "clientId": "123456789-example.apps.googleusercontent.com", "apiKey": "（例）",
                "adminEmail": "jpps-disaster-tf@example.com", "statusFileId": "（初期設定で自動作成）"}
        open_with({K + ":config": gcfg}, "#tf")
        clip_between('h2:has-text("データの保存先と Google 連携（管理）")', "#approvalTable", "08_保存先設定と承認.png")
        browser.close()
    page_file.unlink()
    print("画面例を出力しました：", OUT)


if __name__ == "__main__":
    main()
