#!/usr/bin/env python3
"""TripDogs static site generator.

Reads content/ (Markdown) and regenerates all HTML pages.
Uses only the Python standard library.
"""
import datetime
import glob
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
TODAY = datetime.date.today().isoformat()
EMPTY = "There's nothing here yet, but additions are coming soon."
LISTS = [("anime", "Anime / Cartoons"), ("films", "Movies"), ("music", "Music")]
ABOUT_LASTMOD = "2026-10-04"


class BuildError(Exception):
    def __init__(self, path, reason, line=None):
        super().__init__(reason)
        self.path = path
        self.reason = reason
        self.line = line


# ---------------------------------------------------------------- helpers

def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def esc(s):
    return html.escape(s, quote=True)


def read_source(path):
    """Read a Markdown source as a list of lines (UTF-8, BOM and CRLF tolerant)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except UnicodeDecodeError:
        raise BuildError(path, "file is not valid UTF-8 (save it as UTF-8)")
    lines = []
    for line in text.splitlines():
        # Tolerate a common typo: "\---" instead of "---"
        if line.strip() == "\\---":
            line = "---"
        lines.append(line.rstrip())
    return lines


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def remove_stale(folder, keep):
    if not os.path.isdir(folder):
        return
    for f in glob.glob(os.path.join(folder, "*.html")):
        if os.path.splitext(os.path.basename(f))[0] not in keep:
            os.remove(f)


def check_slug(path):
    slug = os.path.splitext(os.path.basename(path))[0]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", slug):
        raise BuildError(
            path,
            "file name may contain only Latin letters, digits, '-' and '_' "
            "(no spaces or Cyrillic)",
        )
    return slug


def check_date(path, value):
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise BuildError(path, "date must be YYYY-MM-DD, got: %r" % value)


# ------------------------------------------------------- front matter

def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def split_front_matter(path, lines):
    """Return (meta, body_lines). meta is {} when there is no front matter."""
    if not lines or lines[0].strip() != "---":
        return {}, lines
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise BuildError(path, "front matter is not closed with a line '---'", 1)

    meta = {"tags": []}
    key = None
    for i in range(1, end):
        line = lines[i]
        if not line.strip():
            continue
        item = re.match(r"^\s*-\s*(.*)$", line)
        if item and key == "tags":
            value = unquote(item.group(1))
            if value:
                meta["tags"].append(value)
            continue
        m = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", line)
        if not m:
            raise BuildError(path, "invalid front matter line", i + 1)
        key = m.group(1).lower()
        value = m.group(2).strip()
        if key == "tags":
            if value.startswith("["):
                meta["tags"] = [unquote(x) for x in value.strip("[]").split(",") if x.strip()]
            elif value:
                meta["tags"] = [unquote(value)]
        else:
            meta[key] = unquote(value)
    return meta, lines[end + 1:]


def drop_title_heading(lines, title):
    """Remove a leading '# Title' line that repeats the front matter title."""
    for i, line in enumerate(lines):
        if line.strip():
            m = re.match(r"^#\s+(.*)$", line.strip())
            if m and m.group(1).strip() == title:
                return lines[:i] + lines[i + 1:]
            return lines
    return lines


# ----------------------------------------------------------- markdown

def slugify(text):
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_]+", "-", s) or "section"


def inline(text):
    s = esc(text)
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    s = re.sub(r"`([^`]+)`", stash, s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img src="\2" alt="\1">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)([^*]+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % codes[int(m.group(1))], s)
    return s


def md_to_html(lines):
    out, buf, seen = [], [], {}
    kind = None
    code, in_code, lang = [], False, ""

    def flush():
        nonlocal kind
        if buf:
            if kind == "p":
                out.append("<p>%s</p>" % inline(" ".join(buf)))
            elif kind == "ul":
                out.append("<ul>\n%s\n</ul>" % "\n".join("<li>%s</li>" % inline(b) for b in buf))
            elif kind == "quote":
                out.append("<blockquote><p>%s</p></blockquote>" % inline(" ".join(buf)))
        buf.clear()
        kind = None

    def switch(new):
        nonlocal kind
        if new != kind:
            flush()
            kind = new

    for line in lines:
        stripped = line.strip()

        if in_code:
            if stripped.startswith("```"):
                cls = ' class="language-%s"' % esc(lang) if lang else ""
                out.append("<pre><code%s>%s</code></pre>" % (cls, esc("\n".join(code))))
                code, in_code = [], False
            else:
                code.append(line)
            continue

        if stripped.startswith("```"):
            flush()
            in_code, lang, code = True, stripped[3:].strip(), []
            continue

        # Tolerate "**## Heading**" written by mistake
        bold_heading = re.match(r"^\*\*(#{1,3}\s+.+?)\*\*$", stripped)
        if bold_heading:
            stripped = bold_heading.group(1)

        if not stripped:
            flush()
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush()
            out.append("<hr>")
            continue

        h = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if h:
            flush()
            level, text = len(h.group(1)), h.group(2).strip()
            base = slugify(text)
            n = seen.get(base, 0)
            seen[base] = n + 1
            hid = base if n == 0 else "%s-%d" % (base, n)
            out.append('<h%d id="%s">%s <a class="anchor" href="#%s">[#]</a></h%d>'
                       % (level, hid, inline(text), hid, level))
            continue

        if stripped.startswith(">"):
            switch("quote")
            buf.append(stripped[1:].strip())
            continue

        li = re.match(r"^[-*]\s+(.*)$", stripped)
        if li:
            switch("ul")
            buf.append(li.group(1))
            continue

        switch("p")
        buf.append(stripped)

    if in_code:
        out.append("<pre><code>%s</code></pre>" % esc("\n".join(code)))
    flush()
    return "\n".join(out)


# ------------------------------------------------------------- loading

def load_tags():
    tags = {}
    for path in sorted(glob.glob(os.path.join(CONTENT, "tags", "*.md"))):
        if os.path.basename(path).startswith("_"):
            continue
        slug = check_slug(path)
        meta, _ = split_front_matter(path, read_source(path))
        title = meta.get("title", "").strip()
        if not title:
            raise BuildError(path, "tag file needs a title field", 1)
        tags[title.lower()] = {"slug": slug, "name": title}
    return tags


def load_articles():
    items = []
    for path in sorted(glob.glob(os.path.join(CONTENT, "articles", "*.md"))):
        if os.path.basename(path).startswith("_"):
            continue
        slug = check_slug(path)
        meta, body = split_front_matter(path, read_source(path))
        if not meta:
            raise BuildError(path, "missing front matter (file must start with ---)", 1)
        title = meta.get("title", "").strip()
        if not title:
            raise BuildError(path, "missing required field: title", 1)
        date = meta.get("date", "").strip()
        if not date:
            raise BuildError(path, "missing required field: date", 1)
        check_date(path, date)
        home = {"true": True, "false": False}.get(meta.get("home", "").strip().lower())
        items.append({
            "slug": slug,
            "title": title,
            "date": date,
            "category": meta.get("category", "").strip() or "Personal",
            "tags": meta["tags"],
            "home": home,
            "body": md_to_html(drop_title_heading(body, title)),
            "path": path,
        })
    return items


def load_lists():
    data = {}
    for slug, title in LISTS:
        path = os.path.join(CONTENT, "lists", slug + ".md")
        if not os.path.isfile(path):
            raise BuildError(path, "list source file is missing")
        _, body = split_front_matter(path, read_source(path))
        data[slug] = md_to_html(body)
    return data


# ----------------------------------------------------------- templates

def shell(title, body, body_class, root="", home=False):
    if home:
        nav = ('<nav class="main-nav"><a href="about.html">About</a> | '
               '<a href="lists/index.html">Lists</a> | <a href="tags.html">Tags</a> | '
               '<a href="updates.html">Updates</a></nav>')
        logo_class = "logo logo-home"
        page_nav = ""
        page_title = "TripDogs"
    else:
        nav = ""
        logo_class = "logo"
        page_nav = ('<nav class="page-nav"><a href="%sindex.html">Home</a>'
                    '<a href="#top">Top</a></nav>' % root)
        page_title = "%s — TripDogs" % title

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(page_title)}</title>
<link rel="icon" href="{root}assets/favicon/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{root}css/style.css">
</head>
<body class="{body_class}" id="top">
<div class="shell">
<header class="site-header">
<a class="{logo_class}" href="{root}index.html" data-logo>TripDogs</a>
{nav}
</header>
<main class="content">
{body}
</main>
<footer class="site-footer">
{page_nav}
<hr>
<div class="foot-row"><span>[Made with &lt;3 for dogs]</span><span>Site last updated: {TODAY}</span></div>
</footer>
</div>
<script src="{root}js/main.js"></script>
</body>
</html>
"""


