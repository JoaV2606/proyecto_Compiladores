from datetime import datetime
from flask import Flask, render_template, request, jsonify
import re

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

    return {
        "tokens": tokens,
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
