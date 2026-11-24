"""
Independent mini DAX evaluator.

Evaluates the DAX measures that are defined in the blueprint (i.e. compiled from the user's
Requirement.md) directly against the Parquet warehouse with pandas/numpy, so the "KPI audit"
reflects exactly what the Requirement asks for and can be compared with Power BI's numbers.

Supported: COUNTROWS, SUM, AVERAGE, MIN, MAX, MEDIAN, DISTINCTCOUNT, PERCENTILE.INC,
SUMX/AVERAGEX/MINX/MAXX (over a table or FILTER(table, cond), and MINX/MAXX over {a, b, c}),
DIVIDE, CALCULATE (filters of the form 'T'[col] <op> literal, joined with &&), FILTER,
IF, ISBLANK, NOT, BLANK, ABS, ROUND, COALESCE, + - * / comparisons, && ||, [Measure] references.
Anything else is reported as UNSUPPORTED (never silently wrong).
"""
import operator
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


class Unsupported(Exception):
    pass


_TOKEN_RE = re.compile(
    r"""(?:
        (?P<str>"(?:[^"]|"")*")
      | (?P<col>(?:'[^']+'|[A-Za-z_][A-Za-z0-9_]*)\[[^\]]+\])
      | (?P<qid>'[^']+')
      | (?P<meas>\[[^\]]+\])
      | (?P<num>\d+(?:\.\d+)?)
      | (?P<id>[A-Za-z_][A-Za-z0-9_\.]*)
      | (?P<op><>|<=|>=|&&|\|\||[=<>+\-*/(),{}])
    )""",
    re.X,
)
_COL_RE = re.compile(r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
_CMP = {"=", "<>", "<", ">", "<=", ">="}
_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "=": "=", "<>": "<>"}
_PYOP = {"=": operator.eq, "<>": operator.ne, "<": operator.lt, ">": operator.gt, "<=": operator.le, ">=": operator.ge}


def tokenize(s: str) -> List[Tuple[str, str]]:
    toks: List[Tuple[str, str]] = []
    pos, n = 0, len(s)
    while pos < n:
        if s[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(s, pos)
        if not m:
            raise Unsupported(f"cannot tokenize near '{s[pos:pos + 18]}'")
        kind = m.lastgroup
        toks.append((kind, m.group(kind)))
        pos = m.end()
    return toks


class Parser:
    def __init__(self, toks: List[Tuple[str, str]]):
        self.t = toks
        self.i = 0

    def peek(self) -> Tuple[Optional[str], Optional[str]]:
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def next(self) -> Tuple[Optional[str], Optional[str]]:
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, op: str) -> None:
        if self.next() != ("op", op):
            raise Unsupported(f"parse error: expected '{op}'")

    def parse(self):
        node = self.or_()
        if self.i < len(self.t):
            raise Unsupported("parse error: unexpected trailing tokens")
        return node

    def or_(self):
        n = self.and_()
        while self.peek() == ("op", "||"):
            self.next()
            n = ("bin", "||", n, self.and_())
        return n

    def and_(self):
        n = self.cmp_()
        while self.peek() == ("op", "&&"):
            self.next()
            n = ("bin", "&&", n, self.cmp_())
        return n

    def cmp_(self):
        n = self.add()
        k, v = self.peek()
        if k == "op" and v in _CMP:
            self.next()
            n = ("bin", v, n, self.add())
        return n

    def add(self):
        n = self.mul()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            n = ("bin", op, n, self.mul())
        return n

    def mul(self):
        n = self.unary()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/"):
            op = self.next()[1]
            n = ("bin", op, n, self.unary())
        return n

    def unary(self):
        if self.peek() == ("op", "-"):
            self.next()
            return ("neg", self.unary())
        return self.primary()

    def primary(self):
        kind, val = self.next()
        if kind == "num":
            return ("num", float(val))
        if kind == "str":
            return ("str", val[1:-1].replace('""', '"'))
        if kind == "col":
            m = _COL_RE.match(val)
            return ("col", m.group(1) or m.group(2), m.group(3))
        if kind == "qid":
            return ("ident", val.strip("'"))
        if kind == "meas":
            return ("meas", val[1:-1])
        if kind == "id":
            if self.peek() == ("op", "("):
                self.next()
                args = []
                if self.peek() == ("op", ")"):
                    self.next()
                else:
                    while True:
                        args.append(self.or_())
                        k, v = self.next()
                        if (k, v) == ("op", ")"):
                            break
                        if (k, v) != ("op", ","):
                            raise Unsupported("parse error in argument list")
                return ("fn", val.upper(), args)
            return ("ident", val)
        if (kind, val) == ("op", "("):
            n = self.or_()
            self.expect(")")
            return n
        if (kind, val) == ("op", "{"):
            items = []
            while True:
                items.append(self.or_())
                k, v = self.next()
                if (k, v) == ("op", "}"):
                    break
                if (k, v) != ("op", ","):
                    raise Unsupported("parse error in table constructor")
            return ("set", items)
        raise Unsupported("parse error: unexpected token")


