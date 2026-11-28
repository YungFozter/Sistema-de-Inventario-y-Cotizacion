/**
 * productos_importacion_pdf.js
 * Módulo de importación multi-PDF y texto pegado con separación visual por documento
 * y fusión ordenada secuencial (PDF #1 -> PDF #2 -> ... -> PDF #N) al guardar/exportar.
 */

(function () {
  'use strict';

  // Estado ordenado de lotes/documentos cargados en la sesión del modal
  let lotesImportados = [];
  let contadorLotesSecuencia = 0;
  let ultimoTextoProcesado = '';

  // Mantener referencia global sincronizada por compatibilidad
  window.itemsImportados = [];

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return str
      .toString()
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function autoAjustarTextarea(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.max(46, el.scrollHeight + 4) + 'px';
  }

  /**
   * Fusiona todos los lotes en un único arreglo respetando estrictamente
   * el orden secuencial de los PDFs importados (PDF #1 -> PDF #2 -> PDF #N).
   */
  function obtenerItemsFusionados(soloSeleccionados = false) {
    const resultado = [];
    lotesImportados.forEach((lote) => {
      (lote.items || []).forEach((item) => {
        if (!soloSeleccionados || item.selected) {
          resultado.push(item);
        }
      });
    });
    return resultado;
  }

  function sincronizarEstadoGlobal() {
    window.itemsImportados = obtenerItemsFusionados(false);
    actualizarTextoBotonExtraer();
  }

  function actualizarTextoBotonExtraer() {
    const btnPDF = document.getElementById('btnProcesarPDF');
    if (btnPDF) {
      if (lotesImportados.length > 0) {
        btnPDF.innerHTML = '<i class="bi bi-plus-circle-fill me-1"></i> Extraer y Agregar PDF';
      } else {
        btnPDF.innerHTML = '<i class="bi bi-cpu me-1"></i> Extraer Celdas';
      }
    }

    const btnTexto = document.getElementById('btnProcesarTextoPegado');
    if (btnTexto) {
      if (lotesImportados.length > 0) {
        btnTexto.innerHTML = '<i class="bi bi-plus-circle-fill me-1"></i> Procesar y Agregar Texto';
      } else {
        btnTexto.innerHTML = '<i class="bi bi-magic me-1"></i> Procesar Texto Pegado';
      }
    }
  }

  function crearNuevoLote(tipo, nombreOrigen, products) {
    contadorLotesSecuencia += 1;
    const lote = {
      id: `lote_${Date.now()}_${contadorLotesSecuencia}`,
      tipo: tipo, // 'pdf' | 'texto' | 'historial'
      nombreOrigen: nombreOrigen || (tipo === 'pdf' ? `PDF #${lotesImportados.length + 1}` : `Texto #${lotesImportados.length + 1}`),
      items: (products || []).map((p) => ({
        ...p,
        cantidad: parseFloat(p.cantidad) || 1.0,
        precio_unitario: parseFloat(p.precio_unitario) || 0.0,
        selected: p.selected !== undefined ? Boolean(p.selected) : true
      }))
    };
    lotesImportados.push(lote);
    return lote;
  }

  // =========================================================================
  // MODAL DE DUPLICADOS (POR PDF EXTRAÍDO)
  // =========================================================================
  function mostrarModalDuplicados(duplicados) {
    if (!duplicados || duplicados.length === 0) return;

    const contenedor = document.getElementById('contenedorComparacionDuplicados');
    if (!contenedor) return;
    contenedor.innerHTML = '';

    duplicados.forEach((group) => {
      const card = document.createElement('div');
      card.className = 'card border-warning shadow-sm';

      const diffs = group.diferencias_campos || [];
      let filasHtml = '';

      (group.ocurrencias || []).forEach((occ, oIdx) => {
        const esDifCant = diffs.includes('cantidad');
        const esDifPrecio = diffs.includes('precio_unitario');

        filasHtml += `
          <tr class="${oIdx % 2 === 0 ? 'table-warning' : 'table-info'} align-middle">
            <td class="text-center fw-bold">Repetición #${oIdx + 1}</td>
            <td class="text-center fw-bold text-dark"><span class="badge bg-secondary fs-6">Ítem #${occ.item_index || '?'}</span></td>
            <td class="text-center"><span class="badge bg-dark fs-6">${escapeHtml(occ.um || 'Pza')}</span></td>
            <td class="text-center">
              <span class="badge ${esDifCant ? 'bg-warning text-dark fs-6 border border-dark p-2' : 'bg-primary fs-6 p-2'} fw-bold">
                ${occ.cantidad} ${escapeHtml(occ.um || '')}
              </span>
            </td>
            <td class="text-end fw-bold">Bs ${parseFloat(occ.precio_unitario || 0).toFixed(2)}</td>
            <td class="text-end">
              <span class="badge ${esDifPrecio ? 'bg-danger text-white fs-6 p-2' : 'bg-success text-white fs-6 p-2'} fw-bold">
                Bs ${parseFloat(occ.precio_total || 0).toFixed(2)}
              </span>
            </td>
          </tr>
        `;
      });

      card.innerHTML = `
        <div class="card-header bg-warning bg-opacity-25 border-warning d-flex justify-content-between align-items-center flex-wrap gap-2">
          <div>
            <span class="badge bg-dark fs-6 me-2">Código: ${escapeHtml(group.codigo)}</span>
            <strong class="text-dark fs-6">${escapeHtml(group.descripcion)}</strong>
          </div>
          <span class="badge bg-danger fs-6"><i class="bi bi-layers-fill me-1"></i>${group.total_repeticiones} Repeticiones</span>
        </div>
        <div class="card-body p-2">
          <div class="table-responsive">
            <table class="table table-sm table-bordered align-middle mb-2">
              <thead class="table-dark">
                <tr>
                  <th class="text-center" style="width: 140px;">Ocurrencia</th>
                  <th class="text-center" style="width: 120px;">Fila Origen</th>
                  <th class="text-center" style="width: 90px;">U/M</th>
                  <th class="text-center">Cantidad Extraída</th>
                  <th class="text-end">P/Unitario (Bs)</th>
                  <th class="text-end">Subtotal (Bs)</th>
                </tr>
              </thead>
              <tbody>${filasHtml}</tbody>
            </table>
          </div>
          <div class="bg-success bg-opacity-10 p-2 rounded border border-success d-flex justify-content-between align-items-center flex-wrap gap-2 mt-2">
            <span>
              <i class="bi bi-calculator-fill text-success fs-5 me-1"></i>
              <strong class="text-success">Consolidación Automática en este PDF:</strong>
            </span>
            <span class="badge bg-success fs-6 p-2">
              Suma Cantidad: <strong>${group.cantidad_consolidada} ${escapeHtml(group.um)}</strong> | Subtotal Combinado: <strong>Bs ${parseFloat(group.subtotal_consolidado || 0).toFixed(2)}</strong>
            </span>
          </div>
        </div>
      `;
      contenedor.appendChild(card);
    });

    const modalElem = document.getElementById('modalDuplicadosDetectados');
    if (modalElem) {
      const modalInstance = new bootstrap.Modal(modalElem, {
        backdrop: 'static',
        keyboard: false
      });
      modalInstance.show();
    }
  }

  function toggleModoConsolidacion(checked) {
    const desc = document.getElementById('descModoConsolidar');
    if (desc) {
      if (checked) {
        desc.innerHTML = '<strong>ACTIVADO:</strong> Fusiona productos duplicados <em>dentro de cada PDF</em> sumando sus cantidades, respetando el orden entre PDFs.';
      } else {
        desc.innerHTML = '<strong>DESACTIVADO:</strong> Conserva todas las filas por separado sin fusionar cantidades.';
      }
    }
  }

  // =========================================================================
  // EXTRACCIÓN MULTI-PDF Y TEXTO PEGADO (ACUMULATIVO EN ORDEN)
  // =========================================================================
  function procesarPDFSubido() {
    const fileInput = document.getElementById('archivoPDFInput');
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      mostrarAlertaPDF('Por favor, seleccione un archivo PDF.', 'warning');
      return;
    }

    const archivo = fileInput.files[0];
    const chkConsolidar = document.getElementById('chkConsolidarDuplicados');
    const consolidar = chkConsolidar ? chkConsolidar.checked : true;

    const formData = new FormData();
    formData.append('archivo_pdf', archivo);
    formData.append('consolidar_duplicados', consolidar ? 'true' : 'false');

    const spinner = document.getElementById('spinnerProcesandoPDF');
    if (spinner) spinner.style.display = 'block';
    ocultarAlertaPDF();

    fetch('/productos/importar-pdf', {
      method: 'POST',
      body: formData
    })
      .then(async (res) => {
        const rawText = await res.text();
        let data = null;
        try {
          data = JSON.parse(rawText);
        } catch (e) {
          throw new Error(`HTTP ${res.status} ${res.statusText || ''}`.trim());
        }
        return data;
      })
      .then((data) => {
        if (spinner) spinner.style.display = 'none';
        if (data.success) {
          const nombreOrigen = data.nombre_sugerido || archivo.name.replace(/\.pdf$/i, '');
          const inputNombre = document.getElementById('nombreImportacionInput');
          if (inputNombre && !inputNombre.value.trim()) {
            inputNombre.value = nombreOrigen;
          }

          const nuevoLote = crearNuevoLote('pdf', nombreOrigen, data.products);
          fileInput.value = ''; // Listo para elegir el siguiente PDF

          renderTablaItemsImportados(nuevoLote.id);

          const numLote = lotesImportados.length;
          if (consolidar && data.has_duplicates && data.duplicados && data.duplicados.length > 0) {
            mostrarModalDuplicados(data.duplicados);
            mostrarAlertaPDF(
              `⚠️ <strong>PDF #${numLote} ("${escapeHtml(nombreOrigen)}") agregado:</strong> ${data.duplicados.length} código(s) duplicados consolidados en ${data.total_unicos} ítems únicos. Puedes seguir agregando más PDFs.`,
              'warning'
            );
          } else if (!consolidar) {
            mostrarAlertaPDF(
              `📄 <strong>PDF #${numLote} ("${escapeHtml(nombreOrigen)}") agregado:</strong> ${data.total_extraidos} ítems individuales. Puedes agregar otro PDF o guardar la importación fusionada.`,
              'info'
            );
          } else {
            mostrarAlertaPDF(
              `✅ <strong>PDF #${numLote} ("${escapeHtml(nombreOrigen)}") agregado con éxito</strong> (${nuevoLote.items.length} productos). Puedes seleccionar otro PDF para continuar la lista.`,
              'success'
            );
          }
        } else {
          mostrarAlertaPDF(data.message || 'Error al procesar el PDF', 'danger');
        }
      })
      .catch((err) => {
        console.error(err);
        if (spinner) spinner.style.display = 'none';
        mostrarAlertaPDF(`Error de conexión o fallo procesando el PDF (${err.message || 'sin respuesta'}).`, 'danger');
      });
  }

  function procesarTextoPegadoUI() {
    const txtEl = document.getElementById('textoPegadoInput');
    const texto = txtEl ? txtEl.value.trim() : '';
    if (!texto) {
      mostrarAlertaPDF('Por favor, pega el texto de la tabla en el cuadro de texto.', 'warning');
      return;
    }

    const chkConsolidar = document.getElementById('chkConsolidarDuplicados');
    const consolidar = chkConsolidar ? chkConsolidar.checked : true;

    const spinner = document.getElementById('spinnerProcesandoPDF');
    if (spinner) spinner.style.display = 'block';
    ocultarAlertaPDF();

    fetch('/productos/pegar-texto', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        texto: texto,
        consolidar_duplicados: consolidar
      })
    })
      .then(async (res) => {
        const rawText = await res.text();
        try {
          return JSON.parse(rawText);
        } catch (e) {
          throw new Error(`HTTP ${res.status} ${res.statusText || ''}`.trim());
        }
      })
      .then((data) => {
        if (spinner) spinner.style.display = 'none';
        if (data.success) {
          ultimoTextoProcesado = texto;
          const etiqueta = `Texto pegado #${lotesImportados.length + 1}`;
          const nuevoLote = crearNuevoLote('texto', etiqueta, data.products);

          if (txtEl) txtEl.value = '';
          actualizarContadorLineasPegadas();

          renderTablaItemsImportados(nuevoLote.id);

          if (consolidar && data.has_duplicates && data.duplicados && data.duplicados.length > 0) {
            mostrarModalDuplicados(data.duplicados);
            mostrarAlertaPDF(
              `⚠️ <strong>${etiqueta} agregado:</strong> ${data.duplicados.length} código(s) duplicados consolidados en ${data.total_unicos} ítems únicos.`,
              'warning'
            );
          } else {
            mostrarAlertaPDF(
              `✅ <strong>${etiqueta} agregado con éxito</strong> (${nuevoLote.items.length} productos).`,
              'success'
            );
          }
        } else {
          mostrarAlertaPDF(data.message || 'Error al procesar el texto pegado', 'danger');
        }
      })
      .catch((err) => {
        console.error(err);
        if (spinner) spinner.style.display = 'none';
        mostrarAlertaPDF(`Error procesando el texto pegado (${err.message || 'sin respuesta'}).`, 'danger');
      });
  }

  // =========================================================================
  // RENDERIZADO DE BARRA DE LOTES Y TABLA SEPARADA POR PDF
  // =========================================================================
  function renderBarraLotes() {
    const barra = document.getElementById('barraLotesImportados');
    if (!barra) return;

    if (!lotesImportados || lotesImportados.length === 0) {
      barra.style.display = 'none';
      barra.innerHTML = '';
      return;
    }

    let html = `<span class="pdf-lotes-bar-title"><i class="bi bi-collection-fill text-success"></i> Orden de fusión (${lotesImportados.length}):</span>`;

    lotesImportados.forEach((lote, idx) => {
      const icono = lote.tipo === 'texto' ? 'bi-clipboard-data-fill text-primary' : 'bi-file-earmark-pdf-fill text-danger';
      const etiqueta = lote.tipo === 'texto' ? `Texto #${idx + 1}` : `PDF #${idx + 1}`;
      html += `
        <button type="button" class="pdf-lote-pill" onclick="scrollALoteImportado('${lote.id}')" title="Ir a ${escapeHtml(lote.nombreOrigen)}">
          <i class="bi ${icono}"></i>
          <span class="badge ${lote.tipo === 'texto' ? 'bg-primary' : 'bg-success'} rounded-pill">${etiqueta}</span>
          <span class="pdf-lote-pill-name">${escapeHtml(lote.nombreOrigen)}</span>
          <span class="badge bg-light text-dark border rounded-pill">${lote.items.length}</span>
        </button>
      `;
      if (idx < lotesImportados.length - 1) {
        html += '<span class="pdf-lote-arrow" aria-hidden="true"><i class="bi bi-arrow-right"></i></span>';
      }
    });

    barra.innerHTML = html;
    barra.style.display = 'flex';
  }

  function scrollALoteImportado(loteId) {
    const row = document.getElementById(`header_${loteId}`);
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function renderTablaItemsImportados(scrollToLoteId = null) {
    const tbody = document.getElementById('tbodyItemsExtraidos');
    if (!tbody) return;
    tbody.innerHTML = '';

    // Limpiar lotes que hayan quedado sin ítems
    lotesImportados = lotesImportados.filter((l) => l.items && l.items.length > 0);
    sincronizarEstadoGlobal();
    renderBarraLotes();

    const secPrev = document.getElementById('secPrevisualizacionImport');
    const footerBotones = document.getElementById('footerBotonesImport');

    if (lotesImportados.length === 0) {
      if (secPrev) secPrev.style.display = 'none';
      if (footerBotones) footerBotones.style.display = 'none';
      actualizarContadorItems(0);
      return;
    }

    let subtotalGeneral = 0;
    let contadorGlobal = 0;

    lotesImportados.forEach((lote, loteIdx) => {
      const todosMarcadosLote = lote.items.length > 0 && lote.items.every((i) => i.selected);
      const subtotalLote = lote.items.reduce((acc, it) => {
        const c = parseFloat(it.cantidad) || 1.0;
        const p = parseFloat(it.precio_unitario) || 0.0;
        return acc + (it.selected ? Math.round(c * p * 100) / 100 : 0);
      }, 0);

      const esTexto = lote.tipo === 'texto';
      const badgeEtiqueta = esTexto ? `TEXTO #${loteIdx + 1}` : `PDF #${loteIdx + 1}`;
      const badgeColor = esTexto ? 'bg-primary text-white' : 'bg-success text-white';
      const iconClass = esTexto ? 'bi-clipboard-data-fill' : 'bi-file-earmark-pdf-fill';

      // 1. Fila separadora del PDF / lote
      const trHeader = document.createElement('tr');
      trHeader.id = `header_${lote.id}`;
      trHeader.className = `pdf-lote-header-row ${esTexto ? 'pdf-lote-tipo-texto' : ''}`;
      trHeader.innerHTML = `
        <td colspan="9">
          <div class="pdf-lote-header-inner">
            <div class="pdf-lote-header-left">
              <input class="form-check-input m-0" type="checkbox" ${todosMarcadosLote ? 'checked' : ''}
                title="Marcar/desmarcar todos los ítems de este documento"
                onchange="toggleSeleccionarLote(${loteIdx}, this.checked)">
              <span class="pdf-lote-badge-orden ${badgeColor}">
                <i class="bi ${iconClass}"></i> ${badgeEtiqueta}
              </span>
              <span class="pdf-lote-nombre">${escapeHtml(lote.nombreOrigen)}</span>
              <div class="pdf-lote-meta">
                <span class="badge bg-dark text-white rounded-pill">${lote.items.length} ítem(s)</span>
                <span class="badge bg-white text-success border border-success-subtle rounded-pill fw-bold">Subtotal: Bs ${subtotalLote.toFixed(2)}</span>
              </div>
            </div>
            <div class="pdf-lote-actions">
              <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="moverLoteImportado(${loteIdx}, -1)"
                ${loteIdx === 0 ? 'disabled' : ''}
                title="Subir este PDF en el orden de fusión">
                <i class="bi bi-arrow-up"></i>
              </button>
              <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="moverLoteImportado(${loteIdx}, 1)"
                ${loteIdx === lotesImportados.length - 1 ? 'disabled' : ''}
                title="Bajar este PDF en el orden de fusión">
                <i class="bi bi-arrow-down"></i>
              </button>
              <button type="button" class="btn btn-sm btn-outline-danger"
                onclick="eliminarLoteImportado(${loteIdx})"
                title="Quitar este PDF completo">
                <i class="bi bi-trash3-fill"></i>
              </button>
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(trHeader);

      // 2. Filas editables de productos pertenecientes a este PDF
      lote.items.forEach((item, itemIdx) => {
        contadorGlobal += 1;
        const cant = parseFloat(item.cantidad) || 1.0;
        const pu = parseFloat(item.precio_unitario) || 0.0;
        const ptotal = Math.round(cant * pu * 100) / 100;
        item.precio_total = ptotal;

        if (item.selected) {
          subtotalGeneral += ptotal;
        }

        let customBadgesHtml = '';
        if (item.campos_personalizados && typeof item.campos_personalizados === 'object' && Object.keys(item.campos_personalizados).length > 0) {
          customBadgesHtml = '<div class="mt-1 d-flex flex-wrap gap-1">';
          for (const [k, v] of Object.entries(item.campos_personalizados)) {
            customBadgesHtml += `<span class="badge bg-light text-dark border me-1 shadow-sm" style="font-size: 0.73rem;"><i class="bi bi-tag-fill text-warning me-1"></i><strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}</span>`;
          }
          customBadgesHtml += '</div>';
        }

        const tr = document.createElement('tr');
        tr.className = `pdf-item-row ${item.selected ? '' : 'opacity-50 bg-light'}`;
        tr.innerHTML = `
          <td class="text-center align-middle">
            <input class="form-check-input" type="checkbox" ${item.selected ? 'checked' : ''}
              onchange="toggleItemSeleccionado(${loteIdx}, ${itemIdx}, this.checked)">
            <span class="pdf-item-row-num">#${contadorGlobal}</span>
          </td>
          <td class="align-middle">
            <input type="text" class="form-control form-control-sm font-monospace fw-bold text-primary border-secondary-subtle"
              value="${escapeHtml(item.codigo || '')}"
              onchange="actualizarItemCampo(${loteIdx}, ${itemIdx}, 'codigo', this.value)" style="border-radius: 6px;">
          </td>
          <td class="align-middle">
            <textarea class="form-control form-control-sm fw-semibold text-dark border-secondary-subtle auto-expand-desc" rows="2"
              style="min-height: 46px; max-height: 180px; font-size: 0.88rem; line-height: 1.35; resize: vertical; border-radius: 6px; background-color: #fcfcfc;"
              onchange="actualizarItemCampo(${loteIdx}, ${itemIdx}, 'descripcion', this.value)"
              oninput="autoAjustarTextarea(this)">${escapeHtml(item.descripcion || '')}</textarea>
            ${customBadgesHtml}
          </td>
          <td class="align-middle">
            <input type="text" class="form-control form-control-sm fw-medium border-secondary-subtle"
              value="${escapeHtml(item.marca || '')}"
              onchange="actualizarItemCampo(${loteIdx}, ${itemIdx}, 'marca', this.value)" style="border-radius: 6px;">
          </td>
          <td class="align-middle">
            <input type="text" class="form-control form-control-sm text-center fw-bold border-secondary-subtle"
              value="${escapeHtml(item.um || 'Pza')}"
              onchange="actualizarItemCampo(${loteIdx}, ${itemIdx}, 'um', this.value)" style="border-radius: 6px;">
          </td>
          <td class="align-middle">
            <input type="number" step="any" class="form-control form-control-sm text-center fw-bold text-primary border-secondary-subtle"
              value="${cant}"
              onchange="actualizarItemCantidad(${loteIdx}, ${itemIdx}, parseFloat(this.value) || 1)" style="border-radius: 6px;">
          </td>
          <td class="align-middle">
            <input type="number" step="any" class="form-control form-control-sm text-end fw-bold border-secondary-subtle"
              value="${pu}"
              onchange="actualizarItemPrecio(${loteIdx}, ${itemIdx}, parseFloat(this.value) || 0)" style="border-radius: 6px;">
          </td>
          <td class="text-end align-middle">
            <span class="badge bg-success-subtle text-success border border-success-subtle fs-6 px-2 py-1 fw-bold">
              Bs ${ptotal.toFixed(2)}
            </span>
          </td>
          <td class="text-center align-middle">
            <button type="button" class="btn btn-sm btn-outline-danger border-0 rounded-circle" title="Eliminar fila"
              onclick="eliminarItemImportado(${loteIdx}, ${itemIdx})">
              <i class="bi bi-trash-fill fs-6"></i>
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    });

    if (secPrev) secPrev.style.display = 'block';
    if (footerBotones) footerBotones.style.display = 'block';
    actualizarContadorItems(subtotalGeneral);

    setTimeout(() => {
      document.querySelectorAll('#tbodyItemsExtraidos .auto-expand-desc').forEach((el) => autoAjustarTextarea(el));
      if (scrollToLoteId) {
        scrollALoteImportado(scrollToLoteId);
      }
    }, 20);
  }

  // =========================================================================
  // CONTROLES DE LOTES E ÍTEMS
  // =========================================================================
  function toggleSeleccionarLote(loteIdx, checked) {
    const lote = lotesImportados[loteIdx];
    if (!lote) return;
    lote.items.forEach((item) => {
      item.selected = checked;
    });
    renderTablaItemsImportados();
  }

  function moverLoteImportado(loteIdx, direccion) {
    const destino = loteIdx + direccion;
    if (destino < 0 || destino >= lotesImportados.length) return;
    const temp = lotesImportados[loteIdx];
    lotesImportados[loteIdx] = lotesImportados[destino];
    lotesImportados[destino] = temp;
    renderTablaItemsImportados(temp.id);
  }

  function eliminarLoteImportado(loteIdx) {
    const lote = lotesImportados[loteIdx];
    if (!lote) return;
    lotesImportados.splice(loteIdx, 1);
    renderTablaItemsImportados();
  }

  function toggleItemSeleccionado(loteIdx, itemIdx, checked) {
    if (!lotesImportados[loteIdx] || !lotesImportados[loteIdx].items[itemIdx]) return;
    lotesImportados[loteIdx].items[itemIdx].selected = checked;
    renderTablaItemsImportados();
  }

  function toggleSeleccionarTodos(checked) {
    lotesImportados.forEach((lote) => {
      lote.items.forEach((item) => {
        item.selected = checked;
      });
    });
    renderTablaItemsImportados();
  }

  function actualizarItemCampo(loteIdx, itemIdx, campo, valor) {
    if (!lotesImportados[loteIdx] || !lotesImportados[loteIdx].items[itemIdx]) return;
    lotesImportados[loteIdx].items[itemIdx][campo] = valor;
    sincronizarEstadoGlobal();
  }

  function actualizarItemCantidad(loteIdx, itemIdx, val) {
    if (!lotesImportados[loteIdx] || !lotesImportados[loteIdx].items[itemIdx]) return;
    lotesImportados[loteIdx].items[itemIdx].cantidad = val;
    renderTablaItemsImportados();
  }

  function actualizarItemPrecio(loteIdx, itemIdx, val) {
    if (!lotesImportados[loteIdx] || !lotesImportados[loteIdx].items[itemIdx]) return;
    lotesImportados[loteIdx].items[itemIdx].precio_unitario = val;
    renderTablaItemsImportados();
  }

  function eliminarItemImportado(loteIdx, itemIdx) {
    if (!lotesImportados[loteIdx]) return;
    lotesImportados[loteIdx].items.splice(itemIdx, 1);
    renderTablaItemsImportados();
  }

  function actualizarContadorItems(subtotalTotal = null) {
    const todos = obtenerItemsFusionados(false);
    const total = todos.length;
    const marcados = todos.filter((i) => i.selected);

    if (subtotalTotal === null) {
      subtotalTotal = marcados.reduce(
        (sum, item) => sum + ((parseFloat(item.cantidad) || 1.0) * (parseFloat(item.precio_unitario) || 0.0)),
        0
      );
    }

    const chkConsolidar = document.getElementById('chkConsolidarDuplicados');
    const esConsolidado = chkConsolidar ? chkConsolidar.checked : true;
    const numLotes = lotesImportados.length;
    const prefijoLotes = numLotes > 1 ? `${numLotes} PDFs | ` : '';

    const badgeElem = document.getElementById('badgeContadorItems');
    if (badgeElem) {
      badgeElem.textContent = `${prefijoLotes}Ítems: ${total} | Marcados: ${marcados.length} | Subtotal Total: Bs ${subtotalTotal.toFixed(2)}`;
      badgeElem.className = esConsolidado ? 'badge bg-success fs-6' : 'badge bg-primary fs-6';
    }

    const chkAll = document.getElementById('checkSeleccionarTodos');
    if (chkAll) {
      chkAll.checked = total > 0 && marcados.length === total;
    }
  }

  // =========================================================================
  // GUARDAR IMPORTACIÓN (FUSIÓN SECUENCIAL EN UNA SOLA TABLA)
  // =========================================================================
  async function guardarImportacionActual() {
    // Si el usuario dejó texto pegado sin procesar, agregarlo al final antes de guardar
    const txtEl = document.getElementById('textoPegadoInput');
    const textoActual = txtEl ? txtEl.value.trim() : '';
    if (textoActual && textoActual !== ultimoTextoProcesado) {
      try {
        const chkConsolidar = document.getElementById('chkConsolidarDuplicados');
        const consolidar = chkConsolidar ? chkConsolidar.checked : true;
        const resp = await fetch('/productos/pegar-texto', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ texto: textoActual, consolidar_duplicados: consolidar })
        });
        const dataProc = await resp.json();
        if (dataProc.success && dataProc.products) {
          crearNuevoLote('texto', `Texto pegado #${lotesImportados.length + 1}`, dataProc.products);
          ultimoTextoProcesado = textoActual;
          if (txtEl) txtEl.value = '';
          actualizarContadorLineasPegadas();
          renderTablaItemsImportados();
        }
      } catch (e) {
        console.error('Error auto-sincronizando texto pegado:', e);
      }
    }

    // Fusión secuencial estricta: PDF #1 -> PDF #2 -> ... -> PDF #N
    const itemsFusionados = obtenerItemsFusionados(false);
    if (!itemsFusionados || itemsFusionados.length === 0) {
      mostrarAlertaPDF('⚠️ No hay items extraídos para guardar.', 'warning');
      return;
    }

    const inputNombre = document.getElementById('nombreImportacionInput');
    let nombre = inputNombre ? inputNombre.value.trim() : '';
    if (!nombre) {
      const fechaHora = new Date().toLocaleString('es-ES', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
      nombre = lotesImportados.length > 1
        ? `Importación Combinada (${lotesImportados.length} PDFs) - ${fechaHora}`
        : `Importación PDF ${fechaHora}`;
      if (inputNombre) inputNombre.value = nombre;
    }

    const btn = document.getElementById('btnGuardarImportacion');
    const txtOrig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Guardando...';
    ocultarAlertaPDF();

    const cantLotes = lotesImportados.length;

    fetch('/productos/guardar-importacion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre_importacion: nombre,
        items: itemsFusionados
      })
    })
      .then((res) => res.json())
      .then((data) => {
        btn.disabled = false;
        if (data.success) {
          if (data.nombre_importacion && inputNombre) {
            inputNombre.value = data.nombre_importacion;
          }
          btn.className = 'btn btn-success fw-bold';
          btn.innerHTML = '¡Guardado Exitosamente!';
          const detalleFusion = cantLotes > 1
            ? ` (${itemsFusionados.length} ítems fusionados de ${cantLotes} documentos en orden secuencial)`
            : ` (${itemsFusionados.length} ítems)`;
          mostrarAlertaPDF(
            `✅ <strong>Importación guardada exitosamente:</strong> "${escapeHtml(data.nombre_importacion || nombre)}"${detalleFusion}.`,
            'success'
          );
          setTimeout(() => {
            btn.className = 'btn btn-outline-success';
            btn.innerHTML = txtOrig;
          }, 2500);
        } else {
          btn.className = 'btn btn-outline-danger';
          btn.innerHTML = txtOrig;
          mostrarAlertaPDF(`❌ <strong>Error al guardar:</strong> ${escapeHtml(data.message)}`, 'danger');
        }
      })
      .catch((err) => {
        btn.disabled = false;
        btn.innerHTML = txtOrig;
        console.error(err);
        mostrarAlertaPDF('❌ <strong>Error de conexión:</strong> No se pudo guardar la importación.', 'danger');
      });
  }

  // =========================================================================
  // PDF DIRECTO Y REGISTRO EN CATÁLOGO (ORDEN FUSIONADO)
  // =========================================================================
  function imprimirPDFDirecto() {
    const marcados = obtenerItemsFusionados(true);
    if (!marcados || marcados.length === 0) {
      mostrarAlertaPDF('Por favor, seleccione al menos un producto (marque la casilla) para generar el PDF.', 'warning');
      return;
    }

    const descuentoInput = document.getElementById('inputDescuentoPDFDirecto');
    const descuento = descuentoInput ? parseFloat(descuentoInput.value) || 0 : 0;

    const inputNombre = document.getElementById('nombreImportacionInput');
    const nombre = (inputNombre && inputNombre.value.trim()) || 'Cotización Rápida';
    const selectCliente = document.getElementById('selectClientePDFDirecto');
    const cliente_id = selectCliente && selectCliente.value ? selectCliente.value : null;
    let nombre_cliente_final = nombre;

    if (selectCliente && selectCliente.value) {
      const selectedOption = selectCliente.options[selectCliente.selectedIndex];
      nombre_cliente_final = selectedOption.text;
    }

    const payload = {
      items: marcados,
      descuento_porcentaje: descuento,
      nombre_cliente: nombre_cliente_final,
      cliente_id: cliente_id
    };

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/cotizaciones/pdf_directo_importacion';
    form.target = '_blank';

    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'data';
    input.value = JSON.stringify(payload);

    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  }

  function registrarSeleccionadosEnCatalogo(irACotizacion = false) {
    const marcados = obtenerItemsFusionados(true);
    if (!marcados || marcados.length === 0) {
      mostrarAlertaPDF('Por favor, seleccione al menos un producto para registrar en el catálogo.', 'warning');
      return;
    }

    const empresa = document.getElementById('empresaDestinoImport').value.trim() || 'General';
    const categoria_id = document.getElementById('categoriaDestinoImport').value || null;
    const chkExtraerCant = document.getElementById('chkExtraerCantidadesReales');
    const respetar_cantidades = chkExtraerCant ? chkExtraerCant.checked : true;

    let tipo_documento = 'factura';
    const radioCatalogo = document.getElementById('tipoCatalogo');
    if (radioCatalogo && radioCatalogo.checked) {
      tipo_documento = 'catalogo';
    }

    const btn = document.getElementById('btnRegistrarSeleccionados');
    const txtOrig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Registrando...';

    fetch('/productos/registrar-seleccionados', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: marcados,
        empresa: empresa,
        categoria_id: categoria_id,
        respetar_cantidades: respetar_cantidades,
        tipo_documento: tipo_documento
      })
    })
      .then((res) => res.json())
      .then((data) => {
        btn.disabled = false;
        btn.innerHTML = txtOrig;

        if (data.success) {
          mostrarAlertaPDF(`✅ ${escapeHtml(data.message)}`, 'success');
          setTimeout(() => {
            if (irACotizacion) {
              window.location.href = '/cotizaciones?tipo_producto=importados';
            } else {
              window.location.href = '/productos?tab=importados';
            }
          }, 1200);
        } else {
          mostrarAlertaPDF(escapeHtml(data.message), 'danger');
        }
      })
      .catch((err) => {
        btn.disabled = false;
        btn.innerHTML = txtOrig;
        console.error(err);
        mostrarAlertaPDF('Error registrando los productos en la base de datos.', 'danger');
      });
  }

  // =========================================================================
  // HISTORIAL DE IMPORTACIONES
  // =========================================================================
  function cargarHistorialImportaciones() {
    const contenedor = document.getElementById('listaHistorialImportaciones');
    if (!contenedor) return;
    contenedor.innerHTML = '<div class="text-center p-3"><div class="spinner-border text-info" role="status"></div></div>';

    fetch('/productos/importaciones')
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.importaciones && data.importaciones.length > 0) {
          contenedor.innerHTML = '';
          data.importaciones.forEach((imp) => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center flex-wrap gap-2';
            itemDiv.innerHTML = `
              <div>
                <h6 class="mb-1 text-primary"><i class="bi bi-file-earmark-pdf"></i> ${escapeHtml(imp.nombre_importacion)}</h6>
                <small class="text-muted"><i class="bi bi-calendar"></i> ${escapeHtml(imp.fecha_importacion)} | <i class="bi bi-box"></i> ${imp.total_items} items</small>
              </div>
              <div class="d-flex gap-1">
                <button class="btn btn-sm btn-outline-primary" onclick="cargarImportacionGuardada(${imp.id})">
                  <i class="bi bi-folder2-open"></i> Abrir / Editar
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarImportacionHistorial(event, ${imp.id}, '${escapeHtml(imp.nombre_importacion)}')">
                  <i class="bi bi-trash"></i> Eliminar
                </button>
              </div>
            `;
            contenedor.appendChild(itemDiv);
          });
        } else {
          contenedor.innerHTML = '<div class="alert alert-info mb-0">No hay importaciones guardadas previamente en el historial.</div>';
        }
      })
      .catch((err) => {
        console.error(err);
        contenedor.innerHTML = '<div class="alert alert-danger mb-0">Error cargando el historial de importaciones.</div>';
      });
  }

  function eliminarImportacionHistorial(event, id, nombre) {
    if (event) event.stopPropagation();
    if (!confirm(`¿Está seguro de que desea eliminar la importación "${nombre}" del historial?\n\nEsta acción eliminará el registro del historial.`)) {
      return;
    }

    fetch(`/productos/importacion/${id}`, {
      method: 'DELETE'
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          cargarHistorialImportaciones();
        } else {
          alert(data.message || 'Error al eliminar la importación');
        }
      })
      .catch((err) => {
        console.error(err);
        alert('Error de conexión al eliminar la importación.');
      });
  }

  function cargarImportacionGuardada(id) {
    const modalHistEl = document.getElementById('modalHistorialImportaciones');
    const modalHist = modalHistEl ? bootstrap.Modal.getInstance(modalHistEl) : null;
    if (modalHist) modalHist.hide();

    const modalImpEl = document.getElementById('modalImportarPDF');
    const modalImp = bootstrap.Modal.getOrCreateInstance(modalImpEl);
    modalImp.show();

    const spinner = document.getElementById('spinnerProcesandoPDF');
    if (spinner) spinner.style.display = 'block';
    const secPrev = document.getElementById('secPrevisualizacionImport');
    if (secPrev) secPrev.style.display = 'none';

    fetch(`/productos/importacion/${id}`)
      .then((res) => res.json())
      .then((data) => {
        if (spinner) spinner.style.display = 'none';
        if (data.success) {
          lotesImportados = [];
          const inputNombre = document.getElementById('nombreImportacionInput');
          if (inputNombre) inputNombre.value = data.importacion.nombre_importacion;

          const itemsNormalizados = (data.items || []).map((item) => ({
            temp_id: item.id,
            codigo: item.codigo,
            descripcion: item.descripcion,
            marca: item.marca,
            um: item.um,
            cantidad: item.cantidad || 1,
            precio_unitario: item.precio_unitario,
            selected: true
          }));

          crearNuevoLote('historial', data.importacion.nombre_importacion, itemsNormalizados);
          ultimoTextoProcesado = '';
          const txtEl = document.getElementById('textoPegadoInput');
          if (txtEl) txtEl.value = '';
          actualizarContadorLineasPegadas();

          renderTablaItemsImportados();
          mostrarAlertaPDF(
            `Importación "${escapeHtml(data.importacion.nombre_importacion)}" (${data.items.length} ítems) cargada. Puedes editarla o agregar más PDFs al final.`,
            'info'
          );
        } else {
          mostrarAlertaPDF(escapeHtml(data.message), 'danger');
        }
      })
      .catch((err) => {
        console.error(err);
        if (spinner) spinner.style.display = 'none';
        mostrarAlertaPDF('Error al abrir la importación guardada.', 'danger');
      });
  }

  // =========================================================================
  // ALERTAS, CONTADORES Y LIMPIEZA
  // =========================================================================
  function mostrarAlertaPDF(mensaje, tipo) {
    const alertTop = document.getElementById('alertModalPDF');
    const alertFooter = document.getElementById('alertModalPDFFooter');

    if (alertTop) {
      alertTop.className = `alert alert-${tipo} my-2`;
      alertTop.innerHTML = mensaje;
      alertTop.style.display = 'block';
    }

    if (alertFooter) {
      alertFooter.className = `alert alert-${tipo} my-2`;
      alertFooter.innerHTML = mensaje;
      alertFooter.style.display = 'block';
      try {
        alertFooter.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (e) {}
    }
  }

  function ocultarAlertaPDF() {
    const alertTop = document.getElementById('alertModalPDF');
    const alertFooter = document.getElementById('alertModalPDFFooter');
    if (alertTop) alertTop.style.display = 'none';
    if (alertFooter) alertFooter.style.display = 'none';
  }

  function actualizarContadorLineasPegadas() {
    const txtInput = document.getElementById('textoPegadoInput');
    if (!txtInput) return;
    const lineas = txtInput.value.split('\n').filter((l) => l.trim().length > 0);
    const badge = document.getElementById('lblContadorLineas');
    if (badge) {
      badge.innerHTML = `<i class="bi bi-list-ol"></i> ${lineas.length} líneas detectadas`;
      badge.className = lineas.length > 0 ? 'badge bg-success fs-6' : 'badge bg-primary fs-6';
    }
  }

  function limpiarModalImportacion() {
    const inputNombre = document.getElementById('nombreImportacionInput');
    if (inputNombre) inputNombre.value = '';

    const fileInput = document.getElementById('archivoPDFInput');
    if (fileInput) fileInput.value = '';

    const txtInput = document.getElementById('textoPegadoInput');
    if (txtInput) txtInput.value = '';
    ultimoTextoProcesado = '';
    actualizarContadorLineasPegadas();

    lotesImportados = [];
    sincronizarEstadoGlobal();

    const tbody = document.getElementById('tbodyItemsExtraidos');
    if (tbody) tbody.innerHTML = '';

    const barra = document.getElementById('barraLotesImportados');
    if (barra) {
      barra.style.display = 'none';
      barra.innerHTML = '';
    }

    const secPrev = document.getElementById('secPrevisualizacionImport');
    if (secPrev) secPrev.style.display = 'none';

    const footerBotones = document.getElementById('footerBotonesImport');
    if (footerBotones) footerBotones.style.display = 'none';

    ocultarAlertaPDF();

    const badge = document.getElementById('badgeContadorItems');
    if (badge) badge.textContent = 'Items extraídos: 0 | Marcados: 0';
  }

  // Exponer funciones públicas para los handlers inline del template
  window.escapeHtml = escapeHtml;
  window.autoAjustarTextarea = autoAjustarTextarea;
  window.mostrarModalDuplicados = mostrarModalDuplicados;
  window.toggleModoConsolidacion = toggleModoConsolidacion;
  window.procesarPDFSubido = procesarPDFSubido;
  window.procesarTextoPegadoUI = procesarTextoPegadoUI;
  window.renderTablaItemsImportados = renderTablaItemsImportados;
  window.scrollALoteImportado = scrollALoteImportado;
  window.toggleSeleccionarLote = toggleSeleccionarLote;
  window.moverLoteImportado = moverLoteImportado;
  window.eliminarLoteImportado = eliminarLoteImportado;
  window.toggleItemSeleccionado = toggleItemSeleccionado;
  window.toggleSeleccionarTodos = toggleSeleccionarTodos;
  window.actualizarItemCampo = actualizarItemCampo;
  window.actualizarItemCantidad = actualizarItemCantidad;
  window.actualizarItemPrecio = actualizarItemPrecio;
  window.eliminarItemImportado = eliminarItemImportado;
  window.actualizarContadorItems = actualizarContadorItems;
  window.guardarImportacionActual = guardarImportacionActual;
  window.imprimirPDFDirecto = imprimirPDFDirecto;
  window.registrarSeleccionadosEnCatalogo = registrarSeleccionadosEnCatalogo;
  window.cargarHistorialImportaciones = cargarHistorialImportaciones;
  window.eliminarImportacionHistorial = eliminarImportacionHistorial;
  window.cargarImportacionGuardada = cargarImportacionGuardada;
  window.mostrarAlertaPDF = mostrarAlertaPDF;
  window.ocultarAlertaPDF = ocultarAlertaPDF;
  window.actualizarContadorLineasPegadas = actualizarContadorLineasPegadas;
  window.limpiarModalImportacion = limpiarModalImportacion;
})();
