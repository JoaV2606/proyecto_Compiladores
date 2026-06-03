const form = document.getElementById('order-form');
const orderText = document.getElementById('order-text');
const resultsSection = document.getElementById('results');
const statusEl = document.getElementById('status');
const lexicalEl = document.getElementById('lexical-errors');
const syntaxEl = document.getElementById('syntax-errors');
const semanticEl = document.getElementById('semantic-errors');
const tokensEl = document.getElementById('tokens');
const parsedEl = document.getElementById('parsed');

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
      <td>${token.type}</td>
      <td>${token.value}</td>
    </tr>
  `).join('');
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
  lexicalEl.innerHTML = createList(data.lexical_errors);
  syntaxEl.innerHTML = createList(data.syntax_errors);
  semanticEl.innerHTML = createList(data.semantic_errors);
  tokensEl.innerHTML = renderTokens(data.tokens);
  parsedEl.textContent = JSON.stringify(data.parsed_order, null, 2);
});