def article_page(a, tags):
    crumbs = ['<a href="../index.html">TripDogs</a>', esc(a["category"])]
    if a["tags"]:
        first = a["tags"][0]
        info = tags.get(first.lower())
        if info:
            crumbs.append('<a href="../tags/%s.html">%s</a>' % (info["slug"], esc(info["name"])))
        else:
            crumbs.append(esc(first))
    body = f"""<div class="crumbs">{" / ".join(crumbs)}</div>
<article>
<h1>{esc(a["title"])}</h1>
<p class="muted">Published: {esc(a["date"])}</p>
{a["body"]}
</article>"""
    return shell(a["title"], body, "page-articles", root="../")


def entry(href, title, date):
    return ('<li><a href="%s">%s</a> <span class="muted">%s</span></li>'
            % (href, esc(title), esc(date)))


def home_page(items):
    rows = [
        '<li class="entry"><a href="articles/%s.html">%s</a><br>\n<span class="muted">%s</span></li>'
        % (a["slug"], esc(a["title"]), esc(a["date"]))
        for a in items
    ]
    listing = "\n".join(rows) if rows else "<li>%s</li>" % EMPTY
    body = f"""<hr>
<h2>Featured Articles</h2>
<!-- ARTICLE_INDEX_START -->
<ul class="plain article-index">
{listing}
</ul>
<!-- ARTICLE_INDEX_END -->"""
    return shell("TripDogs", body, "page-home", home=True)


