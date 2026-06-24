from datetime import datetime
from flask import Flask, render_template, request, jsonify
import re
import base64
try:
    import graphviz
    HAS_GRAPHVIZ = True
except Exception:
    graphviz = None
    HAS_GRAPHVIZ = False

app = Flask(__name__)

TOKEN_PATTERNS = [
    ("ORDER_KEY", r"ORDEN"),
    ("DATE_KEY", r"FECHA"),
    ("CLIENT_KEY", r"CLIENTE"),
    ("ITEM_KEY", r"ITEM"),
    ("DESC_KEY", r"DESCRIPCION"),
    ("QTY_KEY", r"CANTIDAD"),
    ("PRICE_KEY", r"PRECIO"),
    ("TOTAL_KEY", r"TOTAL"),
    ("COLON", r":"),
    ("PIPE", r"\|"),
    ("DATE", r"\d{2}/\d{2}/\d{4}"),
    ("NUMBER", r"\d+(?:\.\d+)?"),
    ("CODE", r"[A-Z]{1,4}-\d{1,6}"),
    ("TEXT", r"[^:\|\n]+"),
]
TOKEN_REGEX = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_PATTERNS),
    re.IGNORECASE,
)
TOKEN_DEFINITIONS = [{"type": name, "pattern": pattern} for name, pattern in TOKEN_PATTERNS]

PRINTABLE_CHARS = frozenset(chr(i) for i in range(32, 127) if chr(i) != "\n")
DIGIT_SET = frozenset("0123456789")
UPPER_ALPHA_SET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
TEXT_CHAR_SET = frozenset(c for c in PRINTABLE_CHARS if c not in {":", "|", "\n"})

class RegexParser:
    def __init__(self, pattern):
        self.pattern = pattern
        self.pos = 0

    def parse(self):
        node = self.parse_alternation()
        if self.pos != len(self.pattern):
            raise ValueError(f"Caracter inesperado en regex: {self.pattern[self.pos:]}")
        return node

    def peek(self):
        return self.pattern[self.pos] if self.pos < len(self.pattern) else None

    def consume(self):
        char = self.peek()
        self.pos += 1
        return char

    def parse_alternation(self):
        left = self.parse_concatenation()
        while self.peek() == "|":
            self.consume()
            right = self.parse_concatenation()
            left = {"type": "alt", "left": left, "right": right}
        return left

    def parse_concatenation(self):
        nodes = []
        while True:
            char = self.peek()
            if char is None or char == ")" or char == "|":
                break
            nodes.append(self.parse_repetition())
        if not nodes:
            return {"type": "epsilon"}
        if len(nodes) == 1:
            return nodes[0]
        return {"type": "concat", "children": nodes}

    def parse_repetition(self):
        node = self.parse_atom()
        while True:
            char = self.peek()
            if char == "*":
                self.consume()
                node = {"type": "star", "expr": node}
            elif char == "+":
                self.consume()
                node = {"type": "plus", "expr": node}
            elif char == "?":
                self.consume()
                node = {"type": "optional", "expr": node}
            elif char == "{":
                node = self.parse_quantifier(node)
            else:
                break
        return node

    def parse_quantifier(self, node):
        self.consume()
        digits = ""
        while self.peek() and self.peek().isdigit():
            digits += self.consume()
        if not digits:
            raise ValueError("Se esperaba un número en el cuantificador")
        min_count = int(digits)
        max_count = min_count
        if self.peek() == ",":
            self.consume()
            digits = ""
            while self.peek() and self.peek().isdigit():
                digits += self.consume()
            max_count = int(digits) if digits else None
        if self.peek() != "}":
            raise ValueError("Falta '}' en el cuantificador")
        self.consume()
        return {"type": "repeat", "expr": node, "min": min_count, "max": max_count}

    def parse_atom(self):
        char = self.peek()
        if char == "(":
            self.consume()
            if self.peek() == "?":
                self.consume()
                if self.consume() != ":":
                    raise ValueError("Se esperaba '?:' en el grupo")
            node = self.parse_alternation()
            if self.consume() != ")":
                raise ValueError("Se esperaba ')' en el grupo")
            return node
        if char == "[":
            return self.parse_char_class()
        if char == "\\":
            self.consume()
            escaped = self.parse_escape(self.consume())
            if isinstance(escaped, dict):
                return escaped
            return {"type": "literal", "value": escaped}
        return {"type": "literal", "value": self.consume()}

    def parse_char_class(self):
        self.consume()
        negate = False
        if self.peek() == "^":
            negate = True
            self.consume()
        char_set = set()
        while self.peek() and self.peek() != "]":
            start = self.consume()
            if start == "\\":
                start = self.parse_escape(self.consume())
            if self.peek() == "-" and self.pattern[self.pos + 1] != "]":
                self.consume()
                end = self.consume()
                if end == "\\":
                    end = self.parse_escape(self.consume())
                for code in range(ord(start), ord(end) + 1):
                    char_set.add(chr(code))
            else:
                char_set.add(start)
        if self.consume() != "]":
            raise ValueError("Falta ']' en la clase de caracteres")
        if negate:
            return {"type": "set", "chars": frozenset(PRINTABLE_CHARS - char_set)}
        return {"type": "set", "chars": frozenset(char_set)}

    def parse_escape(self, char):
        if char == "d":
            return {"type": "set", "chars": DIGIT_SET}
        if char == "n":
            return "\n"
        return char


