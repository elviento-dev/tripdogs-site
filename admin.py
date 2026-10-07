#!/usr/bin/env python3
"""TripDogs local admin panel.

Run admin.bat, then write and edit articles in the browser.
The server listens only on this computer (127.0.0.1).
"""
import datetime
import html
import http.server
import importlib
import os
import re
import sys
import urllib.parse
import webbrowser

import build

HOST, PORT = "127.0.0.1", 8765
ART_DIR = os.path.join(build.CONTENT, "articles")
TAG_DIR = os.path.join(build.CONTENT, "tags")
SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

CSS = """<style>
body{font-family:Consolas,"Courier New",monospace;background:#141414;color:#e0e0e0;max-width:860px;margin:20px auto;padding:0 16px;line-height:1.5}
h1{font-size:1.4em;color:#fff}
a{color:#82AFF5}
input,textarea,select{background:#1e1e1e;color:#e0e0e0;border:1px solid #444;font:inherit;padding:6px;width:100%;box-sizing:border-box;margin-top:4px}
textarea{min-height:360px;white-space:pre}
label{display:block;margin-top:14px;color:#929292}
.hint{color:#777;font-size:.85em}
button,.btn{background:#222;color:#FF4F91;border:1px solid #FF4F91;padding:8px 14px;font:inherit;cursor:pointer;text-decoration:none;display:inline-block;margin-top:16px;margin-right:8px}
.danger{color:#ff6b6b;border-color:#ff6b6b}
.ok{color:#8fdc8f;border:1px solid #3c6b3c;padding:8px;margin:12px 0}
.err{color:#ff6b6b;border:1px solid #6b3c3c;padding:8px;margin:12px 0;white-space:pre-wrap}
table{width:100%;border-collapse:collapse;margin-top:12px}
td{padding:6px;border-bottom:1px solid #333;vertical-align:top}
</style>"""


def page(body, msg=""):
    return ("<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<title>TripDogs admin</title>" + CSS + "</head><body>"
            "<h1>TripDogs — панель статей</h1>"
            "<p><a href=\"/\">Статьи</a> &nbsp;·&nbsp; <a href=\"/new\">Новая статья</a>"
            " &nbsp;·&nbsp; <a href=\"/rebuild\">Пересобрать сайт</a></p>"
            + msg + body + "</body></html>")


def notice(text, ok=True):
    cls = "ok" if ok else "err"
    return '<div class="%s">%s</div>' % (cls, html.escape(text))


def clean(value):
    """Keep front matter values on one line without quotes."""
    return value.replace('"', "'").replace("\r", " ").replace("\n", " ").strip()


def run_build():
    importlib.reload(build)
    try:
        build.build()
        return None
    except build.BuildError as e:
        text = "Ошибка в файле %s\nПричина: %s" % (build.rel(e.path), e.reason)
        if e.line:
            text += "\nСтрока: %d" % e.line
        return text
    except Exception as e:  # keep the panel alive and show the problem
        return "Неожиданная ошибка сборки: %s" % e


def article_files():
    files = []
    for path in sorted(os.listdir(ART_DIR)):
        if path.endswith(".md") and not path.startswith("_"):
            files.append(path[:-3])
    return files


def load_values(slug):
    path = os.path.join(ART_DIR, slug + ".md")
    if not os.path.isfile(path):
        return None
    lines = build.read_source(path)
    meta, body = build.split_front_matter(path, lines)
    return {
        "original": slug,
        "slug": slug,
        "title": meta.get("title", ""),
        "date": meta.get("date", ""),
        "category": meta.get("category", ""),
        "tags": ", ".join(meta.get("tags", [])),
        "home": meta.get("home", "").lower(),
        "body": "\n".join(body).strip("\n"),
    }


def blank_values():
    return {"original": "", "slug": "", "title": "", "date": datetime.date.today().isoformat(),
            "category": "Personal", "tags": "", "home": "", "body": ""}


def form_page(v, error=""):
    def sel(name, current):
        options = [("", "Авто (без тегов — на главной)"), ("true", "Да — показывать на главной"),
                   ("false", "Нет — не показывать на главной")]
        opts = "".join('<option value="%s"%s>%s</option>' % (
            val, " selected" if val == current else "", label) for val, label in options)
        return '<select name="%s">%s</select>' % (name, opts)

    msg = notice(error, ok=False) if error else ""
    e = html.escape
    body = """<form method="post" action="/save">
<input type="hidden" name="original" value="%(original)s">
<label>Заголовок (title)</label>
<input name="title" value="%(title)s" required>
<label>Имя файла (slug) <span class="hint">— только латиница, цифры, дефис. Пример: my-article</span></label>
<input name="slug" value="%(slug)s" required pattern="[A-Za-z0-9][A-Za-z0-9_-]*">
<label>Дата (date) <span class="hint">— ГГГГ-ММ-ДД</span></label>
<input name="date" value="%(date)s" required pattern="\\d{4}-\\d{2}-\\d{2}">
<label>Категория (category)</label>
<input name="category" value="%(category)s">
<label>Теги (tags) <span class="hint">— через запятую, например: Games. Пусто — статья на главной</span></label>
<input name="tags" value="%(tags)s">
<label>Главная (home)</label>
%(home)s
<label>Текст статьи (Markdown)</label>
<textarea name="body">%(body)s</textarea>
<button type="submit">Сохранить и собрать сайт</button>
</form>""" % {
        "original": e(v["original"]), "title": e(v["title"]), "slug": e(v["slug"]),
        "date": e(v["date"]), "category": e(v["category"]), "tags": e(v["tags"]),
        "home": sel("home", v["home"]), "body": e(v["body"]),
    }
    heading = "<h2>%s</h2>" % ("Редактирование" if v["original"] else "Новая статья")
    return page(heading + msg + body)


