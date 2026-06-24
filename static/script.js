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
const tokenAnalysisEl = document.getElementById('token-analysis');
const grammarRulesEl = document.getElementById('grammar-rules');
const automataSelect = document.getElementById('automata-select');
const automataNfaEl = document.getElementById('automata-nfa');
const automataDfaEl = document.getElementById('automata-dfa');
const automataDfaTableEl = document.getElementById('automata-dfa-table');
const parseTreeEl = document.getElementById('parse-tree');
const parseTreeImgEl = document.getElementById('parse-tree-img');
const parseTreeSvgContainer = document.getElementById('parse-tree-svg');
const loadSampleButton = document.getElementById('load-sample');
const sampleText = document.getElementById('sample')?.textContent.trim() || '';

if (loadSampleButton) {
  loadSampleButton.addEventListener('click', () => {
    if (!orderText) return;
    orderText.value = sampleText;
    orderText.focus();
    if (resultsSection) resultsSection.hidden = true;
  });
}

if (form) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!orderText) return;
    const text = orderText.value.trim();
    if (!text) return;

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_text: text }),
      });

      const responseText = await response.text();
      if (!response.ok) {
        console.error('API error response', response.status, responseText);
        throw new Error(`HTTP ${response.status}`);
      }

      let data;
      try {
        data = JSON.parse(responseText);
      } catch (parseError) {
        console.error('JSON parse error', parseError, responseText);
        throw parseError;
      }

      if (resultsSection) resultsSection.hidden = false;

      const hasErrors = data.lexical_errors.length > 0 || data.syntax_errors.length > 0 || data.semantic_errors.length > 0;
      if (statusEl) {
        statusEl.textContent = hasErrors ? 'Validación completada con errores.' : 'Orden válida. No se detectaron errores.';
        statusEl.className = `status ${hasErrors ? 'error' : 'success'}`;
      }

      if (lexicalStatusEl) lexicalStatusEl.textContent = renderStatusLabel(data.lexical_errors);
      if (syntaxStatusEl) syntaxStatusEl.textContent = renderStatusLabel(data.syntax_errors);
      if (semanticStatusEl) semanticStatusEl.textContent = renderStatusLabel(data.semantic_errors);

      if (lexicalEl) lexicalEl.innerHTML = createList(data.lexical_errors);
      if (syntaxEl) syntaxEl.innerHTML = createList(data.syntax_errors);
      if (semanticEl) semanticEl.innerHTML = createList(data.semantic_errors);
      if (tokensEl) tokensEl.innerHTML = renderTokens(data.tokens);
      if (tokenAnalysisEl) tokenAnalysisEl.innerHTML = renderTokenAnalysis(data.token_analysis);
      if (grammarRulesEl) grammarRulesEl.innerHTML = renderGrammarRules(data.grammar_rules);
      populateAutomataControls(data.automata);

      // Prefer server-rendered PNG if available
      if (parseTreeImgEl && data.parse_tree_img) {
        parseTreeImgEl.src = data.parse_tree_img;
        parseTreeImgEl.style.display = 'block';
        if (parseTreeEl) parseTreeEl.style.display = 'none';
        if (parseTreeSvgContainer) parseTreeSvgContainer.innerHTML = '';
      } else if (parseTreeSvgContainer && data.parse_tree_dot && typeof Viz !== 'undefined') {
        // Render DOT client-side with Viz.js
        if (parseTreeImgEl) {
          parseTreeImgEl.style.display = 'none';
          parseTreeImgEl.src = '';
        }
        if (parseTreeEl) parseTreeEl.style.display = 'none';
        parseTreeSvgContainer.innerHTML = '';
        if (!vizInstance) vizInstance = new Viz();
        vizInstance.renderSVGElement(data.parse_tree_dot)
          .then(svg => parseTreeSvgContainer.appendChild(svg))
          .catch(err => {
            parseTreeSvgContainer.innerHTML = `<pre>Error renderizando árbol: ${err.message}</pre>`;
          });
      } else {
        if (parseTreeImgEl) {
          parseTreeImgEl.style.display = 'none';
          parseTreeImgEl.src = '';
        }
        if (parseTreeSvgContainer) parseTreeSvgContainer.innerHTML = '';
        if (parseTreeEl) {
          parseTreeEl.style.display = 'block';
          parseTreeEl.textContent = renderParseTree(data.parse_tree);
        }
      }
      if (orderSummaryEl) orderSummaryEl.innerHTML = renderOrderSummary(data.parsed_order);
    } catch (error) {
      console.error('Error analyzing order:', error);
      if (statusEl) {
        statusEl.textContent = 'Error al procesar la orden. Revisa la consola.';
        statusEl.className = 'status error';
      }
      if (resultsSection) resultsSection.hidden = false;
    }
  });
}

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
    return '<tr><td colspan="2">No se encontraron tokens.</td></tr>';
  }

  // Agrupar tokens por tipo
  const groupedTokens = {};
  tokens.forEach(token => {
    if (!groupedTokens[token.type]) {
      groupedTokens[token.type] = [];
    }
    groupedTokens[token.type].push(token.value);
  });

  // Generar filas agrupadas
  return Object.entries(groupedTokens).map(([tokenType, lexemes]) => `
    <tr>
      <td><span class="token-type">${tokenType}</span></td>
      <td>${lexemes.join(', ')}</td>
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

function renderTokenAnalysis(analysis) {
  if (!analysis || analysis.length === 0) {
    return '<tr><td colspan="3">No hay análisis de tokens.</td></tr>';
  }
  return analysis.map(entry => `
    <tr>
      <td>${entry.type}</td>
      <td><code>${entry.pattern}</code></td>
      <td>${entry.lexemes.join(', ')}</td>
    </tr>
  `).join('');
}

function renderGrammarRules(rules) {
  if (!rules || rules.length === 0) {
    return '<li>No hay reglas de gramática disponibles.</li>';
  }
  return rules.map(rule => `<li>${rule}</li>`).join('');
}

let vizInstance = null;
let automataList = [];
const treeModal = document.getElementById('tree-modal');
const treeModalContent = document.getElementById('tree-modal-content');
const treeModalClose = document.getElementById('tree-modal-close');
const treeZoomInButton = document.getElementById('tree-zoom-in');
const treeZoomOutButton = document.getElementById('tree-zoom-out');
const treeResetZoomButton = document.getElementById('tree-reset-zoom');

let treeViewer = null;
let treePanArea = null;
let isPanning = false;
let panStart = { x: 0, y: 0 };
let panOffset = { x: 0, y: 0 };
let treeScale = 1;

function resetAutomataDisplay() {
  automataSelect.innerHTML = '';
  automataNfaEl.innerHTML = '';
  automataDfaEl.innerHTML = '';
  if (automataDfaTableEl) automataDfaTableEl.innerHTML = '';
}

initializeTreeControls();
defaultTreeClickSetup();

function defaultTreeClickSetup() {
  const treeVisual = document.querySelector('.tree-visual');
  if (!treeVisual) return;
  treeVisual.classList.add('clickable-tree');
  treeVisual.addEventListener('click', openTreeModal);
}

function initializeTreeControls() {
  if (treeZoomInButton) treeZoomInButton.addEventListener('click', () => zoomTree(1.2));
  if (treeZoomOutButton) treeZoomOutButton.addEventListener('click', () => zoomTree(0.85));
  if (treeResetZoomButton) treeResetZoomButton.addEventListener('click', resetTreeView);
}

function openTreeModal() {
  if (!treeModal || !treeModalContent) return;
  treeModal.classList.add('active');
  treeModalContent.innerHTML = `
    <div class="tree-modal-viewer" id="tree-modal-viewer">
      <div class="tree-modal-pan-area" id="tree-modal-pan-area"></div>
    </div>
  `;

  treeViewer = document.getElementById('tree-modal-viewer');
  treePanArea = document.getElementById('tree-modal-pan-area');
  if (!treePanArea || !treeViewer) return;

  const svgElement = parseTreeSvgContainer?.querySelector('svg');
  if (svgElement) {
    treePanArea.appendChild(svgElement.cloneNode(true));
    setupTreePan();
    resetTreeView();
    return;
  }

  const treeImageSrc = parseTreeImgEl?.getAttribute('src')?.trim();
  if (treeImageSrc) {
    const thumbnail = document.createElement('img');
    thumbnail.src = treeImageSrc;
    thumbnail.alt = 'Árbol sintáctico ampliado';
    thumbnail.style.display = 'block';
    thumbnail.style.maxWidth = 'none';
    thumbnail.style.maxHeight = 'none';
    thumbnail.style.width = '100%';
    thumbnail.style.height = 'auto';
    treePanArea.appendChild(thumbnail);
    setupTreePan();
    resetTreeView();
    return;
  }

  if (parseTreeEl && parseTreeEl.textContent) {
    treePanArea.appendChild(document.createElement('pre')).textContent = parseTreeEl.textContent;
    treePanArea.style.padding = '20px';
    return;
  }

  const emptyMessage = document.createElement('p');
  emptyMessage.textContent = 'No hay contenido del árbol para mostrar.';
  emptyMessage.style.margin = '0';
  emptyMessage.style.color = '#334155';
  treePanArea.appendChild(emptyMessage);
}

function setupTreePan() {
  if (!treeViewer || !treePanArea) return;
  treePanArea.style.transform = `translate(0px, 0px) scale(${treeScale})`;
  treeViewer.addEventListener('pointerdown', beginPan);
  treeViewer.addEventListener('pointermove', movePan);
  treeViewer.addEventListener('pointerup', endPan);
  treeViewer.addEventListener('pointerleave', endPan);
  treeViewer.addEventListener('wheel', handleWheelZoom, { passive: false });
  treeViewer.style.touchAction = 'none';
}

function beginPan(event) {
  if (!treePanArea) return;
  isPanning = true;
  treeViewer.classList.add('grabbing');
  panStart = { x: event.clientX - panOffset.x, y: event.clientY - panOffset.y };
  treeViewer.setPointerCapture(event.pointerId);
}

function movePan(event) {
  if (!isPanning || !treePanArea) return;
  panOffset = { x: event.clientX - panStart.x, y: event.clientY - panStart.y };
  treePanArea.style.transform = `translate(${panOffset.x}px, ${panOffset.y}px) scale(${treeScale})`;
}

function endPan(event) {
  if (!isPanning || !treeViewer) return;
  isPanning = false;
  treeViewer.classList.remove('grabbing');
  if (event.pointerId) {
    treeViewer.releasePointerCapture(event.pointerId);
  }
}

function handleWheelZoom(event) {
  if (!treeViewer || !treePanArea) return;
  event.preventDefault();
  const delta = event.deltaY > 0 ? 0.9 : 1.1;
  zoomTree(delta);
}

function zoomTree(factor) {
  treeScale = Math.min(4, Math.max(0.6, treeScale * factor));
  if (treePanArea) {
    treePanArea.style.transform = `translate(${panOffset.x}px, ${panOffset.y}px) scale(${treeScale})`;
  }
}

function resetTreeView() {
  treeScale = 1;
  panOffset = { x: 0, y: 0 };
  if (treePanArea) {
    treePanArea.style.transform = `translate(0px, 0px) scale(${treeScale})`;
  }
}

function closeTreeModal() {
  if (!treeModal) return;
  treeModal.classList.remove('active');
}

if (treeModalClose) {
  treeModalClose.addEventListener('click', closeTreeModal);
}
if (treeModal) {
  treeModal.addEventListener('click', (event) => {
    if (event.target === treeModal) {
      closeTreeModal();
    }
  });
}

window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && treeModal?.classList.contains('active')) {
    closeTreeModal();
  }
});

function populateAutomataControls(automata) {
  resetAutomataDisplay();
  automataList = automata || [];

  if (!automataList.length) {
    const message = document.createElement('p');
    message.textContent = 'No hay autómatas disponibles.';
    automataNfaEl.appendChild(message);
    return;
  }

  automataList.forEach((entry, index) => {
    const option = document.createElement('option');
    option.value = index;
    option.textContent = entry.pattern;
    automataSelect.appendChild(option);
  });

  automataSelect.onchange = () => renderSelectedAutomaton(Number(automataSelect.value));
  if (automataList.length > 0) {
    automataSelect.value = 0;
    renderSelectedAutomaton(0);
  }
}

function renderSelectedAutomaton(index) {
  automataNfaEl.innerHTML = '';
  automataDfaEl.innerHTML = '';

  if (!automataList.length || !automataList[index]) {
    return;
  }

  const automaton = automataList[index];
  if (typeof Viz === 'undefined') {
    automataNfaEl.textContent = 'No se puede renderizar los autómatas: falta Viz.js.';
    automataDfaEl.textContent = 'No se puede renderizar los autómatas: falta Viz.js.';
    return;
  }

  if (!vizInstance) {
    vizInstance = new Viz();
  }

  vizInstance.renderSVGElement(automaton.nfa_dot)
    .then(svg => automataNfaEl.appendChild(svg))
    .catch(err => {
      automataNfaEl.innerHTML = `<pre>Error NFA: ${err.message}</pre>`;
    });

  vizInstance.renderSVGElement(automaton.dfa_dot)
    .then(svg => automataDfaEl.appendChild(svg))
    .catch(err => {
      automataDfaEl.innerHTML = `<pre>Error DFA: ${err.message}</pre>`;
    });

  renderAutomatonTransitionTables(automaton);
}

function renderAutomatonTransitionTables(automaton) {
  if (automataDfaTableEl) {
    automataDfaTableEl.innerHTML = renderTransitionTable('DFA', automaton.dfa);
  }
}

function renderTransitionTable(title, automaton) {
  if (!automaton || !automaton.transitions || automaton.transitions.length === 0) {
    return `<p>No hay transiciones disponibles para el ${title}.</p>`;
  }

  const states = Array.from(new Set(automaton.transitions.flatMap(t => [t.from, t.to]))).sort((a, b) => a - b);
  // Mantener el orden en que aparecen los símbolos en las transiciones, sin ordenar
  const symbols = Array.from(new Set(automaton.transitions.map(t => t.symbol)));

  const rows = states.map(state => {
    const cells = symbols.map(symbol => {
      const dests = automaton.transitions
        .filter(t => t.from === state && t.symbol === symbol)
        .map(t => t.to)
        .sort((a, b) => a - b);
      return `<td>${dests.length ? dests.join(', ') : '∅'}</td>`;
    }).join('');
    return `<tr><th>${state}${automaton.accepts?.includes(state) ? ' *' : ''}</th>${cells}</tr>`;
  });

  const headerCells = symbols.map(symbol => `<th>${symbol}</th>`).join('');
  return `
    <div class="automata-table-caption"><strong>Tabla de Transiciones</strong></div>
    <table>
      <thead>
        <tr>
          <th>Estado</th>
          ${headerCells}
        </tr>
      </thead>
      <tbody>
        ${rows.join('')}
      </tbody>
    </table>
  `;
}

function renderParseTree(tree) {
  if (!tree || !tree.text) {
    return 'No se generó el árbol sintáctico.';
  }
  return tree.text;
}

function renderStatusLabel(errors) {
  if (!errors || errors.length === 0) {
    return 'Válido';
  }
  return `${errors.length} error${errors.length === 1 ? '' : 'es'}`;
}

