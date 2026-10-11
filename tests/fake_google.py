"""Google（GIS・Drive API・userinfo）の模擬サーバ。テスト専用。

Playwright のルーティングで googleapis.com と accounts.google.com への通信を横取りし、
メモリ上の「ドライブ」で応答する。共有の通知メールは self.mails に記録する。
"""
import json
import re
import urllib.parse

GIS_STUB = """
window.google = window.google || {};
window.google.accounts = { oauth2: { initTokenClient: function(o){
  return { requestAccessToken: function(){ setTimeout(function(){ o.callback({ access_token: 'TOKEN:' + (window.__who || 'nobody@test') }); }, 10); } };
} } };
"""


class FakeGoogle:
    def __init__(self):
        self.files = {}      # id -> {name, owner, props, content, perms:[{type, email}]}
        self.mails = []      # {to, message}
        self.seq = 0

    def _who(self, request):
        auth = request.headers.get("authorization", "")
        return auth.split("TOKEN:", 1)[1] if "TOKEN:" in auth else None

    def _visible(self, f, who):
        return f["owner"] == who or any(p["type"] == "anyone" or p.get("email") == who for p in f["perms"])

    def attach(self, context):
        context.route("https://accounts.google.com/gsi/client", lambda route: route.fulfill(status=200, content_type="text/javascript", body=GIS_STUB))
        context.route(re.compile(r"https://www\.googleapis\.com/.*"), self._handle)

    def _json(self, route, obj, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(obj, ensure_ascii=False))

    def _handle(self, route):
        req = route.request
        url = urllib.parse.urlparse(req.url)
        qs = urllib.parse.parse_qs(url.query)
        who = self._who(req)
        path = url.path

        if path == "/oauth2/v3/userinfo":
            return self._json(route, {"email": who}) if who else route.fulfill(status=401)

        if path == "/upload/drive/v3/files" and req.method == "POST":
            body = req.post_data or ""
            parts = [p for p in body.split("\r\n\r\n")]
            meta = json.loads(parts[1].split("\r\n--")[0])
            content = json.loads(parts[2].split("\r\n--")[0])
            self.seq += 1
            fid = f"F{self.seq}"
            self.files[fid] = {"name": meta["name"], "owner": who, "props": meta.get("appProperties", {}), "content": content,
                               "perms": [], "modifiedTime": "2026-10-05T01:00:00Z"}
            return self._json(route, {"id": fid})

        m = re.match(r"^/upload/drive/v3/files/([^/]+)$", path)
        if m and req.method == "PATCH":
            f = self.files.get(m.group(1))
            if not f or not (f["owner"] == who or any(p.get("email") == who and p.get("role") == "writer" for p in f["perms"])):
                return route.fulfill(status=403)
            f["content"] = json.loads(req.post_data)
            return self._json(route, {"id": m.group(1)})

        m = re.match(r"^/drive/v3/files/([^/]+)/permissions$", path)
        if m and req.method == "POST":
            f = self.files.get(m.group(1))
            if not f or f["owner"] != who:
                return route.fulfill(status=403)
            perm = json.loads(req.post_data)
            f["perms"].append({"type": perm["type"], "role": perm["role"], "email": perm.get("emailAddress")})
            if qs.get("sendNotificationEmail", ["false"])[0] == "true" and perm.get("emailAddress"):
                self.mails.append({"to": perm["emailAddress"], "from": who, "message": qs.get("emailMessage", [""])[0]})
            return self._json(route, {"id": "P"})

        m = re.match(r"^/drive/v3/files/([^/]+)$", path)
        if m and req.method == "GET" and qs.get("alt") == ["media"]:
            f = self.files.get(m.group(1))
            public = f and any(p["type"] == "anyone" for p in f["perms"])
            if not f or not (public or (who and self._visible(f, who))):
                return route.fulfill(status=404)
            return self._json(route, f["content"])

        if path == "/drive/v3/files" and req.method == "GET":
            q = qs.get("q", [""])[0]
            kind = re.search(r"value='([^']+)'", q).group(1)
            out = []
            for fid, f in self.files.items():
                if f["props"].get("jpps") != kind:
                    continue
                if "sharedWithMe" in q and f["owner"] != who and any(p.get("email") == who for p in f["perms"]):
                    out.append(fid)
                elif "'me' in owners" in q and f["owner"] == who:
                    out.append(fid)
            return self._json(route, {"files": [{"id": i, "name": self.files[i]["name"], "modifiedTime": self.files[i]["modifiedTime"],
                                                 "appProperties": self.files[i]["props"],
                                                 "owners": [{"emailAddress": self.files[i]["owner"], "displayName": self.files[i]["owner"].split("@")[0]}]} for i in out]})

        route.fulfill(status=404)