class NFABuilder:
    def __init__(self):
        self.next_id = 0

    def new_state(self):
        state_id = self.next_id
        self.next_id += 1
        return state_id

    def build(self, node):
        kind = node["type"]
        if kind == "epsilon":
            start = self.new_state()
            return {"start": start, "accept": start, "transitions": []}
        if kind == "literal":
            start = self.new_state()
            accept = self.new_state()
            symbol = frozenset({node["value"]})
            return {"start": start, "accept": accept, "transitions": [{"from": start, "symbol": symbol, "to": accept}]}
        if kind == "set":
            start = self.new_state()
            accept = self.new_state()
            return {"start": start, "accept": accept, "transitions": [{"from": start, "symbol": node["chars"], "to": accept}]}
        if kind == "concat":
            pieces = [self.build(child) for child in node["children"]]
            return self.concatenate_fragments(pieces)
        if kind == "alt":
            left = self.build(node["left"])
            right = self.build(node["right"])
            return self.alternate_fragments(left, right)
        if kind == "star":
            fragment = self.build(node["expr"])
            return self.kleene_star(fragment)
        if kind == "plus":
            fragment = self.build(node["expr"])
            return self.concatenate_fragments([fragment, self.kleene_star(fragment)])
        if kind == "optional":
            fragment = self.build(node["expr"])
            return self.alternate_fragments(fragment, self.build({"type": "epsilon"}))
        if kind == "repeat":
            return self.build_repeat(node["expr"], node["min"], node["max"])
        raise ValueError(f"Nodo regex desconocido: {kind}")

    def concatenate_fragments(self, fragments):
        if not fragments:
            return self.build({"type": "epsilon"})
        result = fragments[0]
        for fragment in fragments[1:]:
            connection = {"from": result["accept"], "symbol": None, "to": fragment["start"]}
            result = {
                "start": result["start"],
                "accept": fragment["accept"],
                "transitions": result["transitions"] + [connection] + fragment["transitions"],
            }
        return result

    def alternate_fragments(self, left, right):
        start = self.new_state()
        accept = self.new_state()
        transitions = [
            {"from": start, "symbol": None, "to": left["start"]},
            {"from": start, "symbol": None, "to": right["start"]},
            {"from": left["accept"], "symbol": None, "to": accept},
            {"from": right["accept"], "symbol": None, "to": accept},
        ]
        transitions.extend(left["transitions"])
        transitions.extend(right["transitions"])
        return {"start": start, "accept": accept, "transitions": transitions}

    def kleene_star(self, fragment):
        start = self.new_state()
        accept = self.new_state()
        transitions = [
            {"from": start, "symbol": None, "to": fragment["start"]},
            {"from": start, "symbol": None, "to": accept},
            {"from": fragment["accept"], "symbol": None, "to": fragment["start"]},
            {"from": fragment["accept"], "symbol": None, "to": accept},
        ]
        transitions.extend(fragment["transitions"])
        return {"start": start, "accept": accept, "transitions": transitions}

    def build_repeat(self, expr, min_count, max_count):
        if min_count == 0 and max_count is None:
            return self.kleene_star(self.build(expr))
        base = [self.build(expr) for _ in range(min_count)]
        if max_count is None:
            if not base:
                return self.kleene_star(self.build(expr))
            return self.concatenate_fragments(base + [self.kleene_star(self.build(expr))])
        optional_fragments = [self.alternate_fragments(self.build(expr), self.build({"type": "epsilon"})) for _ in range(max_count - min_count)]
        return self.concatenate_fragments(base + optional_fragments)


