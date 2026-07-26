// Generar código de cliente
document.getElementById('btnGenerarCodigo')?.addEventListener('click', function() {
    const prefijo = 'CLT-' + new Date().getFullYear().toString().slice(-2);
    const random = Math.floor(1000 + Math.random() * 9000);
    document.querySelector('[name="codigo_cliente"]').value = `${prefijo}-${random}`;
});

// Validación de formulario
const form = document.getElementById('clienteForm');
form?.addEventListener('submit', function(e) {
    if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
    }
    form.classList.add('was-validated');
}, false);