def list_page(msg=""):
    rows = []
    for slug in article_files():
        path = os.path.join(ART_DIR, slug + ".md")
        try:
            meta, _ = build.split_front_matter(path, build.read_source(path))
            title = meta.get("title", "(без заголовка)")
            date = meta.get("date", "")
            tags = ", ".join(meta.get("tags", [])) or "—"
        except build.BuildError as e:
            title, date, tags = "⚠ ошибка: " + e.reason, "", "—"
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>"
            '<a class="btn" href="/edit?slug=%s">Изменить</a>'
            '<form method="post" action="/delete" style="display:inline" '
            "onsubmit=\"return confirm('Удалить статью %s?')\">"
            '<input type="hidden" name="slug" value="%s">'
            '<button class="danger" type="submit">Удалить</button></form></td></tr>'
            % (html.escape(title), html.escape(date), html.escape(tags), html.escape(slug),
               urllib.parse.quote(slug), html.escape(slug), html.escape(slug)))
    table = ("<table>%s</table>" % "".join(rows)) if rows else "<p>Статей пока нет.</p>"
    return page("<h2>Статьи</h2>" + table, msg)


def save(form):
    original = form.get("original", "").strip()
    slug = form.get("slug", "").strip()
    title = clean(form.get("title", ""))
    date = form.get("date", "").strip()
    category = clean(form.get("category", "")) or "Personal"
    tags_raw = form.get("tags", "")
    home = form.get("home", "")
    body = form.get("body", "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")

    values = {"original": original, "slug": slug, "title": title, "date": date,
              "category": category, "tags": tags_raw, "home": home, "body": body}

    if not title:
        return form_page(values, "Укажите заголовок статьи.")
    if not SLUG_RE.fullmatch(slug):
        return form_page(values, "Имя файла: только латиница, цифры, '-' и '_', без пробелов.")
    try:
        build.check_date("date", date)
    except build.BuildError:
        return form_page(values, "Дата должна быть в формате ГГГГ-ММ-ДД.")
    if home not in ("", "true", "false"):
        home = ""

    tags = [clean(t) for t in tags_raw.split(",") if t.strip()]
    # Create a tag page automatically for any new tag name.
    existing = build.load_tags()
    for t in tags:
        if t.lower() not in existing:
            tag_slug = t.lower().replace(" ", "-")
            if not SLUG_RE.fullmatch(tag_slug):
                return form_page(values, "Тег '%s' нельзя использовать: только латиница." % t)
            os.makedirs(TAG_DIR, exist_ok=True)
            with open(os.path.join(TAG_DIR, tag_slug + ".md"), "w", encoding="utf-8", newline="\n") as f:
                f.write('---\ntitle: "%s"\n---\n' % t)

    lines = ["---", 'title: "%s"' % title, 'date: "%s"' % date, 'category: "%s"' % category]
    lines.append("tags:")
    lines += ["  - %s" % t for t in tags]
    if home == "true":
        lines.append("home: true")
    elif home == "false":
        lines.append("home: false")
    lines.append("---")
    text = "\n".join(lines) + "\n\n" + body + "\n"

    new_path = os.path.join(ART_DIR, slug + ".md")
    if original and original != slug:
        if os.path.isfile(new_path):
            return form_page(values, "Статья с именем '%s' уже существует." % slug)
        old = os.path.join(ART_DIR, original + ".md")
        if os.path.isfile(old):
            os.remove(old)
    with open(new_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    error = run_build()
    if error:
        return form_page(dict(values, original=slug), error)
    return None  # caller redirects to the list


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, text, status=200, location=None):
        data = text.encode("utf-8")
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if url.path == "/":
            self.reply(list_page(notice(q["msg"]) if "msg" in q else ""))
        elif url.path == "/new":
            self.reply(form_page(blank_values()))
        elif url.path == "/edit":
            values = load_values(q.get("slug", ""))
            if values is None:
                self.reply(list_page(notice("Статья не найдена.", ok=False)), 404)
            else:
                self.reply(form_page(values))
        elif url.path == "/rebuild":
            error = run_build()
            msg = notice(error, ok=False) if error else notice("Сайт пересобран.")
            self.reply(list_page(msg))
        else:
            self.reply("Not found", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
        if self.path == "/save":
            result = save(form)
            if result is None:
                self.reply("", 303, "/?msg=" + urllib.parse.quote("Статья сохранена, сайт пересобран."))
            else:
                self.reply(result)
        elif self.path == "/delete":
            slug = form.get("slug", "")
            if SLUG_RE.fullmatch(slug):
                path = os.path.join(ART_DIR, slug + ".md")
                if os.path.isfile(path):
                    os.remove(path)
            error = run_build()
            msg = urllib.parse.quote("Статья удалена." if not error else "Удалено, но сборка с ошибкой: " + error)
            self.reply("", 303, "/?msg=" + msg)
        else:
            self.reply("Not found", 404)


def main():
    os.chdir(build.ROOT)
    try:
        server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        print("Port %d is busy. Close the other TripDogs admin window and try again." % PORT)
        return 1
    url = "http://%s:%d/" % (HOST, PORT)
    print("TripDogs admin is running: %s" % url)
    print("Keep this window open while you work. Press Ctrl+C or close it to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
