// Validación de formulario y botón Validar NIT

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

    const btnValidarNit = document.getElementById('btnValidarNit');
    const nitInput = document.querySelector('input[name="nit"]');

    if (btnValidarNit && nitInput) {
        btnValidarNit.addEventListener('click', function() {
            const nit = nitInput.value.trim();

            let feedbackEl = document.getElementById('nitFeedbackMsg');
            if (!feedbackEl) {
                feedbackEl = document.createElement('div');
                feedbackEl.id = 'nitFeedbackMsg';
                feedbackEl.className = 'mt-2 small fw-bold';
                const parentBox = nitInput.closest('.bento-clay-box') || nitInput.closest('.col-md-6') || nitInput.parentElement.parentElement;
                parentBox.appendChild(feedbackEl);
            }

            fetch('/api/validar-nit?nit=' + encodeURIComponent(nit))
                .then(response => response.json())
                .then(data => {
                    if (data.vacio) {
                        feedbackEl.className = 'mt-2 small text-info fw-bold';
                        feedbackEl.innerHTML = '<i class="bi bi-info-circle"></i> ' + data.mensaje;
                    } else if (data.valido) {
                        feedbackEl.className = 'mt-2 small text-success fw-bold';
                        feedbackEl.innerHTML = '<i class="bi bi-check-circle-fill"></i> ' + data.mensaje;
                    } else {
                        feedbackEl.className = 'mt-2 small text-danger fw-bold';
                        feedbackEl.innerHTML = '<i class="bi bi-exclamation-triangle-fill"></i> ' + data.mensaje;
                    }
                })
                .catch(err => {
                    console.error('Error al validar NIT:', err);
                });
        });
    }
});