def symbol_to_str(symbol):
    if symbol is None:
        return "ε"
    if isinstance(symbol, frozenset):
        if symbol == DIGIT_SET:
            return r"\d"
        if symbol == UPPER_ALPHA_SET:
            return "[A-Z]"
        if symbol == TEXT_CHAR_SET:
            return r"[^:\|\n]"
        if len(symbol) == 1:
            char = next(iter(symbol))
            if char in {"|", ":", "\\", ".", "*", "+", "?", "(" , ")", "[", "]"}:
                return f"\\{char}"
            return char
        return "[" + "".join(sorted(symbol)) + "]"
    return str(symbol)


def get_nfa_states(nfa):
    states = {nfa["start"], nfa["accept"]}
    for transition in nfa["transitions"]:
        states.add(transition["from"])
        states.add(transition["to"])
    return sorted(states)


def epsilon_closure(transitions, state_ids):
    closure = set(state_ids)
    stack = list(state_ids)
    while stack:
        state = stack.pop()
        for transition in transitions:
            if transition["from"] == state and transition["symbol"] is None and transition["to"] not in closure:
                closure.add(transition["to"])
                stack.append(transition["to"])
    return frozenset(closure)


def move(transitions, state_ids, symbol):
    result = set()
    for transition in transitions:
        if transition["from"] in state_ids and transition["symbol"] == symbol:
            result.add(transition["to"])
    return result


def determinize_nfa(nfa):
    transitions = nfa["transitions"]
    alphabet = sorted(
        {transition["symbol"] for transition in transitions if transition["symbol"] is not None},
        key=lambda x: symbol_to_str(x),
    )
    start_closure = epsilon_closure(transitions, {nfa["start"]})
    state_map = {start_closure: 0}
    queue = [start_closure]
    dfa_transitions = []
    accept_states = set()
    while queue:
        current = queue.pop(0)
        current_id = state_map[current]
        if nfa["accept"] in current:
            accept_states.add(current_id)
        for symbol in alphabet:
            moved = move(transitions, current, symbol)
            if not moved:
                continue
            target = epsilon_closure(transitions, moved)
            if target not in state_map:
                state_map[target] = len(state_map)
                queue.append(target)
            dfa_transitions.append({"from": current_id, "symbol": symbol, "to": state_map[target]})
    return {
        "start": 0,
        "accepts": sorted(accept_states),
        "transitions": dfa_transitions,
        "alphabet": alphabet,
        "states": list(range(len(state_map))),
    }


def quote_label(value):
    return value.replace('"', '\\"')


def automaton_to_dot(name, automaton, shape='circle'):
    lines = [
        f'digraph "{name}" {{',
        '  rankdir=LR;',
        '  node [shape=circle, fontsize=12, fontname="Helvetica"];',
        '  init [shape=point, label=""];',
    ]
    for state in automaton["states"]:
        if state in automaton.get("accepts", []):
            lines.append(f'  {state} [shape=doublecircle];')
        else:
            lines.append(f'  {state};')
    lines.append(f'  init -> {automaton["start"]};')
    for transition in automaton["transitions"]:
        label = quote_label(transition["symbol"])
        lines.append(f'  {transition["from"]} -> {transition["to"]} [label="{label}"];')
    lines.append('}')
    return "\n".join(lines)


