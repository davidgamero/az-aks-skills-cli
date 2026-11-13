"""Verify recorded citations without executing submitted shell or formatter code."""

import json
import re
import shlex


def normalized(text):
    # Formatting-only differences in JSON indentation and line wrapping are immaterial.
    return re.sub(r"\s+", "", text)


def projections(event):
    raw=event["stdout"]+event.get("stderr","")
    output=[raw]
    try: data=json.loads(event["stdout"])
    except ValueError: return output
    if not isinstance(data,dict) or not isinstance(data.get("value"),list): return output
    rows=data["value"]
    if not all(isinstance(m,dict) and isinstance(m.get("name"),dict) and "timeseries" in m for m in rows): return output
    # Two bounded, lossless metrics displays. Do not execute arbitrary Python/jq pipelines.
    output.append("\n".join(json.dumps({"metric":m["name"]["value"],"series":m["timeseries"]},separators=(",",":")) for m in rows))
    output.append("\n".join(" ".join([m["name"]["value"],",".join(v["name"]["value"]+"="+v["value"] for v in series.get("metadatavalues",[])),
        point["timeStamp"],"maximum="+str(point.get("maximum")),"total="+str(point.get("total"))]) for m in rows for series in m["timeseries"] for point in series["data"]))
    return output


def verify(citation, observations):
    if not isinstance(citation,dict) or not isinstance(citation.get("command"),str) or not isinstance(citation.get("quote"),str): return False,set(),False
    quote=citation["quote"]
    if len(quote)<12: return False,set(),False
    try:
        lexer=shlex.shlex(citation["command"],posix=True,punctuation_chars=";&|");lexer.whitespace_split=True;lexer.commenters=""
        tokens=list(lexer)
    except ValueError: return False,set(),False
    if not tokens: return False,set(),False
    if tokens[0] not in ("az","kubectl","curl"): return True,set(),True
    segments=[];part=[];pipeline=False
    for token in tokens+["&&"]:
        if token in ("&&",";"):
            if part: segments.append(part)
            part=[];pipeline=False
        elif token=="|": pipeline=True
        elif not pipeline: part.append(token)
    matched=[];cursor=0
    for command in segments:
        found=next(((i,e) for i,e in enumerate(observations[cursor:],cursor) if command==[e["tool"],*e["argv"]]),None)
        if found is None: return False,set(),False
        cursor=found[0]+1;matched.append(found[1])
    nquote=normalized(quote)
    authentic=any(nquote in normalized(p) for e in matched for p in projections(e)) or nquote in normalized("".join(e["stdout"]+e.get("stderr","") for e in matched))
    if not authentic: return False,set(),False
    cited=set()
    metric_names={"snat_usage":"UsedSnatPorts","snat_allocation":"AllocatedSnatPorts","snat_failures":"SnatConnectionCount"}
    for event in matched:
        for tag,signals in event.get("signals",{}).items():
            if tag in metric_names and metric_names[tag] not in quote: continue
            if any(normalized(signal) in nquote for signal in signals): cited.add(tag)
    return True,cited,False
