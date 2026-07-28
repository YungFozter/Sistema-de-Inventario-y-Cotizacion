// La generación de código de cliente ahora es automática en el backend (app.py)

// Validación de formulario
const form = document.getElementById('clienteForm');
form?.addEventListener('submit', function(e) {
    if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
    }
    form.classList.add('was-validated');
}, false);