def build_nfa_from_pattern(pattern):
    parser = RegexParser(pattern)
    ast = parser.parse()
    builder = NFABuilder()
    nfa = builder.build(ast)
    dfa = determinize_nfa(nfa)
    nfa_def = {
        "start": nfa["start"],
        "states": get_nfa_states(nfa),
        "transitions": [
            {"from": t["from"], "symbol": symbol_to_str(t["symbol"]), "to": t["to"]}
            for t in nfa["transitions"]
        ],
        "accepts": [nfa["accept"]],
    }
    dfa_def = {
        "start": dfa["start"],
        "states": dfa["states"],
        "transitions": [
            {"from": t["from"], "symbol": symbol_to_str(t["symbol"]), "to": t["to"]}
            for t in dfa["transitions"]
        ],
        "accepts": dfa["accepts"],
    }
    dfa_json = _build_dfa_json(dfa)
    return {
        "pattern": pattern,
        "nfa": nfa_def,
        "dfa": dfa_json,
        "nfa_dot": automaton_to_dot(f"{pattern}_NFA", nfa_def),
        "dfa_dot": automaton_to_dot(f"{pattern}_DFA", dfa_def),
    }


def _build_dfa_json(dfa):
    return {
        "start": dfa["start"],
        "accepts": dfa["accepts"],
        "alphabet": [symbol_to_str(symbol) for symbol in dfa["alphabet"]],
        "states": dfa["states"],
        "transitions": [
            {"from": t["from"], "symbol": symbol_to_str(t["symbol"]), "to": t["to"]}
            for t in dfa["transitions"]
        ],
    }


def get_automata_definitions(token_types=None):
    token_patterns = {name: pattern for name, pattern in TOKEN_PATTERNS}
    if token_types is None:
        token_types = list(token_patterns.keys())
    else:
        # preserve order and remove duplicates
        token_types = list(dict.fromkeys(token_types))

    automata = []
    for token_type in token_types:
        pattern = token_patterns.get(token_type)
        if not pattern:
            continue
        built = build_nfa_from_pattern(pattern)
        automata.append({
            "token": token_type,
            "pattern": pattern,
            "nfa": built["nfa"],
            "dfa": built["dfa"],
            "nfa_dot": built["nfa_dot"],
            "dfa_dot": built["dfa_dot"],
        })
    return automata


def get_grammar_rules():
    return [
        "S → DOCUMENTO",
        "DOCUMENTO → ORDEN FECHA CLIENTE LISTA_ITEMS TOTAL",
        "ORDEN → \"ORDEN\" ':' COD_ORDEN",
        "COD_ORDEN → LETRAS '-' NUMERO '-' NUMERO",
        "FECHA → \"FECHA\" ':' DIA '/' MES '/' ANIO",
        "DIA → NUMERO NUMERO",
        "MES → NUMERO NUMERO",
        "ANIO → NUMERO NUMERO NUMERO NUMERO",
        "CLIENTE → \"CLIENTE\" ':' NOMBRE",
        "NOMBRE → PALABRA | PALABRA NOMBRE",
        "LISTA_ITEMS → ITEM | ITEM LISTA_ITEMS",
        "ITEM → \"ITEM\" ':' COD_PRODUCTO '|' DESCRIPCION '|' CANTIDAD '|' PRECIO",
        "COD_PRODUCTO → LETRA '-' NUMERO",
        "DESCRIPCION → PALABRA | PALABRA DESCRIPCION",
        "CANTIDAD → NUMERO",
        "PRECIO → NUMERO '.' NUMERO",
        "TOTAL → \"TOTAL\" ':' PRECIO",
    ]

class ParseNode:
    def __init__(self, symbol, children=None, value=None):
        self.symbol = symbol
        self.children = children or []
        self.value = value

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "value": self.value,
            "children": [child.to_dict() for child in self.children],
        }

    def pretty(self, indent=0):
        prefix = "  " * indent
        value = f": {self.value}" if self.value is not None else ""
        lines = [f"{prefix}{self.symbol}{value}"]
        for child in self.children:
            lines.extend(child.pretty(indent + 1).splitlines())
        return "\n".join(lines)