def tag_page(tag, arts):
    rows = [entry("../articles/%s.html" % a["slug"], a["title"], a["date"]) for a in arts]
    listing = "\n".join(rows) if rows else None
    content = ('<ul class="plain">\n%s\n</ul>' % listing) if listing else "<p>%s</p>" % EMPTY
    body = "<h1>%s</h1>\n%s" % (esc(tag["name"]), content)
    return shell(tag["name"], body, "page-tags", root="../")


def tags_index(tags):
    rows = "\n".join('<li><a href="tags/%s.html">%s</a></li>' % (t["slug"], esc(t["name"]))
                     for t in sorted(tags.values(), key=lambda t: t["name"].lower()))
    body = '<h1>Tags</h1>\n<ul class="plain">\n%s\n</ul>' % rows
    return shell("Tags", body, "page-tags")


def list_index():
    rows = "\n".join('<li><a href="%s.html">%s</a></li>' % (slug, esc(title))
                     for slug, title in LISTS)
    body = '<h1>Lists</h1>\n<ul class="plain">\n%s\n</ul>' % rows
    return shell("Lists", body, "page-lists", root="../")


def list_page(title, html_body):
    return shell(title, html_body, "page-lists", root="../")


ABOUT_BODY = """<h1>About Me</h1>
<p class="muted">Lastmod: 2026-10-04</p>

<details class="toc">
<summary>Table of Contents</summary>
<ul class="plain">
<li>Who? <a class="anchor" href="#who">[#]</a></li>
<li>What’s here? <a class="anchor" href="#whats-here">[#]</a></li>
<li>Why, and for whom? <a class="anchor" href="#why-and-for-whom">[#]</a></li>
<li>Updates? <a class="anchor" href="#updates">[#]</a></li>
</ul>
</details>

<h2 id="who">Who? <a class="anchor" href="#who">[#]</a></h2>
<p>That's me—the owner of this site. Just one person. I write here whenever something pops into my head, all by myself, without anyone's help. Also, you should know that I'm Spanish, and my English isn't exactly great, so just to be safe, my <a href="https://www.deepl.com">assistant</a> translates my texts.</p>

<h2 id="whats-here">What’s here? <a class="anchor" href="#whats-here">[#]</a></h2>
<p>Here’s what I write about:</p>
<ul>
<li>Personal letters</li>
<li>Anime, movies, and cartoons</li>
<li>Games</li>
<li>Technology (maybe)</li>
<li>My thoughts on the world and society (once in a while)</li>
</ul>

<h2 id="why-and-for-whom">Why, and for whom? <a class="anchor" href="#why-and-for-whom">[#]</a></h2>
<p>I like sharing things with people, but at the same time, I want to stay in the background. It doesn’t matter to me who reads this; if people can find something here that speaks to them, or just stop by out of curiosity one day, that’s fine with me.</p>
<p>I don’t keep any information about site visits or visitors, and I don’t find that kind of data useful or interesting—quite the opposite, actually.</p>

<h2 id="updates">Updates? <a class="anchor" href="#updates">[#]</a></h2>
<p>You can find out about site updates on the <a href="updates.html">Updates</a> page.</p>
<p>From time to time, I might add something new here. A comments or reactions section will never be added. But in the future, you’ll be able to contact me personally via email.</p>
"""

