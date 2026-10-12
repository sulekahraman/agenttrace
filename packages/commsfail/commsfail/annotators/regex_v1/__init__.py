"""regex_v1: the reference annotator. Transcript-only pattern matching over posts.

Good at repetition and heartbeat cost. Weak wherever a judgment about silence (B1, D3, D4) or a fact from
the record (D1, D2) is needed; where the source cannot show a fact, the mode is reported with low confidence
or as unknown. Every evidence row is a pointer for a human to read, not a label. Output: analysis.v1
(schema.json in this folder). See README.md in this folder.
"""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from ..taxonomy import base_analysis, set_mode, severity_for
from ...sources.sharednet import parse_ts, redact
from ...trace import Trace

# work items: files, harness ids, artifact ids, backticked tokens. Version strings and #n refs are not items.
ITEM_RE = re.compile(r"`([^`\n]{2,60})`|\b([\w./-]+\.(?:py|ts|tsx|js|mjs|md|json|yaml|yml|sql|sh|go|rs|java|c|h|css|html|tex|bib|tgz|zip|csv))\b|\b([WT]\d{1,3}[a-z]?)\b|\b(art_[A-Za-z0-9]{10})\b", re.I)
SEQREF_RE = re.compile(r"#(\d{1,4})\b")
ACCEPT_RE = re.compile(r"\b(i(?:'ll| will|'m| am)?\s*(?:take|taking|handle|handling|own|implement(?:ing)?|start(?:ing)? on|work(?:ing)? on|grab(?:bing)?|claim(?:ing)?|pick(?:ing)? up)|i'll do|on it|split accepted)\b|我来(?:做|写|处理|接|负责)|我负责|我接(?:了|手)|由我", re.I)
HEDGE_RE  = re.compile(r"\b(can|could|may|might|consider|maybe|perhaps|if|unless|whoever|anyone|someone|should we|shall|if willing)\b|\?|也许|可能|要不|谁来|有人|如果", re.I)
DONE_RE   = re.compile(r"\b(done|finished|complete[d]?|submitted|ready for review|implemented|merged|pushed|deployed|shipped|landed|delivered|uploaded|is up|re-uploaded)\b|已(?:完成|提交|合并|推送|部署|落地|做完|上传)|做完了|完成了|搞定", re.I)
REVIEW_RE = re.compile(r"\b(lgtm|looks good|review(?:ed)? (?:and )?pass(?:ed|es)?|verified\b.{0,20}\b(?:it|this|v\d)|passes? (?:review|tests?)|ship it|accepted\b.{0,25}\b(?:as written|in full|all)|receipt)\b|审(?:核|查)通过|看过了没问题", re.I)
REVIEW_UNREAD_RE = re.compile(r"(?:have not|haven't|did not|didn't) (?:read|run|execute|open)\b.{0,40}\b(?:based on|from) (?:your|the) (?:description|summary|test list)", re.I)
ASK_RE    = re.compile(r"\b(can you|could you|would you|can someone|could someone|any (?:eta|update)|please (?:confirm|send|run|check|review|approve|share|upload|answer|reply|post|re-?upload|decide|ack)|\?\s*$)|@\w+|请你|麻烦你|你能|帮我|能不能|可以帮|你来", re.I | re.M)
PROXY_RE  = re.compile(r"\b(?:can|could|would) (?:you|someone) (?:run|check|test|look ?up|verify|execute|try|pull|fetch)\b.{0,60}?\b(?:for me|on your (?:machine|side|end)|since (?:you|only you))|帮我(?:跑|查|测|看)一下|你那边(?:跑|查|测)", re.I)
WAIT_RE   = re.compile(r"\b(blocked on|waiting (?:on|for)|still waiting|no response|haven't heard|silent for|any eta|bump|nudge|cutoff|deadline)\b|还在等|没回复|催一下", re.I)
HB_RE     = re.compile(r"\bno (?:new (?:messages|posts|branches|changes?)|change|runner changes)\b|still (?:waiting|blocked)|status[^.\n]{0,40}\bno change", re.I)
PAUSE_RE  = re.compile(r"\b(paus(?:e|ing|ed)|freeze|frozen|stop(?:ping)? (?:here|now)|no new work|standing by)\b|暂停|先停|冻结", re.I)
PAY_RE    = re.compile(r"\b(paid|transferred|sent)\b.{0,30}\b(credits?|tokens?)\b|\bpay\s+\S+.{0,20}\bcredits?\b|已(?:支付|转账|付款)", re.I)
UPLOAD_RE = re.compile(r"\b(uploaded|re-uploaded|attached|is up as|room-attached)\b|已上传|附件|上传了", re.I)
PUSH_RE   = re.compile(r"\b(pushed|commit [0-9a-f]{7}|tests? pass(?:es|ed)?|\d+/\d+ tests?)\b", re.I)
IDENT_RE  = re.compile(r"\b(who (?:is|are) (?:this|that|you|i_\w+)|which seat|same principal|two (?:agent )?seats|talk(?:ing)? over each other|messages crossed|say who (?:they|you) are|wrong seat|not my seat|posted from|更正署名|借了别人的身份|你是谁|两个席位)\b", re.I)
ROLE_RE   = re.compile(r"(?:i am|i'm|我是|本人是|acting as)\s*(?:the |this room's |your )?(supervisor|director|lead|coordinator|orchestrator|manager|owner|总监|负责人|协调人|主持|监督)", re.I)
AUTH_RE   = re.compile(r"用户授权我|user (?:has )?authori[sz]ed me|(?:owner|xisen|human) (?:asked|told|instructed) me to (?:supervise|lead|coordinate)", re.I)

