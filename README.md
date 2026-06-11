# Validador de Órdenes de Compra

Proyecto web en Python y Flask para validar órdenes de compra mediante análisis léxico, sintáctico y semántico.

## Estructura del proyecto

- `app.py` - servidor Flask y motor de análisis de órdenes.
- `templates/index.html` - interfaz web principal.
- `static/style.css` - estilos de la aplicación.
- `static/script.js` - lógica de frontend para enviar órdenes y mostrar resultados.
- `requirements.txt` - dependencias del proyecto.
- `Procfile` - configuración de despliegue para Gunicorn.

## Requisitos

- Python 3.10 o superior.
- Entorno virtual recomendado.

## Instalación

1. Abre una terminal en la carpeta `proyecto_Compiladores`.
2. Crea un entorno virtual (recomendado):

   ```bash
   python -m venv venv
   ```

3. Activa el entorno virtual según tu terminal:

   Windows PowerShell:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

   Windows CMD:
   ```cmd
   .\venv\Scripts\activate.bat
   ```

   Git Bash / WSL:
   ```bash
   source venv/Scripts/activate
   ```

4. Instala las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

## Ejecutar localmente

1. Asegúrate de que el entorno virtual esté activado y ejecuta la aplicación:

   ```bash
   python app.py
   ```

2. Abre tu navegador en:

   ```text
   http://127.0.0.1:5000
   ```

> Si usas VS Code, abre la carpeta del proyecto y ejecuta estos comandos en el terminal integrado para que el entorno virtual se active correctamente.

## Ejemplo de uso

### Orden válida

```text
ORDEN: OC-2026-001
FECHA: 15/03/2026
CLIENTE: Distribuidora El Sol
ITEM: P-100 | Tornillo de acero | 200 | 0.15
ITEM: P-200 | Tuerca M6 | 150 | 0.20
TOTAL: 60.00
```

### Orden con error semántico

```text
ORDEN: OC-2026-001
FECHA: 15/03/2026
CLIENTE: Distribuidora El Sol
ITEM: P-100 | Tornillo de acero | 200 | 0.15
ITEM: P-200 | Tuerca M6 | 150 | 0.20
TOTAL: 55.00
```

En este caso, el validador detectará que el total indicado no coincide con la suma de los artículos.

## API

El proyecto también expone un endpoint JSON para análisis programático:

- `POST /api/analyze`
- Cuerpo JSON:

```json
{
  "order_text": "ORDEN: OC-2026-001\nFECHA: 15/03/2026\n..."
}
```

- Respuesta JSON contiene:
  - `tokens`
  - `lexical_errors`
  - `syntax_errors`
  - `semantic_errors`
  - `parsed_order`
  - `success`

## Despliegue

Para desplegar en una plataforma compatible con `Procfile`, se usa:

```text
web: gunicorn app:app
```

## Notas

- El formato de orden debe respetar las claves: `ORDEN`, `FECHA`, `CLIENTE`, `ITEM`, `TOTAL`.
- Cada línea `ITEM` debe tener la forma: `ITEM: código | descripción | cantidad | precio`.
- El validador calcula el total esperado como suma de `cantidad * precio`.