def build_parse_tree(parsed):
    if not parsed:
        return None

    def build_codigo_orden(order_id):
        parts = order_id.split("-")
        return ParseNode("COD_ORDEN", [
            ParseNode("LETRAS", value=parts[0]),
            ParseNode("-", value="-"),
            ParseNode("NUMERO", value=parts[1]),
            ParseNode("-", value="-"),
            ParseNode("NUMERO", value=parts[2]),
        ])

    def build_fecha(fecha):
        dia, mes, anio = fecha.split("/")
        return ParseNode("FECHA", [
            ParseNode("\"FECHA\"", value="FECHA"),
            ParseNode(":", value=":"),
            ParseNode("DIA", [ParseNode("NUMERO", value=dia[0:2]), ParseNode("NUMERO", value=dia[2:4])]),
            ParseNode("/", value="/"),
            ParseNode("MES", [ParseNode("NUMERO", value=mes[0:2]), ParseNode("NUMERO", value=mes[2:4])]),
            ParseNode("/", value="/"),
            ParseNode("ANIO", [ParseNode("NUMERO", value=anio[i:i+1]) for i in range(4)]),
        ])

    def build_nombre(value, symbol_name="NOMBRE"):
        parts = value.split()
        if not parts:
            return ParseNode(symbol_name)
        if len(parts) == 1:
            return ParseNode(symbol_name, [ParseNode("PALABRA", value=parts[0])])
        return ParseNode(symbol_name, [ParseNode("PALABRA", value=parts[0]), build_nombre(" ".join(parts[1:]), symbol_name)])

    def build_codigo_producto(code):
        letra, numero = code.split("-", 1)
        return ParseNode("COD_PRODUCTO", [
            ParseNode("LETRA", value=letra),
            ParseNode("-", value="-"),
            ParseNode("NUMERO", value=numero),
        ])

    def build_precio(price):
        left, right = price.split(".")
        return ParseNode("PRECIO", [ParseNode("NUMERO", value=left), ParseNode(".", value="."), ParseNode("NUMERO", value=right)])

    def build_item(item):
        return ParseNode("ITEM", [
            ParseNode("\"ITEM\"", value="ITEM"),
            ParseNode(":", value=":"),
            build_codigo_producto(item["code"]),
            ParseNode("|", value="|"),
            build_nombre(item["description"], symbol_name="DESCRIPCION"),
            ParseNode("|", value="|"),
            ParseNode("CANTIDAD", [ParseNode("NUMERO", value=str(item["quantity"]))]),
            ParseNode("|", value="|"),
            build_precio(f"{item['price']:.2f}"),
        ])

    def build_lista_items(items):
        if len(items) == 1:
            return ParseNode("LISTA_ITEMS", [build_item(items[0])])
        return ParseNode("LISTA_ITEMS", [build_item(items[0]), build_lista_items(items[1:])])

    documento = ParseNode("DOCUMENTO", [
        ParseNode("ORDEN", [ParseNode("\"ORDEN\"", value="ORDEN"), ParseNode(":", value=":"), build_codigo_orden(parsed["order_id"])]),
        build_fecha(parsed["date"]),
        ParseNode("CLIENTE", [ParseNode("\"CLIENTE\"", value="CLIENTE"), ParseNode(":", value=":"), build_nombre(parsed["client"])]),
        build_lista_items(parsed["items"]),
        ParseNode("TOTAL", [ParseNode("\"TOTAL\"", value="TOTAL"), ParseNode(":", value=":"), build_precio(f"{parsed['total']:.2f}")]),
    ])
    root = ParseNode("S", [documento])
    return {"tree": root.to_dict(), "text": root.pretty()}


