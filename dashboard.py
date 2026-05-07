#!/usr/bin/env python3
"""
Claude Files Dashboard
Start: python3 ~/claude/dashboard.py
Opent automatisch op http://localhost:3333
"""

import http.server
import json
import shlex
import subprocess
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path
from threading import Timer

PORT           = 3333
HOME           = Path.home()
FAVORITES_FILE = HOME / 'claude' / '.dashboard_favorites.json'
NOTES_FILE     = HOME / 'claude' / '.dashboard_notes.json'
RECENTS_FILE   = HOME / 'claude' / '.dashboard_recents.json'
MAX_RECENTS    = 20

ROOTS = {
    'projects': HOME / 'claude',
    'config':   HOME / '.claude',
}

SKIP = {
    '.DS_Store', '__pycache__', '.git', 'node_modules',
    'file-history', 'backups', 'cache', 'debug', 'downloads',
    'ide', 'paste-cache', 'session-env', 'sessions',
    'shell-snapshots', 'statsig', 'telemetry', 'todos',
    'mcp-needs-auth-cache.json', 'stats-cache.json',
    '.dashboard_favorites.json', '.dashboard_notes.json', '.dashboard_recents.json',
}

CONFIG_SHOW = {
    'settings.json', 'settings.local.json',
    'skills', 'plans', 'projects', 'history.jsonl',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_size(n: int) -> str:
    if n < 1024:    return f'{n} B'
    if n < 1 << 20: return f'{n >> 10} KB'
    return f'{n / (1 << 20):.1f} MB'


def normalize_path_key(path: str) -> str:
    try:
        return '~/' + str(Path(path).relative_to(HOME))
    except ValueError:
        return path

def expand_path_key(key: str) -> str:
    if key.startswith('~/'):
        return str(HOME / key[2:])
    return key

def load_notes() -> dict:
    raw = load_json(NOTES_FILE, {})
    migrated = {normalize_path_key(k): v for k, v in raw.items()}
    if migrated != raw:
        save_json(NOTES_FILE, migrated)
    return migrated

def load_favorites() -> list:
    raw = load_json(FAVORITES_FILE, [])
    migrated = [normalize_path_key(p) for p in raw]
    if migrated != raw:
        save_json(FAVORITES_FILE, migrated)
    return migrated

def notes_for_client(data: dict) -> dict:
    return {expand_path_key(k): v for k, v in data.items()}


def build_tree(path: Path, depth: int = 0, limit: int = 6) -> dict | None:
    if path.name in SKIP:
        return None
    try:
        s = path.stat()
    except OSError:
        return None

    is_dir = path.is_dir()
    node = {
        'name':    path.name,
        'path':    str(path),
        'dir':     is_dir,
        'size':    fmt_size(s.st_size) if not is_dir else '',
        'mod':     datetime.fromtimestamp(s.st_mtime).strftime('%d %b'),
        'ext':     path.suffix.lower() if not is_dir else '',
        'kids':    [],
        'last_ts': s.st_mtime,
    }

    if is_dir and depth < limit:
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            for e in entries:
                if e.name in SKIP:
                    continue
                child = build_tree(e, depth + 1, limit)
                if child:
                    node['kids'].append(child)
                    if child['last_ts'] > node['last_ts']:
                        node['last_ts'] = child['last_ts']
        except PermissionError:
            pass

    return node


def load_json(fp: Path, default):
    try:
        return json.loads(fp.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(fp: Path, data):
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def project_root_for(path: str) -> str:
    """Return the top-level project folder for any path under ~/claude."""
    p = Path(path)
    projects = ROOTS['projects']
    if str(p) == str(projects):
        return str(p)
    try:
        rel = p.relative_to(projects)
        return str(projects / rel.parts[0])
    except ValueError:
        return path


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        prs = urllib.parse.urlparse(self.path)
        q   = urllib.parse.parse_qs(prs.query)
        ep  = prs.path

        routes = {
            '/':                     lambda: self._html(),
            '/api/files':            lambda: self._files(q.get('root', ['projects'])[0]),
            '/api/open':             lambda: self._open(q.get('action',['finder'])[0], q.get('path',[''])[0]),
            '/api/favorites':        lambda: self._json([expand_path_key(f) for f in load_favorites()]),
            '/api/favorites/toggle': lambda: self._fav_toggle(q.get('path',[''])[0]),
            '/api/notes':            lambda: self._json(notes_for_client(load_notes())),
            '/api/notes/add':        lambda: self._note_add(q.get('path',[''])[0], q.get('type',['idea'])[0], q.get('text',[''])[0]),
            '/api/notes/toggle':     lambda: self._note_toggle(q.get('path',[''])[0], q.get('id',[''])[0]),
            '/api/notes/delete':     lambda: self._note_delete(q.get('path',[''])[0], q.get('id',[''])[0]),
            '/api/recents':          lambda: self._json(load_json(RECENTS_FILE, [])),
        }

        fn = routes.get(ep)
        if fn:
            fn()
        else:
            self.send_error(404)

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        body = HTML.replace('__HOME__', str(HOME)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _files(self, root: str):
        r = ROOTS.get(root)
        if not r:
            self.send_error(400)
            return
        node = build_tree(r)
        if root == 'config' and node:
            node['kids'] = [k for k in node['kids'] if k['name'] in CONFIG_SHOW]
        self._json(node)

    def _open(self, action: str, path: str):
        if not path:
            self.send_error(400)
            return
        fp = Path(path)
        if not fp.exists():
            self.send_error(404)
            return

        if action == 'finder':
            cmd = ['open', path] if fp.is_dir() else ['open', '-R', path]
        elif action == 'vscode':
            cmd = ['code', path]
        elif action == 'ghostty':
            root = path if fp.is_dir() else project_root_for(path)
            cmd = ['open', '-na', 'Ghostty.app', '--args',
                   '-e', '/bin/bash', '-c', f'cd {shlex.quote(root)} && claude']
        else:
            self.send_error(400)
            return

        subprocess.Popen(cmd)
        self._add_recent(path, action, fp.is_dir(), fp.suffix.lower())
        self._json({'ok': True})

    def _add_recent(self, path: str, action: str, is_dir: bool, ext: str):
        recents = load_json(RECENTS_FILE, [])
        recents = [r for r in recents if not (r['path'] == path and r['action'] == action)]
        recents.insert(0, {
            'path':      path,
            'name':      Path(path).name,
            'action':    action,
            'dir':       is_dir,
            'ext':       ext,
            'timestamp': datetime.now().isoformat(timespec='seconds'),
        })
        save_json(RECENTS_FILE, recents[:MAX_RECENTS])

    def _fav_toggle(self, path: str):
        if not path:
            self.send_error(400)
            return
        favs = load_favorites()
        key = normalize_path_key(path)
        added = key not in favs
        if added:
            favs.append(key)
        else:
            favs.remove(key)
        save_json(FAVORITES_FILE, favs)
        self._json({'ok': True, 'added': added, 'favorites': [expand_path_key(f) for f in favs]})

    def _note_add(self, path: str, ntype: str, text: str):
        if not path or not text.strip():
            self.send_error(400)
            return
        notes = load_notes()
        key = normalize_path_key(path)
        if key not in notes:
            notes[key] = []
        nid = datetime.now().strftime('%Y%m%d%H%M%S%f')
        notes[key].append({
            'id':      nid,
            'type':    ntype,
            'text':    text.strip(),
            'done':    False,
            'created': datetime.now().isoformat(timespec='seconds'),
        })
        save_json(NOTES_FILE, notes)
        self._json({'ok': True, 'notes': notes.get(key, [])})

    def _note_toggle(self, path: str, nid: str):
        if not path or not nid:
            self.send_error(400)
            return
        notes = load_notes()
        key = normalize_path_key(path)
        for n in notes.get(key, []):
            if n['id'] == nid:
                n['done'] = not n['done']
                break
        save_json(NOTES_FILE, notes)
        self._json({'ok': True, 'notes': notes.get(key, [])})

    def _note_delete(self, path: str, nid: str):
        if not path or not nid:
            self.send_error(400)
            return
        notes = load_notes()
        key = normalize_path_key(path)
        notes[key] = [n for n in notes.get(key, []) if n['id'] != nid]
        save_json(NOTES_FILE, notes)
        self._json({'ok': True, 'notes': notes.get(key, [])})


# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="nl" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Dashboard</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --bg:#f2f2f7;
  --sidebar:rgba(255,255,255,.72);
  --content:#fff;
  --panel:rgba(249,249,251,1);
  --text:#1c1c1e;
  --text2:#8e8e93;
  --text3:#aeaeb2;
  --accent:#0071e3;
  --accent-soft:rgba(0,113,227,.1);
  --green:#28c840;
  --green-soft:rgba(40,200,64,.12);
  --star:#ff9f0a;
  --hover:rgba(0,0,0,.04);
  --border:rgba(0,0,0,.08);
  --card:#fff;
  --card-border:rgba(0,0,0,.08);
  --input-bg:rgba(0,0,0,.055);
  --note-idea-bg:rgba(255,214,10,.12);
  --note-idea-c:#b25000;
  --note-bug-bg:rgba(255,59,48,.1);
  --note-bug-c:#c1170b;
  --note-todo-bg:rgba(0,113,227,.1);
  --note-todo-c:#0050a8;
  --shadow:0 2px 16px rgba(0,0,0,.08);
}

[data-theme="dark"]{
  --bg:#1c1c1e;
  --sidebar:rgba(44,44,46,.92);
  --content:#2c2c2e;
  --panel:#1c1c1e;
  --text:#f5f5f7;
  --text2:#8e8e93;
  --text3:#636366;
  --accent:#0a84ff;
  --accent-soft:rgba(10,132,255,.15);
  --green:#30d158;
  --green-soft:rgba(48,209,88,.15);
  --hover:rgba(255,255,255,.06);
  --border:rgba(255,255,255,.1);
  --card:#3a3a3c;
  --card-border:rgba(255,255,255,.08);
  --input-bg:rgba(255,255,255,.08);
  --note-idea-bg:rgba(255,214,10,.1);
  --note-idea-c:#ffd60a;
  --note-bug-bg:rgba(255,69,58,.12);
  --note-bug-c:#ff453a;
  --note-todo-bg:rgba(10,132,255,.12);
  --note-todo-c:#0a84ff;
  --shadow:0 2px 16px rgba(0,0,0,.3);
}

body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",sans-serif;
  background:var(--bg);color:var(--text);
  height:100vh;display:flex;flex-direction:column;
  overflow:hidden;-webkit-font-smoothing:antialiased;
  transition:background .2s,color .2s;
}

/* ── Titlebar ── */
.bar{
  height:52px;display:flex;align-items:center;
  padding:0 16px;gap:12px;
  background:rgba(255,255,255,.85);
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
  border-bottom:1px solid var(--border);
  flex-shrink:0;position:relative;z-index:20;
  transition:background .2s,border-color .2s;
}
[data-theme="dark"] .bar{background:rgba(28,28,30,.9)}
.lights{display:flex;gap:7px}
.dot{width:12px;height:12px;border-radius:50%}
.d-red{background:#ff5f57}.d-yel{background:#febc2e}.d-grn{background:#28c840}
.bar-title{
  position:absolute;left:50%;transform:translateX(-50%);
  font-size:13px;font-weight:600;letter-spacing:-.2px;pointer-events:none;
}
.bar-actions{margin-left:auto;display:flex;gap:6px}
.bar-btn{
  border:1px solid var(--border);border-radius:7px;
  background:transparent;padding:4px 11px;
  font-size:12px;font-weight:500;color:var(--text2);
  cursor:pointer;transition:background .14s,color .14s;font-family:inherit;
}
.bar-btn:hover{background:var(--hover);color:var(--text)}
.theme-btn{padding:4px 8px;font-size:15px;border:1px solid var(--border);
  border-radius:7px;background:transparent;cursor:pointer;
  transition:background .14s;line-height:1}
.theme-btn:hover{background:var(--hover)}

/* ── Layout ── */
.layout{display:flex;flex:1;overflow:hidden}

/* ── Sidebar ── */
.sidebar{
  width:220px;
  background:var(--sidebar);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-right:1px solid var(--border);
  padding:14px 10px;
  display:flex;flex-direction:column;gap:2px;
  flex-shrink:0;overflow-y:auto;
  transition:background .2s,border-color .2s;
}
.sidebar::-webkit-scrollbar{width:4px}
.sidebar::-webkit-scrollbar-thumb{background:rgba(128,128,128,.2);border-radius:2px}

.s-label{
  font-size:10.5px;font-weight:600;letter-spacing:.5px;
  text-transform:uppercase;color:var(--text2);
  padding:10px 10px 4px;margin-top:6px;
}
.s-label:first-child{margin-top:0}

.nav{
  display:flex;align-items:center;gap:9px;
  padding:7px 10px;border-radius:9px;
  cursor:pointer;font-size:13.5px;font-weight:500;
  color:var(--text);transition:background .14s;user-select:none;
}
.nav:hover:not(.active){background:var(--hover)}
.nav.active{background:var(--accent);color:#fff}
.nav .ni{font-size:15px;width:20px;text-align:center}

.badge{
  margin-left:auto;min-width:18px;height:18px;
  border-radius:9px;display:flex;align-items:center;justify-content:center;
  font-size:10.5px;font-weight:700;padding:0 5px;
  background:rgba(142,142,147,.2);color:var(--text2);
}
.nav.active .badge{background:rgba(255,255,255,.25);color:#fff}
.badge.orange{background:rgba(255,159,10,.18);color:var(--star)}
.nav.active .badge.orange{background:rgba(255,255,255,.25);color:#fff}

/* ── Main content ── */
.content{flex:1;display:flex;flex-direction:column;overflow:hidden;
  background:var(--content);transition:background .2s}

.content-head{
  display:flex;align-items:center;gap:12px;
  padding:13px 18px 11px;
  border-bottom:1px solid var(--border);
  background:var(--content);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  flex-shrink:0;transition:background .2s,border-color .2s;
}
.ch-title{font-size:15px;font-weight:600;letter-spacing:-.2px}
.ch-path{font-size:11px;color:var(--text2);font-family:"SF Mono",ui-monospace,monospace}
.search-wrap{margin-left:auto;position:relative}
.search-icon{position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--text2);font-size:13px;pointer-events:none}
.search{
  background:var(--input-bg);border:none;border-radius:8px;
  padding:6px 12px 6px 28px;font-size:13px;color:var(--text);
  outline:none;width:190px;transition:background .14s,width .2s;font-family:inherit;
}
.search:focus{background:var(--input-bg);filter:brightness(1.1);width:230px}
.search::placeholder{color:var(--text2)}

/* ── File tree ── */
.tree{flex:1;overflow-y:auto;padding:6px 0 20px}
.tree::-webkit-scrollbar{width:5px}
.tree::-webkit-scrollbar-thumb{background:rgba(128,128,128,.2);border-radius:3px}
.tree::-webkit-scrollbar-track{background:transparent}

.row{
  display:flex;align-items:center;
  height:34px;padding-right:10px;gap:5px;
  transition:background .08s;cursor:default;
}
.row:hover{background:var(--hover)}
.row:hover .acts{opacity:1}
.row:hover .star-btn{opacity:.5}
.row:hover .note-badge{opacity:.7}

.chev{
  width:16px;height:16px;display:flex;align-items:center;justify-content:center;
  font-size:9px;color:var(--text2);transition:transform .18s ease;flex-shrink:0;
}
.chev.open{transform:rotate(90deg)}
.ico{font-size:14px;flex-shrink:0;width:20px;text-align:center}
.fname{
  flex:1;font-size:13px;font-weight:400;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;
}
.row.isdir .fname{font-weight:500}
.fmeta{font-size:11px;color:var(--text2);white-space:nowrap;margin-right:4px;flex-shrink:0}

.note-badge{
  font-size:10px;font-weight:600;color:var(--accent);
  background:var(--accent-soft);border-radius:8px;padding:1px 5px;
  flex-shrink:0;opacity:0;transition:opacity .13s;cursor:pointer;
}
.note-badge.visible{opacity:1}
.note-badge:hover{opacity:1 !important;background:var(--accent);color:#fff}

.star-btn{
  background:none;border:none;cursor:pointer;
  font-size:13px;padding:2px 4px;border-radius:4px;
  color:var(--text2);opacity:0;
  transition:opacity .13s,color .12s;flex-shrink:0;line-height:1;
}
.star-btn.starred{opacity:1 !important;color:var(--star)}
.star-btn:hover{color:var(--star);opacity:1 !important}

.acts{display:flex;gap:4px;opacity:0;transition:opacity .13s;flex-shrink:0}
.acts button{
  padding:2px 8px;border-radius:5px;
  font-size:11px;font-weight:500;
  cursor:pointer;border:none;
  transition:background .12s,color .12s;font-family:inherit;
}
.btn-f{background:var(--accent-soft);color:var(--accent)}
.btn-f:hover{background:var(--accent);color:#fff}
.btn-v{background:var(--input-bg);color:var(--text2)}
.btn-v:hover{background:rgba(128,128,128,.25);color:var(--text)}
.btn-g{background:var(--green-soft);color:var(--green)}
.btn-g:hover{background:var(--green);color:#fff}
.btn-n{background:var(--accent-soft);color:var(--accent)}
.btn-n:hover{background:var(--accent);color:#fff}

.kids{display:none}.kids.open{display:block}

/* ── Notes panel ── */
.notes-panel{
  width:0;overflow:hidden;
  border-left:0px solid var(--border);
  background:var(--panel);
  display:flex;flex-direction:column;
  transition:width .25s cubic-bezier(.4,0,.2,1), border-color .2s;
  flex-shrink:0;
}
.notes-panel.open{width:300px;border-left:1px solid var(--border)}

.np-head{
  display:flex;align-items:center;gap:8px;
  padding:14px 14px 10px;border-bottom:1px solid var(--border);flex-shrink:0;
}
.np-project-icon{font-size:18px}
.np-title{flex:1;min-width:0}
.np-project{font-size:13px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.np-sub{font-size:11px;color:var(--text2)}
.np-close{
  background:none;border:none;cursor:pointer;
  font-size:16px;color:var(--text2);padding:2px 6px;border-radius:5px;
  transition:background .12s,color .12s;flex-shrink:0;
}
.np-close:hover{background:var(--hover);color:var(--text)}

.np-body{flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:7px}
.np-body::-webkit-scrollbar{width:4px}
.np-body::-webkit-scrollbar-thumb{background:rgba(128,128,128,.2);border-radius:2px}

.note-card{
  background:var(--card);border:1px solid var(--card-border);border-radius:10px;
  padding:9px 10px;display:flex;flex-direction:column;gap:5px;
  transition:opacity .15s;
}
.note-card.done{opacity:.45}
.nc-top{display:flex;align-items:flex-start;gap:8px}
.nc-icon{
  font-size:14px;flex-shrink:0;margin-top:1px;
  width:22px;height:22px;border-radius:6px;
  display:flex;align-items:center;justify-content:center;
}
.nc-icon.idea{background:var(--note-idea-bg)}
.nc-icon.bug{background:var(--note-bug-bg)}
.nc-icon.todo{background:var(--note-todo-bg)}
.nc-text{
  flex:1;font-size:12.5px;line-height:1.45;color:var(--text);
  word-break:break-word;
}
.note-card.done .nc-text{text-decoration:line-through}
.nc-actions{display:flex;gap:5px;align-items:center}
.nc-date{font-size:10.5px;color:var(--text2);flex:1}
.nc-btn{
  background:none;border:none;cursor:pointer;
  font-size:12px;color:var(--text2);padding:2px 5px;border-radius:4px;
  transition:background .12s,color .12s;
}
.nc-btn:hover{background:var(--hover);color:var(--text)}
.nc-btn.done-btn:hover{color:var(--green)}
.nc-btn.del-btn:hover{color:#ff3b30}

.note-card.done .nc-btn.done-btn{color:var(--green)}

.np-empty{
  text-align:center;padding:40px 20px;color:var(--text2);font-size:12.5px;line-height:1.6;
}
.np-empty .big{font-size:28px;display:block;margin-bottom:8px}

.np-footer{padding:10px 12px;border-top:1px solid var(--border);flex-shrink:0}
.np-type-row{display:flex;gap:5px;margin-bottom:7px}
.type-pill{
  flex:1;padding:5px 0;border-radius:7px;border:1px solid var(--border);
  background:none;font-size:11.5px;cursor:pointer;text-align:center;
  transition:all .12s;color:var(--text2);font-family:inherit;
}
.type-pill:hover{background:var(--hover);color:var(--text)}
.type-pill.active{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.np-input-row{display:flex;gap:6px}
.np-input{
  flex:1;background:var(--input-bg);border:1px solid transparent;border-radius:8px;
  padding:7px 10px;font-size:12.5px;color:var(--text);font-family:inherit;
  outline:none;resize:none;height:36px;transition:border-color .15s,height .15s;line-height:1.4;
  overflow:hidden;
}
.np-input:focus{border-color:var(--accent);height:72px;overflow:auto}
.np-input::placeholder{color:var(--text2)}
.np-add{
  background:var(--accent);color:#fff;border:none;border-radius:8px;
  padding:7px 12px;font-size:12px;font-weight:600;cursor:pointer;
  transition:opacity .12s;align-self:flex-end;height:36px;font-family:inherit;
  white-space:nowrap;flex-shrink:0;
}
.np-add:hover{opacity:.85}

/* ── Recents & Favorites views ── */
.list-view{padding:16px}
.lv-section{margin-bottom:20px}
.lv-label{
  font-size:11px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;
  color:var(--text2);margin-bottom:8px;
}
.lv-card{
  display:flex;align-items:center;gap:10px;
  padding:9px 12px;border-radius:10px;border:1px solid var(--border);
  background:var(--card);margin-bottom:6px;
  transition:background .12s;
}
.lv-card:hover{background:var(--hover)}
.lv-card:hover .acts{opacity:1}
.lv-card:hover .star-btn{opacity:.5}
.lv-ico{font-size:20px;flex-shrink:0}
.lv-info{flex:1;min-width:0}
.lv-name{font-size:13px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lv-path{font-size:10.5px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:"SF Mono",ui-monospace,monospace}
.lv-action-tag{
  font-size:10px;color:var(--text2);background:var(--input-bg);
  border-radius:5px;padding:1px 6px;flex-shrink:0;
}

/* ── Empty / loading ── */
.empty-state{
  display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:8px;height:200px;
  color:var(--text2);font-size:13px;
}
.empty-state .big{font-size:32px}
.empty-state p{text-align:center;line-height:1.5;max-width:220px}

/* ── Controls bar (sort) ── */
.controls-bar{
  display:flex;align-items:center;gap:6px;
  padding:5px 16px;border-bottom:1px solid var(--border);
  background:var(--content);flex-shrink:0;min-height:0;
  transition:background .2s,border-color .2s;
}
.controls-bar:empty{padding:0;border:none}
.sort-label{font-size:11px;color:var(--text2);margin-right:2px;user-select:none}
.sort-btn{
  border:1px solid var(--border);border-radius:6px;
  background:transparent;padding:3px 9px;
  font-size:11.5px;font-weight:500;color:var(--text2);
  cursor:pointer;transition:background .12s,color .12s,border-color .12s;font-family:inherit;
}
.sort-btn:hover{background:var(--hover);color:var(--text)}
.sort-btn.active{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
.sort-sep{width:1px;height:16px;background:var(--border);margin:0 4px;flex-shrink:0}

/* ── Activity label ── */
.factivity{
  font-size:10px;color:var(--text3);margin-right:2px;flex-shrink:0;white-space:nowrap;
}
.factivity.fresh{color:var(--green)}
.factivity.recent{color:var(--accent)}

/* ── Spotlight (CMD+K) ── */
.spotlight-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.45);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  z-index:1000;display:none;align-items:flex-start;justify-content:center;padding-top:80px;
}
.spotlight-overlay.open{display:flex}
.spotlight-modal{
  width:560px;max-width:92vw;
  background:var(--content);border:1px solid var(--border);
  border-radius:14px;box-shadow:0 24px 64px rgba(0,0,0,.3);
  overflow:hidden;
}
[data-theme="dark"] .spotlight-modal{box-shadow:0 24px 64px rgba(0,0,0,.6)}
.sp-input-wrap{
  display:flex;align-items:center;gap:10px;
  padding:14px 16px;border-bottom:1px solid var(--border);
}
.sp-icon{font-size:17px;color:var(--text2);flex-shrink:0}
.sp-input{
  flex:1;background:none;border:none;outline:none;
  font-size:15px;color:var(--text);font-family:inherit;
}
.sp-input::placeholder{color:var(--text2)}
.sp-kbd{
  font-size:10px;color:var(--text2);background:var(--input-bg);
  border-radius:5px;padding:2px 6px;flex-shrink:0;
  font-family:"SF Mono",ui-monospace,monospace;
}
.sp-results{max-height:340px;overflow-y:auto}
.sp-empty{padding:24px;text-align:center;color:var(--text2);font-size:13px}
.sp-item{
  display:flex;align-items:center;gap:10px;
  padding:9px 16px;cursor:pointer;transition:background .07s;
}
.sp-item:hover,.sp-item.sp-sel{background:var(--accent);color:#fff}
.sp-item:hover .sp-path,.sp-item.sp-sel .sp-path{color:rgba(255,255,255,.7)}
.sp-item:hover .sp-tag,.sp-item.sp-sel .sp-tag{background:rgba(255,255,255,.2);color:#fff}
.sp-ico{font-size:16px;flex-shrink:0;width:24px;text-align:center}
.sp-info{flex:1;min-width:0}
.sp-name{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-path{font-size:11px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:"SF Mono",ui-monospace,monospace;transition:color .07s}
.sp-tag{font-size:10px;color:var(--text2);background:var(--input-bg);border-radius:4px;padding:1px 6px;flex-shrink:0;transition:background .07s,color .07s}
.sp-hint{padding:8px 16px;font-size:10.5px;color:var(--text2);border-top:1px solid var(--border);display:flex;gap:12px}
.sp-hint kbd{background:var(--input-bg);border-radius:4px;padding:1px 5px;font-family:"SF Mono",ui-monospace,monospace}

/* ── Notes overview ── */
.notes-folder-header{
  font-size:11px;color:var(--text2);
  font-family:"SF Mono",ui-monospace,monospace;
  padding:6px 0 3px;margin-top:10px;
  cursor:pointer;transition:color .12s;border-bottom:1px solid var(--border);
  padding-bottom:4px;
}
.notes-folder-header:hover{color:var(--accent)}

/* ── Toast ── */
#toast{
  position:fixed;bottom:24px;left:50%;
  transform:translateX(-50%) translateY(56px);
  background:rgba(28,28,30,.9);color:#fff;
  padding:7px 16px;border-radius:20px;
  font-size:12.5px;font-weight:500;
  transition:transform .26s cubic-bezier(.34,1.56,.64,1);
  pointer-events:none;z-index:200;white-space:nowrap;
  backdrop-filter:blur(12px);
}
#toast.show{transform:translateX(-50%) translateY(0)}
</style>
</head>
<body>

<div class="bar">
  <div class="lights">
    <div class="dot d-red"></div>
    <div class="dot d-yel"></div>
    <div class="dot d-grn"></div>
  </div>
  <div class="bar-title">Claude Dashboard</div>
  <div class="bar-actions">
    <button class="theme-btn" id="theme-btn" onclick="toggleTheme()" title="Dark/Light mode">🌙</button>
    <button class="bar-btn" onclick="reload()">↻ Vernieuwen</button>
  </div>
</div>

<div class="layout">
  <nav class="sidebar">
    <div class="s-label">Snel</div>
    <div class="nav" data-view="favorites" onclick="showView('favorites')">
      <span class="ni">⭐</span> Favorieten
      <span class="badge orange" id="fav-count">0</span>
    </div>
    <div class="nav" data-view="recents" onclick="showView('recents')">
      <span class="ni">🕐</span> Recents
      <span class="badge" id="rec-count">0</span>
    </div>

    <div class="s-label">Projecten</div>
    <div class="nav active" data-view="projects" onclick="showView('projects')">
      <span class="ni">📁</span> Projects
    </div>

    <div class="s-label">Config</div>
    <div class="nav" data-view="config" onclick="showView('config')">
      <span class="ni">⚙️</span> Claude Config
    </div>

    <div class="s-label">Notities</div>
    <div class="nav" data-view="notes" onclick="showView('notes')">
      <span class="ni">📋</span> Alle Notities
      <span class="badge orange" id="notes-count">0</span>
    </div>
  </nav>

  <div class="content">
    <div class="content-head">
      <div>
        <div class="ch-title" id="head-title">Projects</div>
        <div class="ch-path"  id="head-path">~/claude</div>
      </div>
      <div class="search-wrap">
        <span class="search-icon">⌕</span>
        <input class="search" type="text" placeholder="Zoeken…" id="search" oninput="filterTree(this.value)">
      </div>
    </div>
    <div class="controls-bar" id="controls-bar"></div>
    <div class="tree" id="tree"></div>
  </div>

  <div class="notes-panel" id="notes-panel">
    <div class="np-head">
      <span class="np-project-icon" id="np-icon">📁</span>
      <div class="np-title">
        <div class="np-project" id="np-project">Project</div>
        <div class="np-sub"    id="np-sub">Notities</div>
      </div>
      <button class="np-close" onclick="closeNotes()">✕</button>
    </div>
    <div class="np-body" id="np-body"></div>
    <div class="np-footer">
      <div class="np-type-row" id="np-types">
        <button class="type-pill active" data-type="idea"  onclick="setNoteType('idea')">💡 Idee</button>
        <button class="type-pill"        data-type="bug"   onclick="setNoteType('bug')">🐛 Bug</button>
        <button class="type-pill"        data-type="todo"  onclick="setNoteType('todo')">📌 Todo</button>
      </div>
      <div class="np-input-row">
        <textarea class="np-input" id="np-input" placeholder="Nieuwe notitie…" rows="1"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();addNote()}"></textarea>
        <button class="np-add" onclick="addNote()">+ Toevoegen</button>
      </div>
    </div>
  </div>
</div>

<div class="spotlight-overlay" id="spotlight-overlay" onclick="closeSpotlight()">
  <div class="spotlight-modal" onclick="event.stopPropagation()">
    <div class="sp-input-wrap">
      <span class="sp-icon">⌕</span>
      <input class="sp-input" id="sp-input" placeholder="Zoek projecten, bestanden, notities…"
             oninput="searchSpotlight(this.value)"
             onkeydown="handleSpotlightKey(event)" autocomplete="off">
      <span class="sp-kbd">esc</span>
    </div>
    <div class="sp-results" id="sp-results"></div>
    <div class="sp-hint">
      <span><kbd>↑↓</kbd> navigeren</span>
      <span><kbd>↵</kbd> openen</span>
      <span><kbd>esc</kbd> sluiten</span>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const HOME = '__HOME__';
const PROJECTS_ROOT = HOME + '/claude';

const EXT_ICONS = {
  '.md':'📝','.txt':'📄','.json':'📋','.jsonl':'📋',
  '.py':'🐍','.js':'📜','.ts':'📜','.tsx':'📜','.sh':'⚙️',
  '.csv':'📊','.xlsx':'📊','.xls':'📊',
  '.log':'📋','.workspace':'🗂️','.env':'🔒',
  '.pdf':'📑','.png':'🖼️','.jpg':'🖼️','.jpeg':'🖼️','.svg':'🖼️',
  '.html':'🌐','.css':'🎨','.lock':'🔒',
};
const TYPE_META = {
  idea: {icon:'💡',cls:'idea'},
  bug:  {icon:'🐛',cls:'bug'},
  todo: {icon:'📌',cls:'todo'},
};

let currentView   = 'projects';
let currentSort   = 'name';
let treeData      = null;
let favorites     = new Set();
let spIndex       = -1;
let spItems       = [];
let allNotes      = {};   // path -> [note]
let noteProject   = null; // currently open notes project path
let noteType      = 'idea';

// ── Theme ─────────────────────────────────────────────────────────────────────
function loadTheme(){
  const t = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-btn').textContent = t === 'dark' ? '☀️' : '🌙';
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.getElementById('theme-btn').textContent = next === 'dark' ? '☀️' : '🌙';
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function icon(name, isDir, ext){ return isDir ? '📁' : (EXT_ICONS[ext] || '📄'); }

function shortPath(p){ return p.replace(HOME, '~'); }

function timeAgo(iso){
  const s = (Date.now() - new Date(iso)) / 1000;
  if(s < 60)   return 'zojuist';
  if(s < 3600) return Math.floor(s/60) + ' min geleden';
  if(s < 86400) return Math.floor(s/3600) + ' uur geleden';
  if(s < 86400*7) return Math.floor(s/86400) + ' dag' + (Math.floor(s/86400)>1?'en':'') + ' geleden';
  return new Date(iso).toLocaleDateString('nl-NL',{day:'numeric',month:'short'});
}

function noteCount(path){ return (allNotes[path] || []).filter(n=>!n.done).length; }

function activityLabel(ts){
  const s = Date.now()/1000 - ts;
  if(s < 86400)    return 'vandaag';
  if(s < 172800)   return 'gisteren';
  if(s < 604800)   return Math.floor(s/86400) + 'd geleden';
  if(s < 2592000)  return Math.floor(s/604800) + 'w geleden';
  return Math.floor(s/2592000) + 'mo geleden';
}

function sortedKids(kids){
  if(currentSort === 'active')   return [...kids].sort((a,b)=>(b.last_ts||0)-(a.last_ts||0));
  if(currentSort === 'inactive') return [...kids].sort((a,b)=>(a.last_ts||0)-(b.last_ts||0));
  return [...kids].sort((a,b)=>a.name.localeCompare(b.name,'nl'));
}

// ── Notes ─────────────────────────────────────────────────────────────────────
async function loadAllNotes(){
  const res = await fetch('/api/notes');
  allNotes = await res.json();
  updateNoteBadges();
  updateNotesNavCount();
}

function updateNoteBadges(){
  document.querySelectorAll('.note-badge').forEach(el=>{
    const p = el.dataset.path;
    const c = noteCount(p);
    el.textContent = c + ' 📝';
    el.classList.toggle('visible', c > 0);
  });
}

function setNoteType(t){
  noteType = t;
  document.querySelectorAll('.type-pill').forEach(el=>{
    el.classList.toggle('active', el.dataset.type === t);
  });
}

function openNotes(path, name, ico){
  noteProject = path;
  document.getElementById('np-project').textContent = name;
  document.getElementById('np-sub').textContent = shortPath(path);
  document.getElementById('np-icon').textContent = ico;
  document.getElementById('notes-panel').classList.add('open');
  renderNotesList(allNotes[path] || []);
  document.getElementById('np-input').focus();
}

function closeNotes(){
  document.getElementById('notes-panel').classList.remove('open');
  noteProject = null;
}

function renderNotesList(notes){
  const body = document.getElementById('np-body');
  const active = notes.filter(n=>!n.done);
  const done   = notes.filter(n=> n.done);
  const sorted = [...active,...done];

  if(!sorted.length){
    body.innerHTML = '<div class="np-empty"><span class="big">📋</span>Nog geen notities.<br>Voeg een idee, bug of todo toe!</div>';
    return;
  }

  body.innerHTML = '';
  sorted.forEach(n=>{
    const tm = TYPE_META[n.type] || TYPE_META.idea;
    const card = el('div','note-card' + (n.done?' done':''));

    const top = el('div','nc-top');

    const ico = el('div','nc-icon ' + tm.cls);
    ico.textContent = tm.icon;
    top.appendChild(ico);

    const txt = el('div','nc-text');
    txt.textContent = n.text;
    top.appendChild(txt);
    card.appendChild(top);

    const actions = el('div','nc-actions');
    const date = el('span','nc-date');
    date.textContent = timeAgo(n.created);
    actions.appendChild(date);

    const doneBtn = el('button','nc-btn done-btn');
    doneBtn.textContent = n.done ? '↩ Heropen' : '✓ Klaar';
    doneBtn.title = n.done ? 'Heropen' : 'Markeer als klaar';
    doneBtn.onclick = ()=> toggleNote(n.id);
    actions.appendChild(doneBtn);

    const delBtn = el('button','nc-btn del-btn');
    delBtn.textContent = '✕';
    delBtn.title = 'Verwijder';
    delBtn.onclick = ()=> deleteNote(n.id);
    actions.appendChild(delBtn);

    card.appendChild(actions);
    body.appendChild(card);
  });
}

async function addNote(){
  const input = document.getElementById('np-input');
  const text = input.value.trim();
  if(!text || !noteProject) return;
  const url = '/api/notes/add?path=' + enc(noteProject) + '&type=' + noteType + '&text=' + enc(text);
  const res = await fetch(url);
  const data = await res.json();
  allNotes[noteProject] = data.notes;
  renderNotesList(data.notes);
  updateNoteBadges();
  updateNotesNavCount();
  input.value = '';
  input.style.height = '';
}

async function toggleNoteForPath(path, nid){
  const res = await fetch('/api/notes/toggle?path=' + enc(path) + '&id=' + enc(nid));
  const data = await res.json();
  allNotes[path] = data.notes;
  if(noteProject === path) renderNotesList(data.notes);
  updateNoteBadges();
  updateNotesNavCount();
}

async function deleteNoteForPath(path, nid){
  const res = await fetch('/api/notes/delete?path=' + enc(path) + '&id=' + enc(nid));
  const data = await res.json();
  allNotes[path] = data.notes;
  if(noteProject === path) renderNotesList(data.notes);
  updateNoteBadges();
  updateNotesNavCount();
}

async function toggleNote(nid){
  if(!noteProject) return;
  await toggleNoteForPath(noteProject, nid);
}

async function deleteNote(nid){
  if(!noteProject) return;
  await deleteNoteForPath(noteProject, nid);
}

// ── Favorites ─────────────────────────────────────────────────────────────────
async function loadFavorites(){
  const res = await fetch('/api/favorites');
  const list = await res.json();
  favorites = new Set(list);
  document.getElementById('fav-count').textContent = favorites.size || '0';
}

async function toggleFav(path, btn){
  const res  = await fetch('/api/favorites/toggle?path=' + enc(path));
  const data = await res.json();
  favorites  = new Set(data.favorites);
  document.getElementById('fav-count').textContent = favorites.size || '0';
  document.querySelectorAll(`.star-btn[data-path]`).forEach(b=>{
    if(b.dataset.path === path) b.classList.toggle('starred', data.added);
  });
  showToast(data.added ? '⭐ Toegevoegd' : '✕ Verwijderd uit favorieten');
  if(currentView === 'favorites') renderListView('favorites');
}

// ── Recents ───────────────────────────────────────────────────────────────────
async function loadRecents(){
  const res = await fetch('/api/recents');
  const list = await res.json();
  document.getElementById('rec-count').textContent = list.length || '0';
  return list;
}

// ── Open file ─────────────────────────────────────────────────────────────────
async function openFile(action, path){
  try{
    await fetch('/api/open?action=' + action + '&path=' + enc(path));
    const msgs = {finder:'📁 Finder', vscode:'💻 VS Code', ghostty:'👻 Ghostty + Claude'};
    showToast('Geopend in ' + (msgs[action] || action));
    if(action === 'ghostty') loadRecents();
    else loadRecents();
  }catch(e){ showToast('⚠️ Kon niet openen'); }
}

// ── Views ─────────────────────────────────────────────────────────────────────
async function showView(view){
  currentView = view;
  document.getElementById('search').value = '';
  document.getElementById('search').style.display = ['projects','config'].includes(view) ? '' : 'none';
  closeNotes();

  document.querySelectorAll('.nav').forEach(el=>{
    el.classList.toggle('active', el.dataset.view === view);
  });

  const titles = {
    projects: ['Projects','~/claude'],
    config:   ['Claude Config','~/.claude'],
    favorites:['Favorieten',''],
    recents:  ['Recents',''],
    notes:    ['Alle Notities',''],
  };
  const [title, path] = titles[view] || [view,''];
  document.getElementById('head-title').textContent = title;
  document.getElementById('head-path').textContent  = path;
  renderSortControls(view);

  if(view === 'projects' || view === 'config'){
    await loadTreeView(view);
  } else if(view === 'notes'){
    await loadAllNotes();
    renderNotesView();
  } else {
    await renderListView(view);
  }
}

async function loadTreeView(root){
  const tree = document.getElementById('tree');
  tree.innerHTML = '<div class="empty-state"><div class="big">⏳</div></div>';
  try{
    const res = await fetch('/api/files?root=' + root);
    treeData = await res.json();
    renderTree(treeData, root === 'projects');
  }catch(e){
    tree.innerHTML = '<div class="empty-state"><div class="big">⚠️</div><div>Laden mislukt</div></div>';
  }
}

async function renderListView(view){
  const tree = document.getElementById('tree');
  tree.innerHTML = '';

  if(view === 'favorites'){
    if(!favorites.size){
      tree.innerHTML = '<div class="empty-state"><div class="big">⭐</div><p>Nog geen favorieten.<br>Hover een bestand en klik ☆</p></div>';
      return;
    }
    const wrapper = el('div','list-view');
    const byRoot = {'Projects':[], 'Claude Config':[]};
    favorites.forEach(p=>{
      const label = (p === PROJECTS_ROOT || p.startsWith(PROJECTS_ROOT + '/')) ? 'Projects' : 'Claude Config';
      byRoot[label].push(p);
    });
    for(const [label, paths] of Object.entries(byRoot)){
      if(!paths.length) continue;
      const sec = el('div','lv-section');
      const lbl = el('div','lv-label'); lbl.textContent = label; sec.appendChild(lbl);
      paths.sort().forEach(p=>{
        const name = p.split('/').pop();
        const ext  = name.includes('.') ? '.' + name.split('.').pop().toLowerCase() : '';
        const isDir = !name.match(/\.[a-zA-Z0-9]{1,6}$/);
        sec.appendChild(makeLvCard(p, name, icon(name,isDir,ext), isDir, null));
      });
      wrapper.appendChild(sec);
    }
    tree.appendChild(wrapper);

  } else if(view === 'recents'){
    const recents = await loadRecents();
    if(!recents.length){
      tree.innerHTML = '<div class="empty-state"><div class="big">🕐</div><p>Nog niets geopend.<br>Gebruik Finder, VS Code of Ghostty.</p></div>';
      return;
    }
    const wrapper = el('div','list-view');
    const groups  = {};
    recents.forEach(r=>{
      const d = new Date(r.timestamp);
      const now = new Date();
      let g = 'Eerder';
      if(d.toDateString() === now.toDateString()) g = 'Vandaag';
      else{
        const yest = new Date(now); yest.setDate(yest.getDate()-1);
        if(d.toDateString() === yest.toDateString()) g = 'Gisteren';
      }
      if(!groups[g]) groups[g] = [];
      groups[g].push(r);
    });
    for(const [g, items] of Object.entries(groups)){
      const sec = el('div','lv-section');
      const lbl = el('div','lv-label'); lbl.textContent = g; sec.appendChild(lbl);
      items.forEach(r=>{
        const card = makeLvCard(r.path, r.name, icon(r.name,r.dir,r.ext), r.dir, r);
        sec.appendChild(card);
      });
      wrapper.appendChild(sec);
    }
    tree.appendChild(wrapper);
  }
}

function makeLvCard(path, name, ico, isDir, recent){
  const card = el('div','lv-card');

  const i = el('div','lv-ico'); i.textContent = ico; card.appendChild(i);

  const info = el('div','lv-info');
  const nm = el('div','lv-name'); nm.textContent = name; info.appendChild(nm);
  const pp = el('div','lv-path'); pp.textContent = shortPath(path); info.appendChild(pp);
  card.appendChild(info);

  if(recent){
    const tag = el('span','lv-action-tag');
    const tagMap = {finder:'Finder',vscode:'VS Code',ghostty:'Ghostty'};
    tag.textContent = tagMap[recent.action] || recent.action;
    card.appendChild(tag);
  }

  const nc = noteCount(path);
  if(nc > 0){
    const nb = el('span','note-badge visible');
    nb.dataset.path = path;
    nb.textContent = nc + ' 📝';
    nb.title = 'Notities openen';
    nb.onclick = e => { e.stopPropagation(); openNotes(path, name, ico); };
    card.appendChild(nb);
  }

  const star = makeStar(path);
  card.appendChild(star);

  const acts = el('div','acts');
  acts.appendChild(makeBtn('Finder','btn-f',()=>openFile('finder',path)));
  acts.appendChild(makeBtn('VS Code','btn-v',()=>openFile('vscode',path)));
  if(isDir) acts.appendChild(makeBtn('Claude','btn-g',()=>openFile('ghostty',path)));
  card.appendChild(acts);
  return card;
}

// ── Tree rendering ─────────────────────────────────────────────────────────────
function renderTree(data, isProjects){
  const tree = document.getElementById('tree');
  tree.innerHTML = '';
  if(!data?.kids?.length){
    tree.innerHTML = '<div class="empty-state"><div class="big">📭</div><div>Geen bestanden</div></div>';
    return;
  }
  const kids = isProjects ? sortedKids(data.kids) : data.kids;
  kids.forEach(node => tree.appendChild(renderNode(node, 0, isProjects)));
}

function renderNode(node, depth, isProjects){
  const wrap = el('div','');

  const row = el('div','row' + (node.dir?' isdir':''));
  row.style.paddingLeft = (12 + depth * 18) + 'px';

  const chev = el('span','chev');
  chev.textContent = node.dir && node.kids.length ? '▶' : '';
  row.appendChild(chev);

  const ico = el('span','ico');
  ico.textContent = icon(node.name, node.dir, node.ext);
  row.appendChild(ico);

  const fname = el('span','fname');
  fname.textContent = node.name;
  row.appendChild(fname);

  const meta = el('span','fmeta');
  meta.textContent = node.dir ? node.mod : (node.size + ' · ' + node.mod);
  row.appendChild(meta);

  // Activity label for top-level project dirs
  if(node.dir && depth === 0 && isProjects && node.last_ts){
    const lbl = activityLabel(node.last_ts);
    const act = el('span','factivity' + (lbl==='vandaag'?' fresh':lbl==='gisteren'?' recent':''));
    act.textContent = lbl;
    row.appendChild(act);
  }

  // Note badge (all dirs)
  if(node.dir){
    const nb = el('span','note-badge');
    nb.dataset.path = node.path;
    nb.textContent = '0 📝';
    nb.title = 'Notities';
    nb.onclick = e => { e.stopPropagation(); openNotes(node.path, node.name, '📁'); };
    row.appendChild(nb);
  }

  // Star
  row.appendChild(makeStar(node.path));

  // Actions
  const acts = el('div','acts');
  acts.appendChild(makeBtn('Finder','btn-f',()=>openFile('finder',node.path)));
  acts.appendChild(makeBtn('VS Code','btn-v',()=>openFile('vscode',node.path)));
  if(node.dir){
    acts.appendChild(makeBtn('Claude','btn-g',()=>openFile('ghostty',node.path)));
    acts.appendChild(makeBtn('📝','btn-n',()=>openNotes(node.path,node.name,'📁')));
  }
  row.appendChild(acts);
  wrap.appendChild(row);

  if(node.dir && node.kids.length){
    const kids = el('div','kids');
    node.kids.forEach(k => kids.appendChild(renderNode(k, depth+1, isProjects)));
    wrap.appendChild(kids);
    row.style.cursor = 'pointer';
    row.onclick = ()=>{
      const open = kids.classList.toggle('open');
      chev.classList.toggle('open', open);
    };
    if(depth === 0){ kids.classList.add('open'); chev.classList.add('open'); }
  }

  return wrap;
}

function filterTree(query){
  if(!treeData) return;
  if(!query.trim()){ renderTree(treeData, currentView==='projects'); return; }
  const q = query.toLowerCase();
  function filterNode(n){
    if(n.name.toLowerCase().includes(q)) return n;
    if(!n.dir) return null;
    const kids = n.kids.map(filterNode).filter(Boolean);
    return kids.length ? {...n, kids} : null;
  }
  const filtered = {...treeData, kids: treeData.kids.map(filterNode).filter(Boolean)};
  renderTree(filtered, currentView==='projects');
  document.querySelectorAll('.kids').forEach(e=>e.classList.add('open'));
  document.querySelectorAll('.chev').forEach(e=>e.classList.add('open'));
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
function el(tag, cls){ const e = document.createElement(tag||'div'); if(cls) e.className=cls; return e; }
function enc(s){ return encodeURIComponent(s); }

function makeBtn(label, cls, fn){
  const b = el('button', cls); b.textContent = label;
  b.onclick = e => { e.stopPropagation(); fn(); }; return b;
}

function makeStar(path){
  const s = el('button','star-btn' + (favorites.has(path)?' starred':''));
  s.dataset.path = path; s.textContent = '★';
  s.title = favorites.has(path) ? 'Verwijder' : 'Voeg toe aan favorieten';
  s.onclick = e => { e.stopPropagation(); toggleFav(path,s); };
  return s;
}

let toastTimer;
function showToast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>t.classList.remove('show'), 2200);
}

function reload(){
  showView(currentView);
}

// ── Sort controls ────────────────────────────────────────────────────────────
function renderSortControls(view){
  const bar = document.getElementById('controls-bar');
  if(view !== 'projects'){ bar.innerHTML = ''; return; }
  bar.innerHTML = '';
  const lbl = el('span','sort-label'); lbl.textContent = 'Sorteren:'; bar.appendChild(lbl);
  [
    {key:'name',    txt:'A-Z'},
    {key:'active',  txt:'🕐 Actief eerst'},
    {key:'inactive',txt:'Inactief eerst'},
  ].forEach(s => {
    const btn = el('button','sort-btn' + (currentSort===s.key?' active':''));
    btn.textContent = s.txt;
    btn.onclick = () => { currentSort = s.key; renderSortControls(view); if(treeData) renderTree(treeData, true); };
    bar.appendChild(btn);
  });
  const sep = el('span','sort-sep'); bar.appendChild(sep);
  const colBtn = el('button','sort-btn');
  colBtn.textContent = '⊟ Inklappen';
  colBtn.title = 'Klap alle mappen in';
  colBtn.onclick = () => {
    document.querySelectorAll('.kids').forEach(k => k.classList.remove('open'));
    document.querySelectorAll('.chev').forEach(c => c.classList.remove('open'));
  };
  bar.appendChild(colBtn);
}

// ── Spotlight (CMD+K) ────────────────────────────────────────────────────────
function openSpotlight(){
  document.getElementById('spotlight-overlay').classList.add('open');
  const inp = document.getElementById('sp-input');
  inp.value = ''; inp.focus();
  spIndex = -1; spItems = [];
  document.getElementById('sp-results').innerHTML = '<div class="sp-empty">Typ om te zoeken in projecten, bestanden en notities</div>';
}

function closeSpotlight(){
  document.getElementById('spotlight-overlay').classList.remove('open');
  spIndex = -1;
}

function searchSpotlight(q){
  spIndex = -1;
  const results = document.getElementById('sp-results');
  if(!q.trim()){
    results.innerHTML = '<div class="sp-empty">Typ om te zoeken…</div>';
    spItems = []; return;
  }
  const query = q.toLowerCase();
  const found = [];

  function searchNode(node, d){
    if(node.name !== (treeData && treeData.name) && node.name.toLowerCase().includes(query)){
      found.push({type:node.dir?'dir':'file', ico:icon(node.name,node.dir,node.ext), name:node.name, path:node.path});
    }
    if(node.kids) node.kids.forEach(k=>searchNode(k,d+1));
  }
  if(treeData) searchNode(treeData, 0);

  Object.entries(allNotes).forEach(([path,notes])=>{
    notes.forEach(n=>{
      if(n.text.toLowerCase().includes(query)){
        const tm = TYPE_META[n.type]||TYPE_META.idea;
        found.push({type:'note', ico:tm.icon, name:n.text, path, done:n.done, noteType:n.type});
      }
    });
  });

  spItems = found.slice(0,10);
  renderSpItems();
}

function renderSpItems(){
  const container = document.getElementById('sp-results');
  container.innerHTML = '';
  if(!spItems.length){
    container.innerHTML = '<div class="sp-empty">Geen resultaten</div>'; return;
  }
  spItems.forEach((item,i)=>{
    const row = el('div','sp-item'+(i===spIndex?' sp-sel':''));
    const ico = el('div','sp-ico'); ico.textContent = item.ico; row.appendChild(ico);
    const info = el('div','sp-info');
    const name = el('div','sp-name'); name.textContent = item.name; info.appendChild(name);
    const path = el('div','sp-path'); path.textContent = shortPath(item.path); info.appendChild(path);
    row.appendChild(info);
    const tag = el('span','sp-tag');
    tag.textContent = item.type==='dir'?'Map':item.type==='note'?(item.done?'✓ Klaar':'📝 Note'):'Bestand';
    row.appendChild(tag);
    row.onclick = ()=>{ activateSpItem(item); closeSpotlight(); };
    container.appendChild(row);
  });
}

function activateSpItem(item){
  if(item.type==='dir'){
    openFile('ghostty', item.path);
  } else if(item.type==='file'){
    openFile('vscode', item.path);
  } else if(item.type==='note'){
    const name = item.path.split('/').pop();
    if(currentView!=='projects') showView('projects');
    openNotes(item.path, name, '📁');
  }
}

function handleSpotlightKey(e){
  if(e.key==='Escape'){ closeSpotlight(); return; }
  if(e.key==='ArrowDown'){
    e.preventDefault(); spIndex = Math.min(spIndex+1, spItems.length-1); renderSpItems();
  } else if(e.key==='ArrowUp'){
    e.preventDefault(); spIndex = Math.max(spIndex-1, 0); renderSpItems();
  } else if(e.key==='Enter'){
    e.preventDefault();
    const item = spItems[spIndex >= 0 ? spIndex : 0];
    if(item){ activateSpItem(item); closeSpotlight(); }
  }
}

// ── Notes overview ────────────────────────────────────────────────────────────
function updateNotesNavCount(){
  const total = Object.values(allNotes).flat().filter(n=>!n.done).length;
  const badge = document.getElementById('notes-count');
  if(badge) badge.textContent = total || '0';
}

function renderNotesView(){
  const tree = document.getElementById('tree');
  tree.innerHTML = '';

  const entries = Object.entries(allNotes).filter(([,notes]) => notes.length > 0);
  if(!entries.length){
    tree.innerHTML = '<div class="empty-state"><div class="big">📋</div><p>Nog geen notities.<br>Hover een map en klik 📝</p></div>';
    return;
  }

  // Group by top-level project folder under ~/claude
  const groups = {};
  entries.forEach(([path, notes]) => {
    let gkey;
    if(path === PROJECTS_ROOT) gkey = 'claude';
    else if(path.startsWith(PROJECTS_ROOT + '/')){
      const rel = path.slice(PROJECTS_ROOT.length + 1);
      gkey = rel.split('/')[0];
    } else {
      gkey = shortPath(path);
    }
    if(!groups[gkey]) groups[gkey] = [];
    groups[gkey].push({path, notes});
  });

  const wrapper = el('div','list-view');

  Object.keys(groups).sort().forEach(gkey => {
    const items = groups[gkey];
    const openCount = items.reduce((s,{notes})=>s+notes.filter(n=>!n.done).length, 0);
    const doneCount = items.reduce((s,{notes})=>s+notes.filter(n=> n.done).length, 0);

    const sec = el('div','lv-section');
    const lbl = el('div','lv-label');
    let lblTxt = gkey;
    if(openCount) lblTxt += '  ·  ' + openCount + ' open';
    if(doneCount) lblTxt += '  ·  ' + doneCount + ' klaar';
    lbl.textContent = lblTxt;
    sec.appendChild(lbl);

    items.sort((a,b)=>a.path.localeCompare(b.path)).forEach(({path, notes}) => {
      if(!notes.length) return;

      const folderRow = el('div','notes-folder-header');
      folderRow.textContent = shortPath(path);
      folderRow.title = 'Open notitievenster';
      folderRow.onclick = () => openNotes(path, path.split('/').pop(), '📁');
      sec.appendChild(folderRow);

      const active   = notes.filter(n=>!n.done);
      const finished = notes.filter(n=> n.done);
      [...active, ...finished].forEach(n => {
        const tm = TYPE_META[n.type] || TYPE_META.idea;
        const card = el('div','note-card' + (n.done?' done':''));

        const top = el('div','nc-top');
        const ico = el('div','nc-icon ' + tm.cls); ico.textContent = tm.icon; top.appendChild(ico);
        const txt = el('div','nc-text'); txt.textContent = n.text; top.appendChild(txt);
        card.appendChild(top);

        const actions = el('div','nc-actions');
        const date = el('span','nc-date'); date.textContent = timeAgo(n.created); actions.appendChild(date);

        const doneBtn = el('button','nc-btn done-btn');
        doneBtn.textContent = n.done ? '↩ Heropen' : '✓ Klaar';
        doneBtn.onclick = async () => { await toggleNoteForPath(path, n.id); renderNotesView(); };
        actions.appendChild(doneBtn);

        const delBtn = el('button','nc-btn del-btn');
        delBtn.textContent = '✕';
        delBtn.onclick = async () => { await deleteNoteForPath(path, n.id); renderNotesView(); };
        actions.appendChild(delBtn);

        card.appendChild(actions);
        sec.appendChild(card);
      });
    });

    wrapper.appendChild(sec);
  });

  tree.appendChild(wrapper);
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async()=>{
  loadTheme();
  await Promise.all([loadFavorites(), loadAllNotes(), loadRecents()]);
  showView('projects');
  updateNoteBadges();

  document.addEventListener('keydown', e => {
    if((e.metaKey||e.ctrlKey) && e.key==='k'){
      e.preventDefault();
      const ov = document.getElementById('spotlight-overlay');
      ov.classList.contains('open') ? closeSpotlight() : openSpotlight();
    }
  });
})();
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    server = http.server.HTTPServer(('localhost', PORT), Handler)
    url    = f'http://localhost:{PORT}'
    print(f'\n  Claude Dashboard  →  {url}')
    print('  Stop met Ctrl+C\n')
    Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  Dashboard gestopt.')