UPDATES_BODY = """<h1>Updates</h1>
<p class="muted">Lastmod: 2026-10-04</p>
<ul class="plain">
<li>This website was created on 04.10.2026</li>
</ul>
"""


# --------------------------------------------------------------- build

def build():
    tags = load_tags()
    articles = load_articles()
    lists = load_lists()

    # Articles
    art_dir = os.path.join(ROOT, "articles")
    os.makedirs(art_dir, exist_ok=True)
    remove_stale(art_dir, {a["slug"] for a in articles})
    for a in articles:
        write(os.path.join(art_dir, a["slug"] + ".html"), article_page(a, tags))

    # Home
    featured = sorted(
        [a for a in articles if a["home"] is True or (a["home"] is None and not a["tags"])],
        key=lambda a: a["date"], reverse=True,
    )
    write(os.path.join(ROOT, "index.html"), home_page(featured))

    # Tags
    tag_dir = os.path.join(ROOT, "tags")
    os.makedirs(tag_dir, exist_ok=True)
    remove_stale(tag_dir, {t["slug"] for t in tags.values()})
    for t in tags.values():
        matched = sorted(
            [a for a in articles if t["name"].lower() in [x.lower() for x in a["tags"]]],
            key=lambda a: a["date"], reverse=True,
        )
        write(os.path.join(tag_dir, t["slug"] + ".html"), tag_page(t, matched))
    write(os.path.join(ROOT, "tags.html"), tags_index(tags))

    # Lists
    for slug, title in LISTS:
        write(os.path.join(ROOT, "lists", slug + ".html"), list_page(title, lists[slug]))
    write(os.path.join(ROOT, "lists", "index.html"), list_index())

    # Static pages
    write(os.path.join(ROOT, "about.html"), shell("About Me", ABOUT_BODY, "page-about"))
    write(os.path.join(ROOT, "updates.html"), shell("Updates", UPDATES_BODY, "page-updates"))

    print("Build complete: %d article(s), %d tag(s), %d list(s)."
          % (len(articles), len(tags), len(LISTS)))
    for a in articles:
        missing = [t for t in a["tags"] if t.lower() not in tags]
        if missing:
            print("Warning: %s.md uses tag(s) without a tag page: %s"
                  % (a["slug"], ", ".join(missing)))


def main():
    try:
        build()
    except BuildError as e:
        print()
        print("BUILD ERROR:")
        print("Could not parse %s" % rel(e.path))
        print("Reason: %s" % e.reason)
        if e.line:
            print("Line: %d" % e.line)
        print()
        print("Build stopped. Fix the file above and run build.bat again.")
        return 1
    except OSError as e:
        print()
        print("BUILD ERROR:")
        print("Could not write files.")
        print("Reason: %s" % e)
        return 1
    except Exception:
        import traceback
        print()
        print("BUILD ERROR: unexpected problem. Details:")
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