def tree_dict_to_dot(tree):
    # Convert parse tree dict (from ParseNode.to_dict) into Graphviz DOT
    lines = ["digraph parse_tree {", '  node [shape=box, fontsize=12, fontname="Helvetica"];', '  rankdir=TB;']
    counter = {"n": 0}

    def visit(node):
        nid = f'n{counter["n"]}'
        counter["n"] += 1
        label = node.get("symbol", "")
        if node.get("value") is not None:
            label = f"{label}: {node['value']}"
        label = label.replace('"', '\\"')
        lines.append(f'  {nid} [label="{label}"];')
        for child in node.get("children", []):
            cid = visit(child)
            lines.append(f'  {nid} -> {cid};')
        return nid

    visit(tree)
    lines.append('}')
    return "\n".join(lines)


def get_token_analysis(tokens):
    grouped = {}
    for token in tokens:
        grouped.setdefault(token["type"], []).append(token["value"])
    patterns = {definition["type"]: definition["pattern"] for definition in TOKEN_DEFINITIONS}
    return [
        {"type": token_type, "pattern": patterns.get(token_type, ""), "lexemes": lexemes}
        for token_type, lexemes in grouped.items()
    ]

SAMPLE_ORDER = """ORDEN: OC-2026-001
FECHA: 15/03/2026
CLIENTE: Distribuidora El Sol
ITEM: P-100 | Tornillo de acero | 200 | 0.15
ITEM: P-200 | Tuerca M6 | 150 | 0.20
TOTAL: 60.00
"""


def lex_order(text):
    tokens = []
    errors = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        position = 0
        while position < len(line):
            match = TOKEN_REGEX.match(line, position)
            if not match:
                errors.append(
                    {
                        "line": line_no,
                        "column": position + 1,
                        "message": f"Carácter inesperado '{line[position]}'",
                    }
                )
                position += 1
                continue

            kind = match.lastgroup
            value = match.group(kind).strip()
            position = match.end()

            if kind == "TEXT":
                value = value.strip()
                if not value:
                    continue

            if kind == "MISMATCH":
                errors.append(
                    {
                        "line": line_no,
                        "column": position,
                        "message": f"Token no reconocido '{value}'",
                    }
                )
                continue

            tokens.append({"type": kind, "value": value, "line": line_no})

    return tokens, errors