def _norm(s): return re.sub(r"[^\w一-鿿]+", " ", s.lower()).strip()
def _shingles(s, k=4):
    w = _norm(s).split(); return {" ".join(w[i:i+k]) for i in range(max(0, len(w)-k+1))}
def items(text):
    out = set()
    for m in ITEM_RE.finditer(text):
        g = [x for x in m.groups() if x]
        tok = (" ".join(g) if g else m.group(0)).strip().lower()
        if len(tok) >= 2: out.add(tok)
    return out
def _bucket(seq): return "1-20" if seq <= 20 else "21-40" if seq <= 40 else "41-60" if seq <= 60 else "61+"

class RegexV1:
    """The reference annotator: calibrated transcript patterns. Strong on repetition and heartbeat cost; weak on silence (B1, D3, D4) and on facts the source cannot show (D1, D2)."""
    name = "regex_v1"
    version = "0.2.0"
    schema = "schema.json"
    taxonomy = "ten_modes"

    def modes_in(self, output: dict) -> list[str]:
        return [m["id"] for m in output["modes"] if m["present"]]

    def annotate(self, trace: Trace) -> dict:
        a = base_analysis(trace, self)
        # the goal and the runner's check reports are not communication between seats
        posts = [p for p in trace.posts if (p.get("type") or "message") == "message" and p.get("role") not in ("goal", "runner")]
        n = len(posts) or 1
        has_record = trace.has_record
        is_share = trace.source.get("kind") in ("share", "share-file")
        first_ts = parse_ts(posts[0]["created_at"]) if posts else None
        joined = {s.get("handle"): parse_ts(s.get("joined_at")) for s in trace.seats}
        uploaders = {ar.get("by") for ar in trace.artifacts}

        ev = defaultdict(list)
        log = defaultdict(lambda: {"first_mention": None, "claims": [], "done": [], "reviews": [], "uploads": []})
        acts = Counter(); pos_claims = Counter(); pos_re = Counter(); self_contra = 0
        asks = []; answered = set(); recent = []; dup = 0; hb = 0
        roles = defaultdict(set); action_claims = action_unverifiable = 0
        row = lambda p, why: {"seq": p["seq"], "who": p["who"], "excerpt": redact(p["text"]), "why": why}

        for p in posts:
            seq, who, c = p["seq"], p["who"], p["text"]
            if p.get("reply_to"): answered.add(p["reply_to"])
            for ref in SEQREF_RE.findall(c): answered.add(int(ref))
            its = items(c); hedged = bool(HEDGE_RE.search(c))
            late = bool(joined.get(who) and first_ts and joined[who] > first_ts)
            for it in its:
                if log[it]["first_mention"] is None: log[it]["first_mention"] = seq
            if HB_RE.search(c[:220]): hb += 1
            if ACCEPT_RE.search(c) and its:
                acts["claim_posts"] += 1
                for it in its:
                    acts["claims"] += 1; pos_claims[_bucket(seq)] += 1
                    prior = [x for x in log[it]["done"] if x["seq"] < seq]
                    log[it]["claims"].append({"seq": seq, "who": who, "kind": "hedged" if hedged else "firm"})
                    if prior:
                        pos_re[_bucket(seq)] += 1
                        other = [x for x in prior if x["who"] != who]
                        if other:
                            t = parse_ts(p["created_at"]); fresh = late and joined.get(who) and t and (t - joined[who]).total_seconds() < 6 * 3600
                            ev["R2" if fresh else "R1"].append(row(p, f"claims '{it}', reported done by {other[-1]['who']} at #{other[-1]['seq']}" + (" (first hours after joining)" if fresh else "")))
                        else:
                            self_contra += 1; ev["R1"].append(row(p, f"re-claims '{it}' that it reported done itself at #{prior[-1]['seq']}"))
            if DONE_RE.search(c) and its:
                acts["done"] += 1
                for it in its: log[it]["done"].append({"seq": seq, "who": who})
            if UPLOAD_RE.search(c) or PAY_RE.search(c) or PUSH_RE.search(c):
                action_claims += 1
                for it in its: log[it]["uploads"].append({"seq": seq, "who": who})
                verifiable = has_record and (UPLOAD_RE.search(c) is None or who in uploaders)
                if not verifiable:
                    action_unverifiable += 1
                    if has_record: ev["D1"].append(row(p, "action claimed with no matching artifact row by this seat"))
                    elif len(ev["D1"]) < 10: ev["D1"].append(row(p, f"action claimed (upload / push / tests); {'a share' if is_share else 'this source'} has no artifact or transfer rows to check it against"))
            if REVIEW_RE.search(c):
                acts["reviews"] += 1
                for it in its: log[it]["reviews"].append({"seq": seq, "who": who})
                if REVIEW_UNREAD_RE.search(c): ev["D2"].append(row(p, "review given on a description, not the artifact"))
                elif its and not any(log[it]["done"] or log[it]["uploads"] for it in its): ev["D2"].append(row(p, "review language with no visible prior delivery of the item(s) named"))
            if ASK_RE.search(c):
                acts["asks"] += 1; asks.append(p)
                if PROXY_RE.search(c): ev["D4"].append(row(p, "asks the holder to act instead of taking the item over"))
            if WAIT_RE.search(c): acts["wait_signals"] += 1
            if IDENT_RE.search(c): ev["B2"].append(row(p, "identity or seat ambiguity being negotiated on the board"))
            r = ROLE_RE.search(c)
            if r: roles[r.group(1).lower()].add(who)
            if AUTH_RE.search(c): roles["authorized"].add(who)
            sh = _shingles(c)
            if len(sh) >= 8:
                for pseq, pwho, psh in recent[-80:]:
                    if len(sh & psh) / max(1, len(sh | psh)) >= 0.6:
                        dup += 1
                        if len(ev["REP"]) < 40: ev["REP"].append(row(p, f"near-duplicate of #{pseq} by {pwho}"))
                        break
                recent.append((seq, who, sh))

        for role, ss in roles.items():
            if len(ss) >= 2: ev["B2"].append({"seq": 0, "who": ", ".join(sorted(ss)), "excerpt": "", "why": f"two or more seats claim the role '{role}'"})
        last_seq = posts[-1]["seq"] if posts else 0
        unanswered = [p for p in asks if p["seq"] not in answered and p["seq"] < last_seq - 2]
        for p in unanswered[:40]: ev["B1"].append(row(p, "no later post replies to or cites this ask"))
        for it, lg in log.items():
            if lg["claims"] and all(x["kind"] == "hedged" for x in lg["claims"]) and not lg["done"]:
                ev["B1"].append({"seq": lg["claims"][0]["seq"], "who": lg["claims"][0]["who"], "excerpt": f"hedged claim on '{it}'", "why": "never firmed up or delivered"})

        items_out = {}
        for it, lg in log.items():
            if not (lg["claims"] or lg["done"] or lg["reviews"]): continue
            status = "reviewed" if lg["reviews"] and lg["done"] else "done" if lg["done"] else "claimed" if any(x["kind"] == "firm" for x in lg["claims"]) else "mentioned"
            items_out[it] = {**lg, "status_at_end": status}
        open_items = [it for it, v in items_out.items() if v["status_at_end"] == "claimed"]
        last = posts[-1]["text"] if posts else ""
        last_kind = "pause" if PAUSE_RE.search(last) else "ask" if ASK_RE.search(last) else "heartbeat" if HB_RE.search(last) else "done" if DONE_RE.search(last) else "other"
        if open_items or last_kind in ("ask", "heartbeat", "pause") or acts["wait_signals"] >= max(3, n // 20):
            ev["D3"].append({"seq": last_seq, "who": "", "excerpt": redact(last), "why": f"ends with a {last_kind}; {len(open_items)} claimed item(s) never reported done; {acts['wait_signals']} waiting/blocked signals"})

        span = None
        if len(posts) > 1 and first_ts and parse_ts(posts[-1]["created_at"]):
            span = round((parse_ts(posts[-1]["created_at"]) - first_ts).total_seconds() / 3600, 1)
        a["metrics"].update({
            "posts": len(posts), "seats": len(trace.seats), "principals": len({s.get("principal") for s in trace.seats if s.get("principal")}) or None, "span_hours": span,
            "asks": acts["asks"], "asks_unanswered": len(unanswered), "wait_signals": acts["wait_signals"],
            "claims": acts["claims"], "claim_posts": acts["claim_posts"], "re_claims": sum(pos_re.values()), "self_contradicting_re_claims": self_contra,
            "re_claims_by_position": {b: {"re_claims": pos_re[b], "claims": pos_claims[b]} for b in ["1-20", "21-40", "41-60", "61+"]},
            "done_claims": acts["done"], "reviews": acts["reviews"], "action_claims": action_claims, "action_claims_unverifiable": action_unverifiable,
            "duplicate_posts": dup, "heartbeat_posts": hb, "heartbeat_share": round(hb / n, 3),
            "open_items_at_end": len(open_items), "last_post_kind": last_kind,
        })
        a["items"] = items_out
        conf = {"R1": 0.4, "R2": 0.35, "B1": 0.55, "B2": 0.5, "D1": 0.7 if has_record else 0.3, "D2": 0.3, "D3": 0.6, "D4": 0.4, "REP": 0.85, "HB": 0.9}
        sev = {
            "R1": severity_for(len(ev["R1"]) / max(1, acts["claims"]), 0.4, 0.2, 0.05),
            "R2": severity_for(len(ev["R2"]) / max(1, acts["claims"]), 0.4, 0.2, 0.05),
            "B1": severity_for(len(unanswered) / max(1, acts["asks"]), 0.5, 0.25, 0.08),
            "B2": severity_for(len(ev["B2"]) / n, 0.05, 0.02, 0.004),
            "D1": severity_for(action_unverifiable / max(1, action_claims), 0.9, 0.5, 0.1) if has_record else "unknown",
            "D2": severity_for(len(ev["D2"]) / max(1, acts["reviews"]), 0.5, 0.25, 0.08),
            "D3": "high" if (hb / n >= 0.15 or last_kind in ("pause", "ask")) and (open_items or acts["wait_signals"] >= 3) else "medium" if ev.get("D3") else "none",
            "D4": severity_for(len(ev["D4"]) / max(1, acts["asks"]), 0.3, 0.1, 0.02),
            "REP": severity_for(dup / n, 0.15, 0.07, 0.02),
            "HB": severity_for(hb / n, 0.15, 0.07, 0.02),
        }
        for mid in sev:
            set_mode(a, mid, evidence=ev.get(mid, []), severity=sev[mid], confidence=conf[mid], count=hb if mid == "HB" else len(ev.get(mid, [])))
        a["caveats"] = ["transcript-only detection; every evidence row is a pointer to read, not a label"]
        if is_share:
            a["caveats"].append("share projection: ids, artifacts and transfers stripped, so D1 cannot be verified and D2 cannot see uploads")
        elif not has_record:
            a["caveats"].append("no artifact rows in this source, so D1 cannot be verified against uploads")
        if not trace.has_ops:
            a["caveats"].append("no per-seat execution trace: 'acted' facts of Table 1 are unavailable")
        return a

    def markdown(self, a: dict) -> str:
        m = a["metrics"]
        out = [f"# {a['room'].get('name')}: {m['posts']} posts, {m['seats']} seats" + (f", {m['span_hours']} h" if m.get("span_hours") else ""),
               "", "| mode | severity | count | confidence | removed by |", "|---|---|---:|---:|---|"]
        order = ["high", "medium", "low", "unknown", "none"]
        for x in sorted(a["modes"], key=lambda x: order.index(x["severity"])):
            out.append(f"| {x['id']} {x['name']} | {x['severity']} | {x['count']} | {x['confidence']} | {x['removed_by']} |")
        out += ["", f"heartbeat share {m['heartbeat_share']:.0%}, asks unanswered {m['asks_unanswered']}/{m['asks']}, "
                    f"re-claims {m['re_claims']}/{m['claims']}, open items at end {m['open_items_at_end']}, last post: {m['last_post_kind']}"]
        return "\n".join(out)

ANNOTATOR = RegexV1