def _to_py(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if np.isnan(f) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


class Evaluator:
    def __init__(self, tables: Dict[str, pd.DataFrame], nrows: Dict[str, int], measures: Dict[str, str]):
        self.tables = tables
        self.nrows = nrows
        self.measures = dict(measures)
        self._lower = {k.lower(): k for k in measures}
        self._ast: Dict[str, Any] = {}
        self._mcache: Dict[Tuple[str, tuple], Any] = {}
        self._mask_cache: Dict[tuple, np.ndarray] = {}
        self._stack: List[str] = []

    # ---- parsing / measure lookup -------------------------------------------------
    def ast(self, expr: str):
        if expr not in self._ast:
            self._ast[expr] = Parser(tokenize(expr)).parse()
        return self._ast[expr]

    def measure(self, name: str, filters: tuple) -> Any:
        key = (name.lower(), filters)
        if key in self._mcache:
            return self._mcache[key]
        real = self._lower.get(name.lower())
        if real is None:
            raise Unsupported(f"unknown measure [{name}]")
        if name.lower() in self._stack:
            raise Unsupported("cyclic measure reference")
        self._stack.append(name.lower())
        try:
            val = self.ev(self.ast(self.measures[real]), filters)
        finally:
            self._stack.pop()
        self._mcache[key] = val
        return val

    # ---- data access --------------------------------------------------------------
    def _arr(self, t: str, c: str) -> np.ndarray:
        df = self.tables.get(t)
        if df is None or c not in df.columns:
            raise Unsupported(f"column {t}[{c}] not found in warehouse")
        return df[c].to_numpy()

    def _nrows(self, t: str) -> int:
        if t not in self.nrows:
            raise Unsupported(f"table {t} not found in warehouse")
        return self.nrows[t]

    @staticmethod
    def _cmp(a: Any, b: Any, op: str):
        if isinstance(a, np.ndarray):
            a = pd.Series(a)
        if isinstance(b, np.ndarray):
            b = pd.Series(b)
        res = _PYOP[op](a, b)
        return res.to_numpy() if isinstance(res, pd.Series) else res

    def _mask(self, t: str, filters: tuple) -> Optional[np.ndarray]:
        fl = tuple(f for f in filters if f[0] == t)
        if not fl:
            return None
        if fl in self._mask_cache:
            return self._mask_cache[fl]
        _, c, op, v = fl[-1]
        m = np.asarray(self._cmp(self._arr(t, c), v, op), dtype=bool)
        parent = self._mask(t, fl[:-1])
        out = m if parent is None else (parent & m)
        self._mask_cache[fl] = out
        return out

    def _series(self, t: str, c: str, filters: tuple) -> pd.Series:
        a = self._arr(t, c)
        m = self._mask(t, filters)
        return pd.Series(a if m is None else a[m]).dropna()

    # ---- table / row expressions --------------------------------------------------
    def table_expr(self, node, filters: tuple):
        if node[0] in ("ident", "str"):
            return node[1], self._mask(node[1], filters)
        if node[0] == "fn" and node[1] == "FILTER":
            t, m = self.table_expr(node[2][0], filters)
            cond = np.asarray(self.row(node[2][1], t), dtype=bool)
            return t, (cond if m is None else (m & cond))
        raise Unsupported("table expression")

    def row(self, node, t: str):
        k = node[0]
        if k == "col":
            if node[1] != t:
                raise Unsupported("cross-table row expression")
            return self._arr(t, node[2])
        if k in ("num", "str"):
            return node[1]
        if k == "neg":
            return -self.row(node[1], t)
        if k == "bin":
            op = node[1]
            a, b = self.row(node[2], t), self.row(node[3], t)
            if op in _CMP:
                return self._cmp(a, b, op)
            if op == "&&":
                return np.logical_and(a, b)
            if op == "||":
                return np.logical_or(a, b)
            with np.errstate(all="ignore"):
                if op == "+":
                    return a + b
                if op == "-":
                    return a - b
                if op == "*":
                    return a * b
                if op == "/":
                    return np.true_divide(a, b)
        if k == "fn" and node[1] == "ISBLANK":
            return pd.isna(self.row(node[2][0], t))
        if k == "fn" and node[1] == "NOT":
            return np.logical_not(self.row(node[2][0], t))
        raise Unsupported("row-context expression")

    # ---- scalar evaluation --------------------------------------------------------
    def ev(self, node, filters: tuple) -> Any:
        k = node[0]
        if k in ("num", "str"):
            return node[1]
        if k == "meas":
            return self.measure(node[1], filters)
        if k == "neg":
            v = self.ev(node[1], filters)
            return None if v is None else -v
        if k == "fn":
            return self.fn(node[1], node[2], filters)
        if k == "bin":
            op = node[1]
            if op == "&&":
                return bool(self.ev(node[2], filters)) and bool(self.ev(node[3], filters))
            if op == "||":
                return bool(self.ev(node[2], filters)) or bool(self.ev(node[3], filters))
            a, b = self.ev(node[2], filters), self.ev(node[3], filters)
            if op in _CMP:
                if a is None:
                    a = "" if isinstance(b, str) else 0
                if b is None:
                    b = "" if isinstance(a, str) else 0
                return bool(_PYOP[op](a, b))
            if a is None and b is None:
                return None
            a, b = a or 0, b or 0
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return None if b == 0 else a / b
        raise Unsupported("expression form")

    def filter_specs(self, node) -> List[Tuple[str, str, str, Any]]:
        if node[0] == "bin" and node[1] == "&&":
            return self.filter_specs(node[2]) + self.filter_specs(node[3])
        if node[0] == "bin" and node[1] in _CMP:
            left, right = node[2], node[3]
            lit = ("num", "str", "neg")
            if left[0] == "col" and right[0] in lit:
                return [(left[1], left[2], node[1], self.ev(right, ()))]
            if right[0] == "col" and left[0] in lit:
                return [(right[1], right[2], _FLIP[node[1]], self.ev(left, ()))]
        raise Unsupported("CALCULATE filter form")

    def fn(self, name: str, args: list, filters: tuple) -> Any:
        n = name
        if n == "COUNTROWS":
            t, m = self.table_expr(args[0], filters)
            total = self._nrows(t)
            return int(total if m is None else m.sum())
        if n in ("SUM", "AVERAGE", "MIN", "MAX", "MEDIAN", "DISTINCTCOUNT"):
            if args[0][0] != "col":
                raise Unsupported(f"{n} over an expression")
            s = self._series(args[0][1], args[0][2], filters)
            if n == "DISTINCTCOUNT":
                return int(s.nunique())
            if len(s) == 0:
                return None
            return _to_py({"SUM": s.sum, "AVERAGE": s.mean, "MIN": s.min, "MAX": s.max, "MEDIAN": s.median}[n]())
        if n == "PERCENTILE.INC":
            if args[0][0] != "col":
                raise Unsupported("PERCENTILE.INC over an expression")
            s = self._series(args[0][1], args[0][2], filters)
            if len(s) == 0:
                return None
            p = float(self.ev(args[1], filters))
            return float(np.percentile(s.to_numpy(dtype=float), p * 100.0))
        if n in ("SUMX", "AVERAGEX", "MINX", "MAXX"):
            first = args[0]
            if first[0] == "set" and n in ("MINX", "MAXX"):
                vals = [v for v in (self.ev(i, filters) for i in first[1]) if v is not None]
                if not vals:
                    return None
                return max(vals) if n == "MAXX" else min(vals)
            t, m = self.table_expr(first, filters)
            arr = np.asarray(self.row(args[1], t), dtype=float)
            if arr.ndim == 0:
                arr = np.full(self._nrows(t), float(arr))
            if m is not None:
                arr = arr[m]
            arr = arr[~np.isnan(arr)]
            if arr.size == 0:
                return None
            return float({"SUMX": np.sum, "AVERAGEX": np.mean, "MINX": np.min, "MAXX": np.max}[n](arr))
        if n == "DIVIDE":
            a, b = self.ev(args[0], filters), self.ev(args[1], filters)
            alt = self.ev(args[2], filters) if len(args) > 2 else None
            if a is None or b is None or b == 0:
                return alt
            return a / b
        if n == "CALCULATE":
            new = list(filters)
            for fnode in args[1:]:
                for spec in self.filter_specs(fnode):
                    new = [f for f in new if not (f[0] == spec[0] and f[1] == spec[1])]
                    new.append(spec)
            return self.ev(args[0], tuple(new))
        if n == "IF":
            if self.ev(args[0], filters):
                return self.ev(args[1], filters)
            return self.ev(args[2], filters) if len(args) > 2 else None
        if n == "ISBLANK":
            return self.ev(args[0], filters) is None
        if n == "NOT":
            return not self.ev(args[0], filters)
        if n == "BLANK":
            return None
        if n == "ABS":
            v = self.ev(args[0], filters)
            return None if v is None else abs(v)
        if n == "ROUND":
            v = self.ev(args[0], filters)
            return None if v is None else round(v, int(self.ev(args[1], filters)))
        if n == "COALESCE":
            for a in args:
                v = self.ev(a, filters)
                if v is not None:
                    return v
            return None
        raise Unsupported(f"function {n}")


def format_value(value: Any, fmt: Optional[str]) -> str:
    """Render a value roughly the way Power BI would for the measure's formatString."""
    if value is None:
        return "(Blank)"
    if isinstance(value, (str, bool)):
        return str(value)
    fmt = (fmt or "").split(";")[0]
    sign = "+" if fmt.startswith("+") else ""
    fmt = fmt.lstrip("+")
    try:
        if "%" in fmt:
            dec = len(fmt.split(".")[1].replace("%", "")) if "." in fmt else 0
            return f"{value * 100:{sign},.{dec}f}%"
        dec = len(fmt.split(".")[1]) if "." in fmt else 0
        return f"{value:{sign},.{dec}f}"
    except Exception:
        return str(value)


def _collect_refs(measures: Dict[str, str]) -> Tuple[Dict[str, Set[str]], Set[str]]:
    cols: Dict[str, Set[str]] = {}
    tables: Set[str] = set()
    for expr in measures.values():
        try:
            toks = tokenize(expr)
        except Unsupported:
            continue
        for idx, (kind, val) in enumerate(toks):
            if kind == "col":
                m = _COL_RE.match(val)
                cols.setdefault(m.group(1) or m.group(2), set()).add(m.group(3))
            elif kind == "qid":
                tables.add(val.strip("'"))
            elif kind == "id":
                nxt = toks[idx + 1] if idx + 1 < len(toks) else (None, None)
                if nxt != ("op", "("):
                    tables.add(val)
    return cols, tables


def evaluate_blueprint_measures(workspace_dir: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate every DAX measure of the blueprint on the Parquet warehouse (whole dataset, no slicers)."""
    root = Path(workspace_dir)
    wh = root / blueprint.get("project", {}).get("warehouse_dir", "data_warehouse")
    measure_defs = blueprint.get("dax_measures", [])
    exprs = {m["name"]: m["expression"] for m in measure_defs}
    cols, table_names = _collect_refs(exprs)

    tables: Dict[str, pd.DataFrame] = {}
    nrows: Dict[str, int] = {}
    for t in set(cols) | table_names:
        path = wh / f"{t}.parquet"
        if not path.exists():
            continue
        pf = pq.ParquetFile(str(path))
        n = pf.metadata.num_rows
        present = [c for c in cols.get(t, set()) if c in pf.schema_arrow.names]
        tables[t] = pq.read_table(str(path), columns=present).to_pandas() if present else pd.DataFrame(index=pd.RangeIndex(n))
        nrows[t] = n

    ev = Evaluator(tables, nrows, exprs)
    results: List[Dict[str, Any]] = []
    for m in measure_defs:
        try:
            v = _to_py(ev.measure(m["name"], ()))
            status = "OK" if v is not None else "BLANK"
        except Unsupported as e:
            v, status = None, f"UNSUPPORTED: {e}"
        except Exception as e:  # noqa: BLE001 - report, never crash the pipeline
            v, status = None, f"ERROR: {e}"
        results.append({
            "name": m["name"],
            "folder": m.get("folder", ""),
            "expression": m["expression"],
            "description": m.get("description", ""),
            "formatString": m.get("formatString", ""),
            "value": v,
            "display": format_value(v, m.get("formatString")),
            "status": status,
        })

    req_doc = blueprint.get("project", {}).get("requirement_doc", "")
    req_path = Path(req_doc) if req_doc and Path(req_doc).is_absolute() else (root / req_doc if req_doc else None)
    meta = {
        "requirement_doc": req_doc,
        "requirement_modified": datetime.fromtimestamp(req_path.stat().st_mtime).isoformat(timespec="seconds") if req_path and req_path.exists() else None,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "OK"),
        "blank": sum(1 for r in results if r["status"] == "BLANK"),
        "unsupported": sum(1 for r in results if r["status"].startswith("UNSUPPORTED")),
        "error": sum(1 for r in results if r["status"].startswith("ERROR")),
    }
    return {"measures": results, "meta": meta}
