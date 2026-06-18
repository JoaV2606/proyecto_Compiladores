const form = document.getElementById('order-form');
const orderText = document.getElementById('order-text');
const resultsSection = document.getElementById('results');
const statusEl = document.getElementById('status');
const lexicalEl = document.getElementById('lexical-errors');
const syntaxEl = document.getElementById('syntax-errors');
const semanticEl = document.getElementById('semantic-errors');
const tokensEl = document.getElementById('tokens');
const lexicalStatusEl = document.getElementById('lexical-status');
const syntaxStatusEl = document.getElementById('syntax-status');
const semanticStatusEl = document.getElementById('semantic-status');
const orderSummaryEl = document.getElementById('order-summary');
const loadSampleButton = document.getElementById('load-sample');
const sampleText = document.getElementById('sample')?.textContent.trim() || '';

loadSampleButton?.addEventListener('click', () => {
  orderText.value = sampleText;
  orderText.focus();
  resultsSection.hidden = true;
});

function createList(items) {
  if (!items || items.length === 0) {
    return '<li>Ninguno</li>';
  }
  return items.map(item => {
    if (typeof item === 'string') {
      return `<li>${item}</li>`;
    }
    return `<li>Linea ${item.line || '-'}: ${item.message}</li>`;
  }).join('');
}

function renderTokens(tokens) {
  if (!tokens || tokens.length === 0) {
    return '<tr><td colspan="3">No se encontraron tokens.</td></tr>';
  }
  return tokens.map(token => `
    <tr>
      <td>${token.line}</td>
      <td><span class="token-type">${token.type}</span></td>
      <td>${token.value || '-'}</td>
    </tr>
  `).join('');
}

function renderOrderSummary(parsed) {
  if (!parsed || Object.keys(parsed).length === 0) {
    return '<p>No se pudo generar el resumen de la orden.</p>';
  }

  const items = parsed.items || [];
  const itemRows = items.length
    ? `<div class="order-summary-row">
        <strong>Artículos</strong>
        <table>
          <thead>
            <tr><th>Código</th><th>Descripción</th><th>Cantidad</th><th>Precio</th></tr>
          </thead>
          <tbody>
            ${items.map(item => `
              <tr>
                <td>${item.code || '-'}</td>
                <td>${item.description || '-'}</td>
                <td>${item.quantity ?? '-'}</td>
                <td>${item.price != null ? item.price.toFixed(2) : '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`
    : '<p>No hay artículos válidos para mostrar.</p>';

  return `
    <div class="order-summary">
      <div class="order-summary-row">
        <dl>
          <dt>Número de orden</dt><dd>${parsed.order_id || '-'}</dd>
          <dt>Fecha</dt><dd>${parsed.date || '-'}</dd>
          <dt>Cliente</dt><dd>${parsed.client || '-'}</dd>
          <dt>Total</dt><dd>${parsed.total != null ? parsed.total.toFixed(2) : '-'}</dd>
        </dl>
      </div>
      ${itemRows}
    </div>
  `;
}

function renderStatusLabel(errors) {
  if (!errors || errors.length === 0) {
    return 'Válido';
  }
  return `${errors.length} error${errors.length === 1 ? '' : 'es'}`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = orderText.value.trim();
  if (!text) {
    return;
  }

  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_text: text }),
  });

  const data = await response.json();
  resultsSection.hidden = false;

  const hasErrors = data.lexical_errors.length > 0 || data.syntax_errors.length > 0 || data.semantic_errors.length > 0;
  statusEl.textContent = hasErrors ? 'Validación completada con errores.' : 'Orden válida. No se detectaron errores.';
  statusEl.className = `status ${hasErrors ? 'error' : 'success'}`;

  lexicalStatusEl.textContent = renderStatusLabel(data.lexical_errors);
  syntaxStatusEl.textContent = renderStatusLabel(data.syntax_errors);
  semanticStatusEl.textContent = renderStatusLabel(data.semantic_errors);

  lexicalEl.innerHTML = createList(data.lexical_errors);
  syntaxEl.innerHTML = createList(data.syntax_errors);
  semanticEl.innerHTML = createList(data.semantic_errors);
  tokensEl.innerHTML = renderTokens(data.tokens);
  orderSummaryEl.innerHTML = renderOrderSummary(data.parsed_order);
});