def parse_order(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    errors = []
    data = {
        "order_id": None,
        "date": None,
        "client": None,
        "items": [],
        "total": None,
    }

    for index, line in enumerate(lines):
        line_no = index + 1
        if line.upper().startswith("ORDEN:"):
            data["order_id"] = line.split(":", 1)[1].strip()
            continue
        if line.upper().startswith("FECHA:"):
            data["date"] = line.split(":", 1)[1].strip()
            continue
        if line.upper().startswith("CLIENTE:"):
            data["client"] = line.split(":", 1)[1].strip()
            continue
        if line.upper().startswith("ITEM:"):
            raw_item = line.split(":", 1)[1].strip()
            parts = [part.strip() for part in raw_item.split("|")]
            if len(parts) != 4:
                errors.append(
                    {
                        "line": line_no,
                        "message": "Cada línea ITEM debe tener 4 campos: código | descripción | cantidad | precio.",
                    }
                )
                continue

            code, description, qty_text, price_text = parts
            if not code:
                errors.append(
                    {"line": line_no, "message": "El código del artículo no puede estar vacío."}
                )
            if not description:
                errors.append(
                    {"line": line_no, "message": "La descripción del artículo no puede estar vacía."}
                )

            try:
                quantity = int(qty_text)
            except ValueError:
                errors.append(
                    {"line": line_no, "message": "La cantidad debe ser un número entero."}
                )
                quantity = None

            try:
                price = float(price_text)
            except ValueError:
                errors.append(
                    {"line": line_no, "message": "El precio debe ser un número válido."}
                )
                price = None

            data["items"].append(
                {
                    "code": code,
                    "description": description,
                    "quantity": quantity,
                    "price": price,
                }
            )
            continue
        if line.upper().startswith("TOTAL:"):
            total_text = line.split(":", 1)[1].strip()
            try:
                data["total"] = float(total_text)
            except ValueError:
                errors.append(
                    {"line": line_no, "message": "El total debe ser un número válido."}
                )
            continue

        errors.append(
            {
                "line": line_no,
                "message": "Línea no reconocida o sintaxis inválida.",
            }
        )

    if data["order_id"] is None:
        errors.append({"line": 0, "message": "Falta la línea ORDEN."})
    if data["date"] is None:
        errors.append({"line": 0, "message": "Falta la línea FECHA."})
    if data["client"] is None:
        errors.append({"line": 0, "message": "Falta la línea CLIENTE."})
    if not data["items"]:
        errors.append({"line": 0, "message": "Debe haber al menos un artículo ITEM."})
    if data["total"] is None:
        errors.append({"line": 0, "message": "Falta la línea TOTAL."})

    return data, errors


def validate_semantics(data):
    errors = []
    if data["order_id"] and len(data["order_id"]) < 3:
        errors.append("El número de orden es demasiado corto.")

    if data["date"]:
        try:
            parsed_date = datetime.strptime(data["date"], "%d/%m/%Y")
            if parsed_date.year < 2020 or parsed_date.year > datetime.now().year + 1:
                errors.append("La fecha está fuera del rango esperado.")
        except ValueError:
            errors.append("La fecha debe tener el formato DD/MM/YYYY.")

    if data["client"] and len(data["client"]) < 3:
        errors.append("El nombre del cliente es demasiado corto.")

    seen_codes = set()
    line = 0
    subtotal = 0.0
    for item in data["items"]:
        line += 1
        if item["code"] in seen_codes:
            errors.append(f"El código de artículo '{item['code']}' está repetido.")
        seen_codes.add(item["code"])
        if item["quantity"] is None or item["quantity"] <= 0:
            errors.append(f"La cantidad del artículo '{item['code']}' debe ser mayor que cero.")
        if item["price"] is None or item["price"] <= 0:
            errors.append(f"El precio del artículo '{item['code']}' debe ser mayor que cero.")
        if item["quantity"] is not None and item["price"] is not None:
            subtotal += item["quantity"] * item["price"]

    if data["total"] is not None:
        expected_total = round(subtotal, 2)
        if abs(expected_total - data["total"]) > 0.01:
            errors.append(
                f"El total indicado ({data['total']:.2f}) no coincide con el total esperado ({expected_total:.2f})."
            )

    return errors


def analyze_order(text):
    tokens, lexical_errors = lex_order(text)
    parsed, syntax_errors = parse_order(text)
    semantic_errors = []
    if not syntax_errors:
        semantic_errors = validate_semantics(parsed)

    token_analysis = get_token_analysis(tokens)
    automata = get_automata_definitions([token['type'] for token in tokens])
    grammar_rules = get_grammar_rules()
    parse_tree = None
    if not syntax_errors and parsed["order_id"] and parsed["date"] and parsed["client"] and parsed["items"] and parsed["total"] is not None:
        try:
            parse_tree = build_parse_tree(parsed)
        except Exception:
            parse_tree = None
    parse_tree_img = None
    parse_tree_dot = None
    if parse_tree:
        try:
            parse_tree_dot = tree_dict_to_dot(parse_tree["tree"])
        except Exception:
            parse_tree_dot = None
        if HAS_GRAPHVIZ and parse_tree_dot:
            try:
                src = graphviz.Source(parse_tree_dot)
                png_bytes = src.pipe(format="png")
                if png_bytes:
                    parse_tree_img = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')
            except Exception:
                parse_tree_img = None

    return {
        "tokens": tokens,
        "token_analysis": token_analysis,
        "automata": automata,
        "grammar_rules": grammar_rules,
        "parse_tree": parse_tree,
        "parse_tree_dot": parse_tree_dot,
        "parse_tree_img": parse_tree_img,
        "lexical_errors": lexical_errors,
        "syntax_errors": syntax_errors,
        "semantic_errors": semantic_errors,
        "parsed_order": parsed,
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", sample_order=SAMPLE_ORDER)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    content = request.json or {}
    order_text = content.get("order_text", "").strip()
    result = analyze_order(order_text)
    result["success"] = not (
        result["lexical_errors"] or result["syntax_errors"] or result["semantic_errors"]
    )
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
