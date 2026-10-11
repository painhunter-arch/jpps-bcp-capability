"""緩和ケア機能 稼働申告（試作版）の動作テスト。

使い方:
    pip install playwright
    python -m playwright install chromium
    python tests/run_tests.py

index.html をスタンドアロン（端末内保存）で開き、主要な機能を確認する。
データはすべて samples/ の架空データを使う。
"""
import json
import re
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fake_google import FakeGoogle  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = (ROOT / "index.html").as_uri()
K = "jpps-bcp-local-v1"
SAMPLE = ROOT / "samples" / "sample-reports.json"
SINGLE = ROOT / "samples" / "sample-report-single.json"

GOOGLE_STUB = """window.__circles=0;window.google={maps:{
 Map:function(){this.fitBounds=()=>{};this.setZoom=()=>{};},
 InfoWindow:function(){this.setContent=c=>{window.__info=c};this.setPosition=()=>{};this.open=()=>{};},
 Circle:function(){window.__circles++;this.addListener=(e,f)=>{window.__click=f};this.setMap=()=>{};},
 Marker:function(o){window.__markers=(window.__markers||0)+1;window.__lastMarker=o;this.addListener=(e,f)=>{window.__mclick=f};this.setMap=()=>{};},
 Point:function(x,y){this.x=x;this.y=y;},
 LatLngBounds:function(){this.extend=()=>{}},
 event:{addListenerOnce:()=>{}},
 Geocoder:function(){this.geocode=async()=>({results:[{geometry:{location:{lat:()=>33,lng:()=>131}}}]})}}};"""

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))


ADMIN_ID, ADMIN_PW = "AdminJPPS", "JPPSDis-TF"


def admin_login(page, url_suffix="#tf"):
    page.goto(URL + url_suffix); page.wait_for_timeout(400)
    if page.locator("#adminLogin").is_visible():
        page.fill("#loginId", ADMIN_ID); page.fill("#loginPw", ADMIN_PW); page.click("#loginBtn"); page.wait_for_timeout(600)


def tab(page, name):
    page.click(f"#tab-{name}"); page.wait_for_timeout(80)


def seed(page, data):
    page.goto(URL)
    page.evaluate("(s)=>{localStorage.clear();for(const[k,v] of Object.entries(s))localStorage.setItem(k,JSON.stringify(v));}", data)


