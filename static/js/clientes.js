// Validación de formulario y validación automática de NIT en segundo plano

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('clienteForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            } else {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<i class="bi bi-hourglass-split me-2 fs-6"></i> Guardando...';
                }
            }
            form.classList.add('was-validated');
        }, false);
    }

    const nitInput = document.querySelector('input[name="nit"]');

    if (nitInput) {
        let debounceTimer;

        function validarNitAutomatico() {
            const nit = nitInput.value.trim();
            const feedbackEl = document.getElementById('nitFeedbackMsg');

            // Si está vacío o es S/A, limpiar avisos
            if (!nit || nit.toUpperCase() === 'S/A' || nit.toUpperCase() === 'S/N') {
                if (feedbackEl) {
                    feedbackEl.className = 'small mt-1 ps-1 d-none';
                    feedbackEl.innerHTML = '';
                }
                return;
            }

            fetch('/api/validar-nit?nit=' + encodeURIComponent(nit))
                .then(response => response.json())
                .then(data => {
                    if (!feedbackEl) return;

                    if (data.vacio) {
                        feedbackEl.className = 'small mt-1 ps-1 d-none';
                        feedbackEl.innerHTML = '';
                    } else if (data.valido) {
                        feedbackEl.className = 'small mt-1 ps-1 text-success fw-bold';
                        feedbackEl.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> NIT/CI disponible';
                    } else {
                        feedbackEl.className = 'small mt-1 ps-1 text-danger fw-bold';
                        feedbackEl.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-1"></i> ' + data.mensaje;
                    }
                })
                .catch(err => {
                    console.error('Error al validar NIT automáticamente:', err);
                });
        }

        // Validación reactiva automática al dejar de escribir (debounce 400ms)
        nitInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(validarNitAutomatico, 400);
        });

        // Validación inmediata al salir del campo
        nitInput.addEventListener('blur', validarNitAutomatico);
    }
});