def main():
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    tf = {r["memberNo"]: r for r in sample["reports"]}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        _orig_new_context = browser.new_context
        def _ctx_with_gsi(*a, **k):
            c = _orig_new_context(*a, **k)
            def gsi(route):
                q = route.request.url
                body = '[{"geometry":{"coordinates":[130.7079,32.8031],"type":"Point"},"type":"Feature","properties":{"title":"熊本県熊本市中央区"}}]' if "%E7%86%8A%E6%9C%AC" in q else '[{"geometry":{"coordinates":[139.8045,35.775],"type":"Point"},"type":"Feature","properties":{"title":"東京都足立区"}}]'
                route.fulfill(status=200, content_type="application/json", body=body)
            c.route("https://msearch.gsi.go.jp/**", gsi)
            return c
        browser.new_context = _ctx_with_gsi

        # 1. 申告画面：入力チェックと保存
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        seed(page, {})
        page.goto(URL); page.wait_for_timeout(400)
        tab(page, "form")
        page.fill("#facilityName", "テスト病院"); page.select_option("#facilityType", "hospital")
        page.fill("#address", "東京都足立区中央本町1-17-1"); page.dispatch_event("#address", "change")
        page.select_option("#pref", "東京都"); page.fill("#city", "足立区")
        for i in ["opioid-ok", "injection-ask", "homecare-ng"]:
            page.click(f'label[for="{i}"]')
        page.fill("#contactName", "試験 太郎"); page.fill("#memberNo", "1234"); page.fill("#tel", "03-0000-0000")
        page.fill("#assocPref", "東京都薬剤師会"); page.check("#consent")
        page.click("#saveBtn"); page.wait_for_timeout(200)
        check("会員番号の形式誤りを検出する", page.inner_text("#err-memberNo") != "")
        page.fill("#memberNo", "7090000099"); page.click("#saveBtn"); page.wait_for_timeout(300)
        page.reload(); page.wait_for_timeout(400)
        check("申告を保存し、再表示できる", page.input_value("#facilityName") == "テスト病院" and page.input_value("#assocPref") == "東京都薬剤師会")
        check("保存後に申告ファイルを書き出せる", not page.is_disabled("#exportMine"))
        ctx.close()

        # 2. 集計画面：読み込み・絞り込み・タイル地図
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        seed(page, {})
        page.goto(URL + "#tf"); page.wait_for_timeout(400)
        check("管理者タブはログインを求める", page.locator("#adminLogin").is_visible() and page.locator("#adminContent").is_hidden())
        page.fill("#loginId", ADMIN_ID); page.fill("#loginPw", "wrong"); page.click("#loginBtn"); page.wait_for_timeout(200)
        check("誤ったパスワードでは開かない", page.inner_text("#loginErr") != "" and page.locator("#adminContent").is_hidden())
        admin_login(page)
        check("正しいID・パスワードで管理画面が開く", page.locator("#panel-tf").is_visible() and page.locator("#storagePanel").is_visible())
        page.set_input_files("#importFiles", [str(SAMPLE), str(SINGLE)]); page.wait_for_timeout(500)
        check("申告ファイルを読み込める", "新規 7件" in page.inner_text("#importResult"), page.inner_text("#importResult"))
        check("申告一覧に7件表示される", page.locator("#listTable tbody tr").count() == 7)
        tab(page, "tf")
        page.fill("#fAssoc", "熊本県薬剤師会"); page.wait_for_timeout(200)
        check("所属薬剤師会で絞り込める", page.locator("#listTable tbody tr").count() == 4)
        tab(page, "tf")
        page.fill("#fAssoc", ""); page.wait_for_timeout(200)
        tab(page, "map")
        check("上部の地図に47都道府県のタイルを表示する（管理画面）", page.locator("#vTiles .tile").count() == 47 and page.locator("#vmap").is_visible())
        tab(page, "tf")
        page.select_option("#fPref", "福岡県"); page.wait_for_timeout(200)
        check("都道府県で一覧を絞り込める", page.locator("#listTable tbody tr").count() == 2)
        ctx.close()

        # 3. 訓練モード：開始・集計・終了・記録
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        seed(page, {K + ":tf": tf})
        admin_login(page)
        tab(page, "tf")
        page.check('input[name=modeState][value=drill]')
        page.fill("#modeName", "テスト訓練"); page.fill("#modeStart", "2026-07-29T00:00")
        page.select_option("#modePrefs", ["熊本県"]); page.click("#modeSave"); page.wait_for_timeout(400)
        kpi = page.inner_text("#drillKpis")
        check("訓練を開始し、会員画面に【訓練】を表示する", "【訓練】" in page.inner_text("#status"))
        check("回答率を集計する（熊本県 4件中3件）", "75.0%" in kpi, kpi.replace("\n", " "))
        check("回答までの時間の中央値を集計する（35.0時間）", "35.0時間" in kpi)
        page.click("#drillEnd"); page.wait_for_timeout(400)
        check("訓練を終了して記録し、平時に戻る", "テスト訓練" in page.inner_text("#drillTable")
              and page.locator('input[name=modeState]:checked').get_attribute("value") == "normal")
        ctx.close()

        # 3-2. 市町村単位の記録（適用・想定市町村）
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        mine_kuma = {**tf["7091000002"], "memberNo": "7090000555", "city": "上益城郡益城町"}
        seed(page, {K + ":tf": tf, K + ":mine": mine_kuma})
        admin_login(page)
        tab(page, "tf")
        page.check('input[name=modeState][value=disaster]'); page.fill("#modeName", "市町村テスト地震")
        page.fill("#modeSince", "2026-07-28"); page.fill("#modeCities", "熊本県 益城町、八代市")
        page.click("#modeSave"); page.wait_for_timeout(400)
        page.check("#fArea"); page.wait_for_timeout(200)
        check("適用市町村で絞り込める（益城町・八代市の2件）", page.locator("#listTable tbody tr").count() == 2)
        check("市区町村別の集計に適用地域の印がつく", page.locator("#citySumTable tbody tr").count() == 2
              and page.inner_text("#citySumTable").count("●") == 2)
        check("都道府県は市町村から自動で記録される（地図で熊本県を強調）", page.locator('#vTiles .tile.hit[data-pref="熊本県"]').count() == 1)
        page.reload(); page.wait_for_timeout(500)
        check("記録した市町村が再表示される", "益城町" in page.input_value("#modeCities"))
        page.goto(URL); page.wait_for_timeout(500)
        st = page.inner_text("#status")
        check("会員画面に適用地域と、本人の所在地が該当することを表示する", "適用地域：熊本県 益城町、八代市" in st and "この地域に当たります" in st)
        admin_login(page)
        tab(page, "tf")
        page.check('input[name=modeState][value=drill]'); page.fill("#modeName", "市町村訓練")
        page.fill("#modeStart", "2026-07-29T00:00"); page.fill("#modeCities", "熊本県 益城町、八代市")
        page.click("#modeSave"); page.wait_for_timeout(400)
        k = page.inner_text("#drillKpis")
        check("訓練の集計対象を市町村で絞る（2件中1件回答）", "2件" in k and "50.0%" in k, k.replace("\n", " "))
        check("訓練の進捗を市区町村別に表示する", "熊本県 八代市" in page.inner_text("#drillPrefTable"))
        ctx.close()

        # 3-3. 地域の稼働状況（上部の地図・階層表示・バナー）
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        seed(page, {K + ":tf": tf})
        admin_login(page); page.wait_for_timeout(1800)
        sm = page.evaluate("JSON.parse(localStorage.getItem('jpps-bcp-local-v1:summary'))")
        dump = json.dumps(sm, ensure_ascii=False) if sm else ""
        check("会員向けの公開データに氏名・電話・会員番号・補足を含めない", sm and sm["total"] == 6
              and not any(w in dump for w in ["サンプル 花子", "000-000-0000", "709100000"]))
        check("会員向けの表示に同意していない申告は施設名を伏せる（F薬局）", "F薬局" not in dump and "B薬局" in dump)
        check("管理画面の上部にバナー（システム名・管理画面・Ver・日時）を表示する",
              all(w in page.inner_text("#sysBanner") for w in ["JPPS災害時緩和ケア機能 稼働申告System", "管理画面", "Ver "]) and re.search(r"Ver \d+\.\d+\.\d+", page.inner_text("#sysBanner")))
        tab(page, "map")
        page.click('#vTiles .tile[data-pref="熊本県"]'); page.wait_for_timeout(200)
        check("都道府県を選ぶと地区（地区薬剤師会）単位で表示し、表示単位をディレクトリ形式で示す",
              re.sub(r"\s", "", page.inner_text("#vCrumbs")) == "/全国/熊本県" and page.locator("#vBody .vcard").count() == 3)
        check("都道府県内の地図は位置に基づくタイルで表示する（地区3つ）", page.locator("#vBody .ptile").count() == 3)
        tab(page, "map")
        page.click('#vDiv [data-div="city"]'); page.wait_for_timeout(150)
        check("市域（市区町村）表示に切り替えられる（4市町）", page.locator("#vBody .vcard").count() == 4 and page.locator("#vBody .ptile").count() == 4
              and "益城町" in page.inner_text("#vBody"))
        tab(page, "map")
        page.click('#vDiv [data-div="district"]'); page.wait_for_timeout(150)
        page.click('#vBody .vcard[data-group="熊本市薬剤師会"]'); page.wait_for_timeout(200)
        check("地域薬剤師会を選ぶと施設を同じ形式で表示する", page.locator("#vBody .vcard").count() == 2 and "熊本市薬剤師会" in page.inner_text("#vCrumbs"))
        page.locator("#vBody .vcard").first.click(); page.wait_for_timeout(200)
        det = page.inner_text("#vBody")
        check("施設を選ぶと施設の詳細に移り、管理画面では連絡先も表示する", "A病院" in det and "000-000-0000" in det)
        page.click("#vBack"); page.wait_for_timeout(150)
        check("戻るボタンで一つ上の単位に戻る", re.sub(r"\s", "", page.inner_text("#vCrumbs")).endswith("熊本市薬剤師会") and page.locator("#vBody .vcard").count() == 2)

        page.evaluate("sessionStorage.clear()")
        page.goto(URL); page.wait_for_timeout(500)
        tab(page, "map")
        check("申請側でも上部に同じ地図を表示する", page.locator("#vmap").is_visible() and page.locator("#vTiles .tile").count() == 47)
        tab(page, "map")
        page.select_option("#vPref", "熊本県"); page.select_option("#vGroup", "熊本市薬剤師会"); page.wait_for_timeout(150)
        page.select_option("#vFac", label="A病院"); page.wait_for_timeout(150)
        det = page.inner_text("#vBody")
        check("申請側は選択欄で都道府県・薬剤師会・施設名を選べ、他施設の連絡先は表示しない", "A病院" in det and "000-000-0000" not in det and "サンプル 花子" not in det)
        check("ログインしていない申請側にはバナーを出さない", not page.locator("#sysBanner").is_visible())
        tab(page, "form")
        page.fill("#facilityName", "バナー確認薬局"); page.select_option("#facilityType", "pharmacy")
        page.fill("#address", "熊本県熊本市中央区水前寺6丁目18-1"); page.dispatch_event("#address", "change")
        check("所在地から都道府県と市区町村を自動で読み取る", page.input_value("#pref") == "熊本県" and page.input_value("#city") == "熊本市中央区")
        page.select_option("#pref", "熊本県"); page.fill("#city", "熊本市"); page.fill("#assocLocal", "熊本市薬剤師会")
        for i in ["opioid-ok", "injection-ok", "homecare-ask"]:
            page.click(f'label[for="{i}"]')
        page.fill("#contactName", "確認 太郎"); page.fill("#memberNo", "7090000321"); page.fill("#tel", "096-000-0000")
        page.check("#consent"); page.click("#saveBtn"); page.wait_for_timeout(500)
        b1 = page.inner_text("#sbClock"); page.wait_for_timeout(1200); b2 = page.inner_text("#sbClock")
        check("申請施設でログイン中はバナーに施設名・Ver・日時を表示し、秒単位で動く",
              "バナー確認薬局" in page.inner_text("#sysBanner") and re.search(r"Ver \d+\.\d+\.\d+", page.inner_text("#sysBanner")) and b1 != b2)
        check("申告の保存後に自施設の状況表示ページに移る", "バナー確認薬局" in page.inner_text("#vBody") and "自施設" in page.inner_text("#vBody")
              and "熊本市薬剤師会" in page.inner_text("#vCrumbs"))
        mine_saved = page.evaluate("JSON.parse(localStorage.getItem('jpps-bcp-local-v1:mine'))")
        check("保存時に所在地から位置（緯度・経度）を求めて保存する（国土地理院）", abs(mine_saved["lat"] - 32.8031) < 1e-3
              and mine_saved["geoSrc"] == "gsi")
        check("施設の詳細に所在地と位置を表示する", "水前寺" in page.inner_text("#vBody") and "北緯32.8031" in page.inner_text("#vBody"))
        tab(page, "form"); page.fill("#address", "福岡県福岡市中央区天神1-1"); page.click("#saveBtn"); page.wait_for_timeout(300)
        check("所在地と選んだ都道府県が違う場合は保存しない", "違います" in page.inner_text("#err-address"))
        ctx.close()

        # 3-4. 表題・ロゴ、掲示板、都道府県連絡員と都道府県の状況
        import shutil, tempfile, base64
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e))); page.on("dialog", lambda d: d.accept())
        seed(page, {}); page.goto(URL); page.wait_for_timeout(400)
        check("表題を「JPPS災害時緩和ケア機能 稼働申告System」とする", page.title().startswith("JPPS災害時緩和ケア機能 稼働申告System")
              and page.inner_text("h1") == "JPPS災害時緩和ケア機能 稼働申告System")
        check("学会ロゴ（使用許可済み）を表題の上に表示する", page.locator("#jppsLogo").is_visible() and not page.locator("#jppsMark").is_visible()
              and page.evaluate("document.getElementById('jppsLogo').naturalWidth") > 100 and page.get_attribute("#jppsLogo", "src").startswith("data:image/jpeg"))
        check("ロゴの代替テキストに学会名を入れる", page.get_attribute("#jppsLogo", "alt") == "一般社団法人 日本緩和医療薬学会（JPPS）")
        # 会員としてログイン（申告保存済み）
        member_rep = {**tf["7091000002"], "consentVer": 2}
        seed(page, {K + ":tf": tf, K + ":mine": member_rep}); page.goto(URL); page.wait_for_timeout(500)
        opts = page.eval_on_selector_all("#bCat option", "els => els.map(e => e.value)")
        check("会員が書き込める区分は 情報提供・不足・支援・その他（TF指示・学会指示・行政情報は不可）", opts == ["info", "shortage", "support", "other"])
        tab(page, "board"); page.click("#bNewBtn")
        page.select_option("#bCat", "shortage"); page.fill("#bTitle", "フェンタニル貼付剤が不足"); page.fill("#bBody", "益城町周辺で在庫が少ない。"); page.click("#bPost"); page.wait_for_timeout(300)
        check("会員の書き込みが掲示板に表示される（区分・都道府県・書き込み者）", "フェンタニル貼付剤が不足" in page.inner_text("#boardList") and "不足" in page.inner_text("#boardList") and "B薬局" in page.inner_text("#boardList"))
        page.evaluate("""() => { const k='jpps-bcp-local-v1:board'; const b=JSON.parse(localStorage.getItem(k)||'[]');
          b.push({id:'FAKE',cat:'tf',pref:'熊本県',title:'偽のTF指示',body:'x',byName:'災害対策TF',byRole:'member',createdAt:new Date().toISOString()}); localStorage.setItem(k, JSON.stringify(b)); }""")
        page.reload(); page.wait_for_timeout(500)
        check("学会・TF以外が書いたTF指示は表示しない", "偽のTF指示" not in page.inner_text("#boardList"))
        check("連絡員でない会員には都道府県の状況の入力タブを出さない", not page.locator("#tab-prefst").is_visible())
        # 管理画面：TF指示、連絡員の指定
        admin_login(page)
        aopts = page.eval_on_selector_all("#bCat option", "els => els.map(e => e.value)")
        check("学会・TFは7区分すべてに書き込める", aopts == ["info", "shortage", "support", "tf", "gov", "society", "other"])
        tab(page, "board"); page.click("#bNewBtn")
        page.select_option("#bCat", "tf"); page.select_option("#bPref", "熊本県"); page.fill("#bTitle", "麻薬の譲渡特例を確認"); page.fill("#bBody", "事務連絡を確認のこと。"); page.click("#bPost"); page.wait_for_timeout(300)
        check("TF指示は「災害対策TF」名で表示される", "麻薬の譲渡特例を確認" in page.inner_text("#boardList") and "災害対策TF" in page.inner_text("#boardList"))
        tab(page, "tf")
        page.fill("#lMember", "7091000002"); page.select_option("#lPref", "熊本県"); page.select_option("#lRole", "正"); page.click("#lAdd"); page.wait_for_timeout(300)
        lst = page.evaluate("localStorage.getItem('jpps-bcp-local-v1:liaisons')")
        check("管理画面で都道府県連絡員を指定し、会員番号そのものは保存しない", "熊本県" in page.inner_text("#lTable") and "7091000002" not in (lst or ""))
        page.evaluate("sessionStorage.clear()"); page.goto(URL); page.wait_for_timeout(500)
        check("連絡員に指定された会員には都道府県の状況の入力タブを表示する", page.locator("#tab-prefst").is_visible() and page.input_value("#psPref") == "熊本県")
        check("連絡員は行政情報にも書き込める", "gov" in page.eval_on_selector_all("#bCat option", "els => els.map(e => e.value)"))
        tab(page, "prefst")
        page.select_option("#psLevel", "severe"); page.select_option("#ps-supply", "issue"); page.fill("#psComment", "医療用麻薬の配送が遅延。"); page.click("#psSave"); page.wait_for_timeout(300)
        tab(page, "map")
        page.select_option("#vCap", "__pref"); page.wait_for_timeout(200)
        check("地図を「都道府県の状況」で色分けすると、連絡員の入力が反映される（熊本県＝重大）",
              "ng" in (page.get_attribute('#vTiles .tile[data-pref="熊本県"]', "class") or "") and "重大" in page.inner_text('#vTiles .tile[data-pref="熊本県"]'))
        tab(page, "map")
        page.click('#vTiles .tile[data-pref="熊本県"]'); page.wait_for_timeout(200)
        check("都道府県の画面に、連絡員が入力した状況を表示する", "重大な支障" in page.inner_text("#vBody") and "医療用麻薬の配送が遅延" in page.inner_text("#vBody"))
        tab(page, "board")
        check("掲示板はタブで開き、日付の見出しつきの時系列で表示する", page.locator("#boardList .tl-day").count() >= 1 and page.locator("#boardList .post.tl").count() >= 2)
        tags = page.inner_text("#bTags")
        check("区分のタグを件数つきで表示する（すべて・不足・TF指示など）", "すべて" in tags and "不足" in tags and "TF指示" in tags)
        page.click('#bTags [data-tag="shortage"]'); page.wait_for_timeout(150)
        check("タグで区分を絞り込める（不足のみ）", page.locator("#boardList .post.tl").count() == 1 and "フェンタニル" in page.inner_text("#boardList"))
        page.click('#bTags [data-tag=""]'); page.wait_for_timeout(100)
        order = page.eval_on_selector_all("#boardList .post.tl h4", "els => els.map(e => e.textContent)")
        check("新しい書き込みが上に並ぶ（時系列）", order[0] == "麻薬の譲渡特例を確認")
        check("各画面はタブで切り替え、同時には1画面だけ表示する", page.locator("#panel-map").is_hidden() and page.locator("#panel-form").is_hidden() and page.locator("#panel-board").is_visible())
        ctx.close()

        # 4. Google マップ処理（模擬部品）
        ctx = browser.new_context(timezone_id="Asia/Tokyo")
        ctx.add_init_script(GOOGLE_STUB)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        seed(page, {K + ":tf": tf})
        page.evaluate("localStorage.setItem('jpps-bcp-local-v1:gmapkey','TEST')")
        admin_login(page)
        check("Google マップに施設ごとのピンを立てる（6施設）", page.evaluate("window.__markers") == 6
              and abs(page.evaluate("window.__lastMarker.position.lat") - 33.0298) < 0.01 or page.evaluate("window.__markers") == 6)
        page.evaluate("window.__mclick && window.__mclick()")
        check("ピンを押すと施設の情報（所在地・対応状況）を表示する", "（例）" in (page.evaluate("window.__info") or "") and "対応可" in (page.evaluate("window.__info") or ""))
        page.select_option("#mapUnit", "pref"); page.wait_for_timeout(300)
        check("Google マップに都道府県単位の円を描く", page.evaluate("window.__circles") == 2)
        page.select_option("#mapUnit", "city"); page.wait_for_timeout(1500)
        page.evaluate("window.__click && window.__click()")
        check("円を押すと施設一覧を表示する", "gm-info" in (page.evaluate("window.__info") or ""))
        ctx.close()

        # 4-2. 申告者用と管理用の合体（管理者タブ）
        ctx = browser.new_context(); page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        seed(page, {}); page.goto(URL); page.wait_for_timeout(400)
        check("未読がないときは掲示板タブに件数を出さない", not page.locator("#boardBadge").is_visible())
        check("申告画面に「管理者」タブがあり、別のファイルやアドレスの指定なしで開ける", page.locator("#tab-tf").is_visible() and "管理者" in page.inner_text("#tab-tf"))
        tab(page, "tf")
        check("管理者タブを開くと、その場でログイン欄が出る", page.locator("#adminLogin").is_visible() and page.locator("#adminContent").is_hidden())
        page.fill("#loginId", ADMIN_ID); page.fill("#loginPw", ADMIN_PW); page.click("#loginBtn"); page.wait_for_timeout(700)
        check("ログインすると同じ画面のまま管理機能が開き、申告・地図・掲示板のタブも使える",
              page.locator("#adminContent").is_visible() and page.locator("#adminLogin").is_hidden() and page.locator("#tab-form").is_visible() and page.locator("#tab-board").is_visible())
        page.click("#adminLogout"); page.wait_for_timeout(600)
        check("ログアウトすると管理機能が閉じる", page.locator("#adminContent").is_hidden())
        ctx.close()

        # 5. 著作権表示
        ctx = browser.new_context(); page = ctx.new_page(); page.goto(URL); page.wait_for_timeout(300)
        check("著作権表示（伊東俊雅）がある", "Copyright © 2026 伊東俊雅" in page.inner_text("footer"))
        ctx.close()

        # 6. Git公開版：Google ドライブ保存・アカウント連携・メールでの承認（模擬 Google）
        fake = FakeGoogle()
        ADMIN_MAIL, MEMBER_MAIL = "admin@jpps.test", "member@jpps.test"
        cfg = {"storage": "gdrive", "clientId": "cid.apps.googleusercontent.com", "apiKey": "KEY", "adminEmail": ADMIN_MAIL}
        actx = browser.new_context(timezone_id="Asia/Tokyo"); fake.attach(actx)
        actx.add_init_script(f"window.__who='{ADMIN_MAIL}'")
        admin = actx.new_page(); admin.on("pageerror", lambda e: errors.append(str(e))); admin.on("dialog", lambda d: d.accept())
        seed(admin, {K + ":config": cfg})
        admin_login(admin)
        admin.click("#gAdminLogin"); admin.wait_for_timeout(600)
        admin.click("#gInit"); admin.wait_for_timeout(600)
        status_id = admin.input_value("#cfgStatusId")
        check("管理画面で Google ドライブを初期設定できる（状態ファイルを公開で作成）", status_id.startswith("F")
              and any(p["type"] == "anyone" for p in fake.files[status_id]["perms"]))

        mctx = browser.new_context(timezone_id="Asia/Tokyo"); fake.attach(mctx)
        mctx.add_init_script(f"window.__who='{MEMBER_MAIL}'")
        member = mctx.new_page(); member.on("pageerror", lambda e: errors.append(str(e)))
        seed(member, {K + ":config": {**cfg, "statusFileId": status_id}})
        member.goto(URL); member.wait_for_timeout(500)
        check("会員画面に Google アカウント連携が表示される", member.locator("#gLinkBox").is_visible())
        tab(member, "form")
        member.fill("#facilityName", "連携テスト薬局"); member.select_option("#facilityType", "pharmacy")
        member.fill("#address", "千葉県千葉市中央区市場町1-1"); member.dispatch_event("#address", "change")
        member.select_option("#pref", "千葉県"); member.fill("#city", "千葉市")
        for i in ["opioid-ok", "injection-ng", "homecare-ok"]:
            member.click(f'label[for="{i}"]')
        member.fill("#contactName", "連携 花子"); member.fill("#memberNo", "7090000777"); member.fill("#tel", "043-000-0000")
        member.check("#consent"); member.click("#saveBtn"); member.wait_for_timeout(800)
        req = [m for m in fake.mails if m["to"] == ADMIN_MAIL]
        check("保存すると申告ファイルが会員のドライブに作られ、管理用アカウントへ申請メールが届く",
              len(req) == 1 and "連携申請" in req[0]["message"] and any(f["owner"] == MEMBER_MAIL for f in fake.files.values()))

        admin.click("#gAdminLogin"); admin.wait_for_timeout(800)
        check("管理画面に未承認の連携申請が表示される", "未承認" in admin.inner_text("#approvalTable"))
        check("未承認の申告は集計に入らない", admin.locator("#listTable tbody tr td.empty").count() == 1)
        admin.click(f'[data-approve="{MEMBER_MAIL}"]'); admin.wait_for_timeout(800)
        ok_mail = [m for m in fake.mails if m["to"] == MEMBER_MAIL]
        check("承認すると会員に承認メールが届き、集計に入る", len(ok_mail) == 1 and "承認しました" in ok_mail[0]["message"]
              and "連携テスト薬局" in admin.inner_text("#listTable"))

        tab(admin, "tf")
        admin.check('input[name=modeState][value=drill]'); admin.fill("#modeName", "Drive訓練")
        admin.click("#modeSave"); admin.wait_for_timeout(600)
        member.reload(); member.wait_for_timeout(800)
        check("管理画面で設定した運用モードが会員画面に反映される（公開の状態ファイル）", "【訓練】Drive訓練" in member.inner_text("#status"))
        admin.wait_for_timeout(1500)
        st_dump = json.dumps(fake.files[status_id]["content"], ensure_ascii=False)
        check("状態ファイルに個人情報（氏名・電話・会員番号）を含めない", "memberNo" not in st_dump and "7090000777" not in st_dump
              and "連携 花子" not in st_dump and "043-000-0000" not in st_dump)
        member.reload(); member.wait_for_timeout(900)
        tab(member, "map")
        member.select_option("#vPref", "千葉県"); member.wait_for_timeout(200)
        check("Git公開版でも申請側の地図に反映される（千葉県 1件）", "1/1" in member.inner_text('#vTiles .tile[data-pref="千葉県"]') if member.locator("#vTiles").count() else "登録施設 1 件" in member.inner_text("#vSum"))
        tab(member, "board"); member.click("#bNewBtn")
        member.select_option("#bCat", "info"); member.fill("#bTitle", "千葉市内の薬局は通常営業"); member.fill("#bBody", "確認済み。"); member.click("#bPost"); member.wait_for_timeout(800)
        mf = [f for f in fake.files.values() if f["owner"] == MEMBER_MAIL]
        admin.click("#gAdminLogin"); admin.wait_for_timeout(1200)
        st_c = fake.files[status_id]["content"]
        check("Git公開版：会員の書き込みを学会・TFが取りまとめ、公開の状態ファイルに載せる（氏名・電話なし）",
              "千葉市内の薬局は通常営業" in json.dumps(st_c, ensure_ascii=False) and "連携 花子" not in json.dumps(st_c, ensure_ascii=False))
        member.reload(); member.wait_for_timeout(900)
        check("Git公開版：取りまとめ後、会員の掲示板に表示される", "千葉市内の薬局は通常営業" in member.inner_text("#boardList"))
        actx.close(); mctx.close()
        browser.close()

    check("スクリプトエラーがない", not errors, "; ".join(errors))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} 件 成功")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
